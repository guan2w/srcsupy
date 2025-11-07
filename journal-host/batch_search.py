#!/usr/bin/env python3
"""
批量联网搜索工具 - batch_search.py

从 Excel 文件读取期刊名称，通过大模型联网搜索主办单位信息
支持并行处理、失败重试、断点续传、成本统计
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("[ERROR] pandas not installed. Run: pip install pandas openpyxl", file=sys.stderr)
    sys.exit(1)

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("[WARNING] tomllib/tomli not available, using empty config", file=sys.stderr)
        tomllib = None

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("[WARNING] tqdm not installed, progress bar disabled. Run: pip install tqdm", file=sys.stderr)

# 导入 llm_call 模块
sys.path.insert(0, os.path.dirname(__file__))
try:
    from llm_call import call_llm_search, calculate_cost
except ImportError as e:
    print(f"[ERROR] Failed to import llm_call.py: {e}", file=sys.stderr)
    sys.exit(1)


# ========== 配置加载 ==========

def load_config(path: str = "config.toml") -> Dict[str, Any]:
    """读取配置文件"""
    if not os.path.exists(path):
        return {}
    if tomllib is None:
        return {}
    
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
            return data
    except Exception as e:
        print(f"[WARNING] Failed to load config.toml: {e}", file=sys.stderr)
        return {}


# ========== Excel 处理 ==========

def excel_col_to_num(col: str) -> int:
    """
    将 Excel 列名转换为数字索引（从0开始）
    例如: A -> 0, B -> 1, ..., Z -> 25, AA -> 26
    """
    num = 0
    for char in col.upper():
        num = num * 26 + (ord(char) - ord('A') + 1)
    return num - 1


def parse_rows_range(rows_str: str) -> Tuple[int, int]:
    """
    解析行范围字符串
    
    Args:
        rows_str: 行范围，如 "3-99"
    
    Returns:
        (start_row, end_row)
    """
    rows_str = rows_str.strip()
    
    # 处理 "3-99" 格式
    match = re.match(r'(\d+)-(\d+)', rows_str)
    if match:
        start_row = int(match.group(1))
        end_row = int(match.group(2))
        return start_row, end_row
    
    raise ValueError(f"Invalid rows format: {rows_str}. Use '3-99'")


def read_journal_names_from_excel(
    file_path: Path,
    sheet_name: Any,
    name_column: str,
    start_row: int,
    end_row: int
) -> List[str]:
    """
    从 Excel 文件读取期刊名称列表
    
    Returns:
        期刊名称列表
    """
    # 读取 Excel
    try:
        # 确定读取范围
        skiprows = start_row - 1
        nrows = end_row - start_row + 1
        
        # 读取名称列
        name_col_idx = excel_col_to_num(name_column)
        
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            usecols=[name_col_idx],
            skiprows=skiprows,
            nrows=nrows,
            header=None,
            engine='openpyxl'
        )
        
    except Exception as e:
        print(f"[ERROR] Failed to read Excel: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 处理数据
    journal_names = []
    
    for idx, row in df.iterrows():
        name = row[name_col_idx]
        
        # 跳过空行
        if pd.isna(name):
            continue
        
        name_str = str(name).strip()
        if name_str:
            journal_names.append(name_str)
    
    return journal_names


# ========== 日志管理 ==========

def init_log_file(log_file: Path):
    """初始化搜索日志文件（CSV）"""
    if not log_file.exists():
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'journal_name', 'search_time', 'status', 'results_count',
                'prompt_tokens', 'completion_tokens', 'total_tokens', 'cost',
                'elapsed_time', 'error_type', 'error_message', 'results_json'
            ])


def log_search_result(log_file: Path, result: Dict[str, Any]):
    """记录搜索结果到日志"""
    try:
        # 序列化结果为 JSON
        results_json = ""
        if result['status'] == 'success' and result.get('results'):
            results_json = json.dumps(result['results'], ensure_ascii=False)
        
        with open(log_file, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                result['journal_name'],
                result['search_time'],
                result['status'],
                result.get('results_count', 0),
                result.get('prompt_tokens', 0),
                result.get('completion_tokens', 0),
                result.get('total_tokens', 0),
                result.get('cost', 0.0),
                result.get('elapsed_time', 0.0),
                result.get('error_type', ''),
                result.get('error_message', ''),
                results_json
            ])
    except Exception as e:
        print(f"[ERROR] Failed to write log: {e}", file=sys.stderr)


def load_processed_journals(log_file: Path) -> set:
    """从日志文件加载已处理的期刊名称"""
    if not log_file.exists():
        return set()
    
    processed = set()
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['status'] == 'success':
                    processed.add(row['journal_name'])
    except Exception as e:
        print(f"[WARNING] Failed to load processed journals: {e}", file=sys.stderr)
    
    return processed


def load_all_results_from_log(log_file: Path) -> Dict[str, Dict[str, Any]]:
    """
    从日志文件加载所有结果（包括成功和失败的）
    
    Returns:
        字典：{journal_name: result_dict}
    """
    if not log_file.exists():
        return {}
    
    results = {}
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                journal_name = row['journal_name']
                
                # 解析结果
                result = {
                    'journal_name': journal_name,
                    'search_time': row['search_time'],
                    'status': row['status'],
                    'results_count': int(row['results_count']) if row['results_count'] else 0,
                    'prompt_tokens': int(row['prompt_tokens']) if row['prompt_tokens'] else 0,
                    'completion_tokens': int(row['completion_tokens']) if row['completion_tokens'] else 0,
                    'total_tokens': int(row['total_tokens']) if row['total_tokens'] else 0,
                    'cost': float(row['cost']) if row['cost'] else 0.0,
                    'error_type': row.get('error_type', ''),
                    'error_message': row.get('error_message', ''),
                    'results': []
                }
                
                # 解析 JSON 结果
                if row['status'] == 'success' and row.get('results_json'):
                    try:
                        result['results'] = json.loads(row['results_json'])
                    except json.JSONDecodeError:
                        pass
                
                # 保留最新的结果（如果有多次运行）
                results[journal_name] = result
    
    except Exception as e:
        print(f"[WARNING] Failed to load results from log: {e}", file=sys.stderr)
    
    return results


# ========== 搜索处理 ==========

def process_journal(
    journal_name: str,
    config: Dict[str, Any],
    retry_times: int,
    retry_delay: int,
    llm_logger: logging.Logger
) -> Dict[str, Any]:
    """
    处理单个期刊的搜索
    
    Args:
        journal_name: 期刊名称
        config: 配置字典
        retry_times: 重试次数
        retry_delay: 重试延迟（秒）
        llm_logger: LLM 交互日志对象
    
    Returns:
        处理结果字典
    """
    result = {
        'journal_name': journal_name,
        'search_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'failed',
        'results_count': 0,
        'results': [],
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'total_tokens': 0,
        'cost': 0.0,
        'elapsed_time': 0.0,
        'error_type': '',
        'error_message': ''
    }
    
    # 获取配置（优先级：llm.search > llm > 环境变量）
    llm_config = config.get('llm', {})
    search_config = config.get('llm', {}).get('search', {})
    
    # API 配置（search 可覆盖 llm 通用配置）
    api_key = search_config.get('api_key') or llm_config.get('api_key') or os.environ.get('OPENAI_API_KEY')
    api_base = search_config.get('api_base') or llm_config.get('api_base') or os.environ.get('OPENAI_API_BASE')
    
    # 搜索专用配置
    model_id = search_config.get('model_id', 'qwen-plus')
    timeout = search_config.get('timeout', 120)
    price_input = search_config.get('price_per_1m_input_tokens', 2.75)
    price_output = search_config.get('price_per_1m_output_tokens', 22.0)
    
    if not api_key:
        result['error_type'] = 'config_error'
        result['error_message'] = 'API key not configured'
        return result
    
    # 重试逻辑
    last_error_type = None
    last_error_msg = None
    
    for attempt in range(retry_times):
        try:
            success, results, usage, usage_source, elapsed_time, error_type, error_msg = call_llm_search(
                journal_name=journal_name,
                model_id=model_id,
                api_key=api_key,
                api_base=api_base,
                timeout=timeout,
                logger=llm_logger
            )
            
            if success and results:
                # 成功
                result['status'] = 'success'
                result['results_count'] = len(results)
                result['results'] = results
                result['usage_source'] = usage_source  # 记录 token 来源
                result['elapsed_time'] = elapsed_time  # 记录耗时
                
                # 统计 token 使用
                if usage:
                    result['prompt_tokens'] = usage.get('prompt_tokens', 0)
                    result['completion_tokens'] = usage.get('completion_tokens', 0)
                    result['total_tokens'] = usage.get('total_tokens', 0)
                    
                    # 计算成本
                    cost = calculate_cost(usage, price_input, price_output)
                    if cost:
                        result['cost'] = cost
                
                return result
            
            # 失败，记录错误
            last_error_type = error_type
            last_error_msg = error_msg
            
            # 检查是否需要重试
            if error_type in ['rate_limit', 'timeout', 'network_error']:
                if attempt < retry_times - 1:
                    wait_time = retry_delay * (attempt + 1)
                    print(f"\n[RETRY] {journal_name}: {error_type}, 等待 {wait_time} 秒后重试 (第 {attempt + 1}/{retry_times} 次)...", file=sys.stderr)
                    time.sleep(wait_time)
                    continue
            
            # 其他错误，直接失败
            break
        
        except Exception as e:
            last_error_type = 'unknown'
            last_error_msg = str(e)
            
            if attempt < retry_times - 1:
                wait_time = retry_delay * (attempt + 1)
                print(f"\n[RETRY] {journal_name}: 异常 {str(e)}, 等待 {wait_time} 秒后重试 (第 {attempt + 1}/{retry_times} 次)...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                break
    
    # 所有重试都失败
    result['error_type'] = last_error_type or 'unknown'
    result['error_message'] = last_error_msg or 'Unknown error'
    
    return result


# ========== Excel 输出 ==========

def write_output_excel(output_file: Path, results: List[Dict[str, Any]]):
    """
    将结果写入 Excel 文件
    
    Args:
        output_file: 输出文件路径
        results: 结果列表
    """
    rows = []
    
    for result in results:
        journal_name = result['journal_name']
        status = result['status']
        search_time = result.get('search_time', '')
        
        if status == 'success' and result.get('results'):
            # 成功：每个结果项输出一行
            for item in result['results']:
                rows.append({
                    '期刊名称': journal_name,
                    '主办单位': item.get('主办单位', ''),
                    '关键句子': item.get('关键句子', ''),
                    '判断依据': item.get('判断依据', ''),
                    '来源链接': item.get('来源链接', ''),
                    '状态': 'success',
                    '错误信息': '',
                    '处理时间': search_time
                })
        elif status == 'pending':
            # 待处理：输出占位行
            rows.append({
                '期刊名称': journal_name,
                '主办单位': '',
                '关键句子': '',
                '判断依据': '',
                '来源链接': '',
                '状态': 'pending',
                '错误信息': result.get('error_message', '待处理'),
                '处理时间': search_time
            })
        else:
            # 失败：输出一行错误信息
            rows.append({
                '期刊名称': journal_name,
                '主办单位': '',
                '关键句子': '',
                '判断依据': '',
                '来源链接': '',
                '状态': 'failed',
                '错误信息': f"{result.get('error_type', 'unknown')}: {result.get('error_message', '')}",
                '处理时间': search_time
            })
    
    # 写入 Excel
    df = pd.DataFrame(rows)
    df.to_excel(output_file, index=False, engine='openpyxl')


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(
        description="批量联网搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python batch_search.py \\
    --input-excel journals.xlsx \\
    --name-column A \\
    --rows 3-99

  python batch_search.py \\
    --input-excel journals.xlsx \\
    --name-column A \\
    --rows 3-99 \\
    --parallel 5
        """
    )
    
    parser.add_argument(
        '--input-excel',
        required=True,
        help='Excel 文件路径'
    )
    parser.add_argument(
        '--sheet-name',
        default=0,
        help='Sheet 名称或索引（默认 0，即第一个 sheet）'
    )
    parser.add_argument(
        '--name-column',
        required=True,
        help='期刊名称列，如 "A"'
    )
    parser.add_argument(
        '--rows',
        required=True,
        help='行范围，如 "3-99"'
    )
    parser.add_argument(
        '--parallel',
        type=int,
        default=None,
        help='并行数量（覆盖配置文件）'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config("config.toml")
    
    # 获取配置参数（优先级：llm.search > llm > 默认值）
    llm_config = config.get('llm', {})
    search_config = config.get('llm', {}).get('search', {})
    
    # API 配置（search 可覆盖 llm 通用配置）
    api_base = search_config.get('api_base') or llm_config.get('api_base', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    
    # 搜索专用配置
    parallel = args.parallel if args.parallel is not None else search_config.get('parallel', 10)
    retry_times = search_config.get('retry_times', 3)
    retry_delay = search_config.get('retry_delay', 5)
    timeout = search_config.get('timeout', 120)
    model_id = search_config.get('model_id', 'qwen-plus')
    price_input = search_config.get('price_per_1m_input_tokens', 2.75)
    price_output = search_config.get('price_per_1m_output_tokens', 22.0)
    
    # 生成日志文件名（带模型名称和时间戳）
    timestamp = datetime.now().strftime("%y%m%d.%H%M%S")
    llm_log_file = Path(f"batch_search-{model_id}-{timestamp}.log")
    
    # 配置 LLM 交互日志
    llm_logger = logging.getLogger('llm_interactions')
    llm_logger.setLevel(logging.INFO)
    llm_handler = logging.FileHandler(llm_log_file, encoding='utf-8')
    llm_handler.setFormatter(logging.Formatter('%(message)s'))
    llm_logger.addHandler(llm_handler)
    llm_logger.propagate = False  # 不传播到根 logger
    
    # 解析参数
    try:
        # 处理 sheet_name（可能是数字或字符串）
        sheet_name = args.sheet_name
        try:
            sheet_name = int(sheet_name)
        except (ValueError, TypeError):
            pass
        
        # 解析行范围
        start_row, end_row = parse_rows_range(args.rows)
        
    except Exception as e:
        print(f"[ERROR] Invalid arguments: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 打印关键参数
    print("=" * 60)
    print("[CONFIG] 批量联网搜索工具 - 启动参数")
    print("=" * 60)
    print(f"Excel 文件:        {args.input_excel}")
    print(f"Sheet 名称:        {args.sheet_name}")
    print(f"期刊名称列:        {args.name_column}")
    print(f"行范围:            {args.rows}")
    print(f"并行数量:          {parallel}")
    print(f"模型 ID:           {model_id}")
    print(f"API Base:          {api_base}")
    print(f"重试次数:          {retry_times}")
    print(f"重试延迟:          {retry_delay} 秒")
    print(f"请求超时:          {timeout} 秒")
    print(f"Token 价格:        输入 ${price_input}/1M, 输出 ${price_output}/1M")
    print(f"日志文件:          {llm_log_file}")
    print(f"配置文件:          config.toml")
    print("=" * 60)
    print()
    
    # 检查 Excel 文件
    excel_path = Path(args.input_excel)
    if not excel_path.exists():
        print(f"[ERROR] Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)
    
    # 读取期刊名称
    print(f"[SEARCH] 读取 Excel 文件...")
    
    try:
        journal_names = read_journal_names_from_excel(
            excel_path,
            sheet_name,
            args.name_column,
            start_row,
            end_row
        )
    except Exception as e:
        print(f"[ERROR] Failed to read Excel: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[SEARCH] 读取到 {len(journal_names)} 个期刊名称")
    
    if not journal_names:
        print("[WARNING] No journal names found", file=sys.stderr)
        sys.exit(0)
    
    # 初始化日志
    search_log_file = excel_path.parent / f"{excel_path.name}-search-log.csv"
    init_log_file(search_log_file)
    
    # 加载已处理的期刊
    processed_journals = load_processed_journals(search_log_file)
    
    # 过滤待处理的期刊
    pending_journals = [name for name in journal_names if name not in processed_journals]
    
    if processed_journals:
        print(f"[SEARCH] 跳过 {len(processed_journals)} 个已处理的期刊")
    
    if not pending_journals:
        print("[INFO] 所有期刊已完成搜索，生成完整 Excel...")
        
        # 生成完整 Excel（即使没有新的处理）
        output_file = excel_path.parent / f"{excel_path.name}-output-{model_id}-{timestamp}.xlsx"
        historical_results = load_all_results_from_log(search_log_file)
        
        complete_results = []
        for journal_name in journal_names:
            if journal_name in historical_results:
                complete_results.append(historical_results[journal_name])
            else:
                complete_results.append({
                    'journal_name': journal_name,
                    'search_time': '',
                    'status': 'pending',
                    'results_count': 0,
                    'results': [],
                    'error_type': '',
                    'error_message': '待处理'
                })
        
        write_output_excel(output_file, complete_results)
        
        total_in_excel = len(complete_results)
        success_in_excel = sum(1 for r in complete_results if r['status'] == 'success')
        failed_in_excel = sum(1 for r in complete_results if r['status'] == 'failed')
        pending_in_excel = sum(1 for r in complete_results if r['status'] == 'pending')
        
        print(f"[OK] 输出文件已保存: {output_file}")
        print(f"[OK] Excel 包含 {total_in_excel} 个期刊: 成功 {success_in_excel}, 失败 {failed_in_excel}, 待处理 {pending_in_excel}")
        sys.exit(0)
    
    print(f"[SEARCH] 开始处理 {len(pending_journals)} 个期刊，并行数={parallel}")
    print()
    
    # 并行处理
    all_results = []
    success_count = 0
    failed_count = 0
    
    # Token 和时间统计
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_cost = 0.0
    total_elapsed_time = 0.0
    
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        # 提交任务
        future_to_journal = {
            executor.submit(
                process_journal,
                journal_name,
                config,
                retry_times,
                retry_delay,
                llm_logger
            ): journal_name
            for journal_name in pending_journals
        }
        
        # 使用进度条
        if TQDM_AVAILABLE:
            progress = tqdm(total=len(pending_journals), desc="[PROGRESS]", unit="期刊")
        
        # 处理完成的任务
        for future in as_completed(future_to_journal):
            journal_name = future_to_journal[future]
            
            try:
                result = future.result()
                
                # 记录日志
                log_search_result(search_log_file, result)
                
                # 保存结果
                all_results.append(result)
                
                # 统计
                if result['status'] == 'success':
                    success_count += 1
                    results_count = result.get('results_count', 0)
                    
                    # 累加 token 和时间统计
                    total_prompt_tokens += result.get('prompt_tokens', 0)
                    total_completion_tokens += result.get('completion_tokens', 0)
                    total_tokens += result.get('total_tokens', 0)
                    total_cost += result.get('cost', 0.0)
                    total_elapsed_time += result.get('elapsed_time', 0.0)
                    
                    # 打印成功信息
                    elapsed = result.get('elapsed_time', 0.0)
                    cost_str = f", 成本: ${result['cost']:.4f}" if result.get('cost', 0) > 0 else ""
                    
                    # Token 来源标注
                    usage_source = result.get('usage_source', 'none')
                    if usage_source == 'api':
                        token_source_label = "API返回"
                    else:
                        token_source_label = "无统计"
                    
                    token_str = f", tokens: {result.get('total_tokens', 0)} ({token_source_label})" if result.get('total_tokens', 0) > 0 else f" (Token: {token_source_label})"
                    time_str = f", 耗时: {elapsed:.2f}秒"
                    print(f"[SUCCESS] {journal_name}: 提取 {results_count} 条结果{token_str}{cost_str}{time_str}")
                else:
                    failed_count += 1
                    print(f"[FAILED] {journal_name}: {result.get('error_type', 'unknown')}")
                
                # 更新进度
                if TQDM_AVAILABLE:
                    progress.update(1)
                    progress.set_postfix(成功=success_count, 失败=failed_count)
            
            except Exception as e:
                print(f"\n[ERROR] Exception processing {journal_name}: {e}", file=sys.stderr)
                failed_count += 1
                
                # 记录异常到日志
                log_search_result(search_log_file, {
                    'journal_name': journal_name,
                    'search_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'status': 'failed',
                    'results_count': 0,
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'cost': 0.0,
                    'elapsed_time': 0.0,
                    'error_type': 'unknown',
                    'error_message': str(e)[:200]
                })
                
                if TQDM_AVAILABLE:
                    progress.update(1)
        
        if TQDM_AVAILABLE:
            progress.close()
    
    # 输出 Excel - 合并历史结果和当前结果
    print(f"\n[OUTPUT] 生成输出文件...")
    output_file = excel_path.parent / f"{excel_path.name}-output-{model_id}-{timestamp}.xlsx"
    
    try:
        # 从日志加载所有历史结果
        historical_results = load_all_results_from_log(search_log_file)
        
        # 合并当前运行的结果（覆盖历史结果）
        for result in all_results:
            historical_results[result['journal_name']] = result
        
        # 按照输入期刊名称的顺序生成完整结果列表
        complete_results = []
        for journal_name in journal_names:
            if journal_name in historical_results:
                complete_results.append(historical_results[journal_name])
            else:
                # 如果日志中也没有，创建一个"待处理"的占位条目
                complete_results.append({
                    'journal_name': journal_name,
                    'search_time': '',
                    'status': 'pending',
                    'results_count': 0,
                    'results': [],
                    'error_type': '',
                    'error_message': '待处理'
                })
        
        write_output_excel(output_file, complete_results)
        
        # 统计完整结果
        total_in_excel = len(complete_results)
        success_in_excel = sum(1 for r in complete_results if r['status'] == 'success')
        failed_in_excel = sum(1 for r in complete_results if r['status'] == 'failed')
        pending_in_excel = sum(1 for r in complete_results if r['status'] == 'pending')
        
        print(f"[OK] 输出文件已保存: {output_file}")
        print(f"[OK] Excel 包含 {total_in_excel} 个期刊: 成功 {success_in_excel}, 失败 {failed_in_excel}, 待处理 {pending_in_excel}")
    except Exception as e:
        print(f"[ERROR] Failed to write output Excel: {e}", file=sys.stderr)
    
    # 输出统计
    print(f"\n[OK] 全部完成")
    print(f"     成功: {success_count}")
    print(f"     失败: {failed_count}")
    
    if total_tokens > 0:
        print(f"     总 tokens: 输入 {total_prompt_tokens:,}, 输出 {total_completion_tokens:,}, 总计 {total_tokens:,} (来自API返回)")
    
    if total_cost > 0:
        print(f"     总成本: ${total_cost:.2f}")
    
    if total_elapsed_time > 0:
        avg_time = total_elapsed_time / success_count if success_count > 0 else 0
        print(f"     总耗时: {total_elapsed_time:.2f}秒 (平均: {avg_time:.2f}秒/请求)")
    
    print(f"     输出文件: {output_file}")
    print(f"     日志文件: {llm_log_file}")
    print(f"     续传日志: {search_log_file}")


if __name__ == "__main__":
    main()
