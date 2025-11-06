#!/usr/bin/env python3
"""
批量信息提取工具 - batch_extract.py

从 Excel 文件读取URL列表，批量提取期刊主办单位信息
支持并行处理、失败重试、断点续传
"""

import argparse
import csv
import hashlib
import json
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
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False
    print("[ERROR] markitdown not installed. Run: pip install markitdown", file=sys.stderr)
    sys.exit(1)

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("[WARNING] tqdm not installed, progress bar disabled. Run: pip install tqdm", file=sys.stderr)

# 导入 extract.py 的核心函数
sys.path.insert(0, os.path.dirname(__file__))
try:
    from extract import extract_with_langextract, extract_with_regexp, LANGEXTRACT_AVAILABLE
except ImportError as e:
    print(f"[ERROR] Failed to import extract.py: {e}", file=sys.stderr)
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


# ========== URL 处理 ==========

def sha1_hex(text: str) -> str:
    """计算字符串的 SHA1 hash"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def excel_col_to_num(col: str) -> int:
    """
    将 Excel 列名转换为数字索引（从0开始）
    例如: A -> 0, B -> 1, ..., Z -> 25, AA -> 26
    """
    num = 0
    for char in col.upper():
        num = num * 26 + (ord(char) - ord('A') + 1)
    return num - 1


def parse_rows_range(rows_str: str) -> Tuple[int, Optional[int]]:
    """
    解析行范围字符串
    
    Args:
        rows_str: 行范围，如 "4+" 或 "4-99"
    
    Returns:
        (start_row, end_row)
        - "4+" -> (4, None) 表示从第4行开始，直到空行
        - "4-99" -> (4, 99) 表示第4行到第99行
    """
    rows_str = rows_str.strip()
    
    # 处理 "4+" 格式
    if rows_str.endswith('+'):
        start_row = int(rows_str[:-1])
        return start_row, None
    
    # 处理 "4-99" 格式
    match = re.match(r'(\d+)-(\d+)', rows_str)
    if match:
        start_row = int(match.group(1))
        end_row = int(match.group(2))
        return start_row, end_row
    
    raise ValueError(f"Invalid rows format: {rows_str}. Use '4+' or '4-99'")


def read_urls_from_excel(
    file_path: Path,
    sheet_name: Any,
    name_column: str,
    url_columns: List[str],
    start_row: int,
    end_row: Optional[int]
) -> Tuple[List[str], int]:
    """
    从 Excel 文件读取 URL 列表
    
    Returns:
        (urls, actual_end_row)
    """
    # 读取 Excel
    try:
        # 确定读取范围
        skiprows = start_row - 1
        
        if end_row is not None:
            nrows = end_row - start_row + 1
        else:
            nrows = None  # 读取到最后
        
        # 读取所有相关列
        name_col_idx = excel_col_to_num(name_column)
        url_col_indices = [excel_col_to_num(col) for col in url_columns]
        all_col_indices = [name_col_idx] + url_col_indices
        
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            usecols=all_col_indices,
            skiprows=skiprows,
            nrows=nrows,
            header=None,
            engine='openpyxl'
        )
        
    except Exception as e:
        print(f"[ERROR] Failed to read Excel: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 处理数据
    all_urls = []
    actual_end_row = start_row - 1
    
    for idx, row in df.iterrows():
        name = row[name_col_idx]
        
        # 如果是 "4+" 格式，遇到空行停止
        if end_row is None and pd.isna(name):
            break
        
        # 跳过空行
        if pd.isna(name):
            continue
        
        actual_end_row = start_row + idx
        
        # 提取所有 URL
        for col_idx in url_col_indices:
            url = row[col_idx]
            if pd.notna(url):
                url_str = str(url).strip()
                # 过滤无效 URL
                if url_str.startswith('http://') or url_str.startswith('https://'):
                    all_urls.append(url_str)
    
    # 去重并保持顺序
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls, actual_end_row


# ========== 目录和文件处理 ==========

def get_hash_path(snapshot_dir: Path, url_hash: str) -> Path:
    """获取 hash 分层目录路径"""
    return snapshot_dir / url_hash[:2] / url_hash[2:4] / url_hash[4:]


def get_url_hash_dirs(snapshot_dir: Path, urls: List[str], extract_method: str = 'auto', force: bool = False) -> List[Tuple[str, Path, str]]:
    """
    根据 URL 列表获取对应的 hash 目录
    
    Args:
        snapshot_dir: 快照目录
        urls: URL 列表
        extract_method: 提取方法 ('langextract', 'regexp', 'auto')
        force: 是否强制重新提取
    
    Returns:
        List[(url, hash_dir, status)]
        status: 'ready' / 'no_snapshot' / 'already_extracted'
    """
    url_info = []
    
    for url in urls:
        url_hash = sha1_hex(url)
        hash_path = get_hash_path(snapshot_dir, url_hash)
        dom_file = hash_path / "dom.html"
        
        # 根据 extract_method 确定需要检查的文件
        if extract_method == 'langextract':
            json_file = hash_path / "host-langextract.json"
        elif extract_method == 'regexp':
            json_file = hash_path / "host-regexp.json"
        else:  # auto
            # auto 模式下，任意一个文件存在就算已提取
            langextract_file = hash_path / "host-langextract.json"
            regexp_file = hash_path / "host-regexp.json"
            json_file = langextract_file if langextract_file.exists() else (regexp_file if regexp_file.exists() else None)
        
        if not dom_file.exists():
            # 快照不存在
            url_info.append((url, hash_path, 'no_snapshot'))
        elif not force and (json_file is not None if extract_method == 'auto' else json_file.exists()):
            # 已提取（除非 force=True）
            url_info.append((url, hash_path, 'already_extracted'))
        else:
            # 准备提取
            url_info.append((url, hash_path, 'ready'))
    
    return url_info


# ========== 日志管理 ==========

def init_log_file(log_file: Path):
    """初始化提取日志文件"""
    if not log_file.exists():
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['hash', 'url', 'snapshot_time', 'extract_time', 
                           'status', 'institutions_count', 'extract_method', 'error_type', 'error_message'])


def log_result(log_file: Path, result: Dict[str, Any]):
    """记录提取结果到日志"""
    try:
        with open(log_file, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                result['hash'],
                result.get('url', ''),
                result.get('snapshot_time', ''),
                result.get('extract_time', ''),
                result['status'],
                result.get('institutions_count', 0),
                result.get('extract_method', ''),
                result.get('error_type', ''),
                result.get('error_message', '')
            ])
    except Exception as e:
        print(f"[ERROR] Failed to write log: {e}", file=sys.stderr)


# ========== 提取处理 ==========

def convert_html_to_markdown(html_file: Path, md_file: Path) -> bool:
    """
    使用 markitdown 将 HTML 转换为 Markdown
    
    Returns:
        是否成功
    """
    try:
        md = MarkItDown()
        result = md.convert(str(html_file))
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(result.text_content)
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to convert HTML to Markdown: {e}", file=sys.stderr)
        return False


def extract_institutions(md_file: Path, json_file: Path, config: Dict[str, Any], extract_method: str = 'auto', retry_times: int = 3, retry_delay: int = 5) -> Dict[str, Any]:
    """
    从 Markdown 文件提取主办单位信息
    
    Args:
        md_file: Markdown 输入文件
        json_file: JSON 输出文件
        config: 配置字典
        extract_method: 提取方法 ('langextract', 'regexp', 'auto')
        retry_times: 重试次数（用于 API 频率限制）
        retry_delay: 重试延迟（秒）
    
    Returns:
        提取结果字典（包含 success, institutions_count, extract_method, error_type, error_message）
    """
    result = {
        'success': False,
        'institutions_count': 0,
        'extract_method': '',
        'error_type': '',
        'error_message': ''
    }
    
    try:
        # 读取 Markdown 文件
        text = md_file.read_text(encoding='utf-8')
        
        # 获取 API 配置
        extract_config = config.get('extract', {})
        api_config = config.get('api', {})
        
        model_id = extract_config.get('model_id', 'gpt-4o-mini')
        api_key = api_config.get('api_key') or os.environ.get('OPENAI_API_KEY') or os.environ.get('LANGEXTRACT_API_KEY')
        api_base = api_config.get('api_base') or os.environ.get('OPENAI_API_BASE')
        
        # 根据 extract_method 决定提取策略
        institutions = []
        actual_method = None
        
        if extract_method == 'regexp':
            # 仅使用 regexp
            institutions = extract_with_regexp(text)
            actual_method = 'regexp'
            
        elif extract_method == 'langextract':
            # 仅使用 langextract（带重试）
            if not LANGEXTRACT_AVAILABLE:
                result['error_type'] = 'config_error'
                result['error_message'] = 'LangExtract not available'
                return result
            
            if not api_key:
                result['error_type'] = 'config_error'
                result['error_message'] = 'API key not configured'
                return result
            
            # 重试逻辑
            last_error = None
            for attempt in range(retry_times):
                try:
                    institutions = extract_with_langextract(
                        text,
                        model_id=model_id,
                        api_key=api_key,
                        api_base=api_base
                    )
                    actual_method = 'langextract'
                    break  # 成功则跳出重试循环
                except Exception as e:
                    last_error = e
                    error_msg = str(e)
                    
                    # 检查是否是频率限制
                    if 'rate' in error_msg.lower() or 'limit' in error_msg.lower() or '429' in error_msg:
                        if attempt < retry_times - 1:
                            wait_time = retry_delay * (attempt + 1)
                            print(f"\n[RATE LIMIT] API 频率限制，等待 {wait_time} 秒后重试 (第 {attempt + 1}/{retry_times} 次)...", file=sys.stderr)
                            time.sleep(wait_time)
                            continue
                        else:
                            result['error_type'] = 'rate_limit'
                            result['error_message'] = error_msg
                            print(f"\n[ERROR] API 频率限制，{retry_times} 次重试均失败", file=sys.stderr)
                            raise
                    else:
                        # 非频率限制错误，直接失败
                        result['error_type'] = 'api_error'
                        result['error_message'] = error_msg
                        raise
                    
        else:  # auto
            # 优先使用 LangExtract（带重试），全部失败后回退到 regexp
            langextract_failed = False
            if LANGEXTRACT_AVAILABLE and api_key:
                last_error = None
                for attempt in range(retry_times):
                    try:
                        institutions = extract_with_langextract(
                            text,
                            model_id=model_id,
                            api_key=api_key,
                            api_base=api_base
                        )
                        if institutions:
                            actual_method = 'langextract'
                            break  # 成功则跳出重试循环
                    except Exception as e:
                        last_error = e
                        error_msg = str(e)
                        
                        # 检查是否是频率限制
                        if 'rate' in error_msg.lower() or 'limit' in error_msg.lower() or '429' in error_msg:
                            if attempt < retry_times - 1:
                                wait_time = retry_delay * (attempt + 1)
                                print(f"\n[RATE LIMIT] API 频率限制，等待 {wait_time} 秒后重试 (第 {attempt + 1}/{retry_times} 次)...", file=sys.stderr)
                                time.sleep(wait_time)
                                continue
                            else:
                                # 所有重试都失败
                                print(f"\n[WARNING] LangExtract {retry_times} 次重试均失败: {error_msg}", file=sys.stderr)
                                print(f"[INFO] 回退到 regexp 方法", file=sys.stderr)
                                langextract_failed = True
                                break
                        else:
                            # 非频率限制错误，直接回退
                            print(f"[WARNING] LangExtract 失败: {error_msg}", file=sys.stderr)
                            print(f"[INFO] 回退到 regexp 方法", file=sys.stderr)
                            langextract_failed = True
                            break
            
            # 如果 LangExtract 失败或不可用，回退到 regexp
            if not institutions:
                institutions = extract_with_regexp(text)
                actual_method = 'regexp'
        
        # 保存结果（包含元数据）
        output_data = {
            "extraction_metadata": {
                "method": actual_method,
                "model": model_id if actual_method == 'langextract' else None,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "host_institutions": institutions
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        result['success'] = True
        result['institutions_count'] = len(institutions)
        result['extract_method'] = actual_method
        
        # 打印成功信息
        print(f"[SUCCESS] 提取成功: {len(institutions)} 个机构 -> {json_file.absolute()}", file=sys.stderr)
        
    except Exception as e:
        if not result['error_type']:  # 如果还没有设置错误类型
            result['error_type'] = 'unknown'
            result['error_message'] = str(e)[:200]
    
    return result


def process_url(url: str, hash_dir: Path, config: Dict[str, Any], extract_method: str = 'auto', retry_times: int = 3, retry_delay: int = 5) -> Dict[str, Any]:
    """
    处理单个 URL 的提取
    
    Args:
        url: URL 地址
        hash_dir: Hash 目录路径
        config: 配置字典
        extract_method: 提取方法 ('langextract', 'regexp', 'auto')
        retry_times: 重试次数
        retry_delay: 重试延迟（秒）
    
    Returns:
        处理结果字典
    """
    hash_name = hash_dir.name
    dom_file = hash_dir / "dom.html"
    md_file = hash_dir / "dom.md"
    
    # 根据 extract_method 决定输出文件名
    if extract_method == 'langextract':
        json_file = hash_dir / "host-langextract.json"
    elif extract_method == 'regexp':
        json_file = hash_dir / "host-regexp.json"
    else:  # auto
        # auto 模式下，先尝试 langextract，成功则保存到 host-langextract.json
        # 失败回退到 regexp，保存到 host-regexp.json
        # 这里先设置为 None，后面根据实际方法决定
        json_file = None
    
    result = {
        'hash': hash_name,
        'url': url,
        'extract_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'failed',
        'institutions_count': 0,
        'extract_method': '',
        'error_type': '',
        'error_message': ''
    }
    
    # 获取快照时间（从文件修改时间）
    try:
        snapshot_time = datetime.fromtimestamp(dom_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        result['snapshot_time'] = snapshot_time
    except:
        pass
    
    # 检查 dom.html 是否存在
    if not dom_file.exists():
        result['error_type'] = 'file_not_found'
        result['error_message'] = 'dom.html not found'
        return result
    
    # 转换 HTML 到 Markdown（如果不存在）
    if not md_file.exists():
        if not convert_html_to_markdown(dom_file, md_file):
            result['error_type'] = 'conversion_error'
            result['error_message'] = 'Failed to convert HTML to Markdown'
            return result
    
    # 提取信息（重试逻辑在 extract_institutions 内部）
    try:
        # 对于 auto 模式，先用临时文件名
        temp_json_file = json_file or hash_dir / "temp.json"
        
        extract_result = extract_institutions(
            md_file, 
            temp_json_file, 
            config, 
            extract_method,
            retry_times,
            retry_delay
        )
        
        if extract_result['success']:
            # 对于 auto 模式，根据实际方法决定最终文件名
            if extract_method == 'auto':
                actual_method = extract_result.get('extract_method', 'regexp')
                if actual_method == 'langextract':
                    final_json_file = hash_dir / "host-langextract.json"
                else:
                    final_json_file = hash_dir / "host-regexp.json"
                
                # 重命名临时文件到最终文件名
                if temp_json_file.exists() and temp_json_file != final_json_file:
                    temp_json_file.rename(final_json_file)
                    # 更新成功打印信息显示的路径
                    print(f"[INFO] 文件已保存到: {final_json_file.absolute()}", file=sys.stderr)
            
            result['status'] = 'success'
            result['institutions_count'] = extract_result['institutions_count']
            result['extract_method'] = extract_result.get('extract_method', extract_method)
            return result
        else:
            # 提取失败
            result['error_type'] = extract_result['error_type']
            result['error_message'] = extract_result['error_message']
            result['extract_method'] = extract_result.get('extract_method', extract_method)
            return result
    
    except Exception as e:
        result['error_type'] = 'unknown'
        result['error_message'] = str(e)[:200]
        return result


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(
        description="批量信息提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python batch_extract.py \\
    --url-excel journals.xlsx \\
    --name-column A \\
    --url-columns D,F \\
    --rows 4+

  python batch_extract.py \\
    --url-excel journals.xlsx \\
    --name-column A \\
    --url-columns D \\
    --rows 4-99 \\
    --parallel 3
        """
    )
    
    parser.add_argument(
        '--url-excel',
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
        '--url-columns',
        required=True,
        help='URL 列（多列用逗号分隔），如 "D,F"'
    )
    parser.add_argument(
        '--rows',
        required=True,
        help='行范围，如 "4+" 或 "4-99"'
    )
    parser.add_argument(
        '--parallel',
        type=int,
        default=None,
        help='并行数量（覆盖配置文件）'
    )
    parser.add_argument(
        '--model-id',
        default=None,
        help='LangExtract 模型 ID（覆盖配置文件）'
    )
    parser.add_argument(
        '--api-base',
        default=None,
        help='API 接口地址'
    )
    parser.add_argument(
        '--api-key',
        default=None,
        help='API Key'
    )
    parser.add_argument(
        '--extract-method',
        choices=['langextract', 'regexp', 'auto'],
        default='auto',
        help='提取方法：langextract（仅 AI）、regexp（仅规则）、auto（AI 优先，失败回退规则）（默认: auto）'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='强制重新提取（忽略已存在的结果文件）'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config("config.toml")
    
    # 命令行参数覆盖配置文件
    extract_config = config.get('extract', {})
    api_config = config.get('api', {})
    
    if args.model_id:
        extract_config['model_id'] = args.model_id
    if args.api_base:
        api_config['api_base'] = args.api_base
    if args.api_key:
        api_config['api_key'] = args.api_key
    
    config['extract'] = extract_config
    config['api'] = api_config
    
    parallel = args.parallel if args.parallel is not None else extract_config.get('parallel', 2)
    retry_times = extract_config.get('retry_times', 3)
    retry_delay = extract_config.get('retry_delay', 5)
    
    # 解析参数
    try:
        # 处理 sheet_name（可能是数字或字符串）
        sheet_name = args.sheet_name
        try:
            sheet_name = int(sheet_name)
        except (ValueError, TypeError):
            pass
        
        # 解析 URL 列
        url_columns = [col.strip() for col in args.url_columns.split(',')]
        
        # 解析行范围
        start_row, end_row = parse_rows_range(args.rows)
        
    except Exception as e:
        print(f"[ERROR] Invalid arguments: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 打印关键参数（排错用）
    print("=" * 60)
    print("[CONFIG] 批量信息提取工具 - 启动参数")
    print("=" * 60)
    print(f"Excel 文件:    {args.url_excel}")
    print(f"Sheet 名称:    {args.sheet_name}")
    print(f"期刊名称列:    {args.name_column}")
    print(f"URL 列:        {args.url_columns}")
    print(f"行范围:        {args.rows}")
    print(f"提取方法:      {args.extract_method}")
    print(f"强制重提取:    {'是' if args.force else '否'}")
    print(f"并行数量:      {parallel}")
    print(f"模型 ID:       {extract_config.get('model_id', 'gpt-4o-mini')}")
    print(f"API Base:      {api_config.get('api_base', 'from env')}")
    print(f"重试次数:      {retry_times}")
    print(f"重试延迟:      {retry_delay} 秒")
    print(f"配置文件:      config.toml")
    print("=" * 60)
    print()
    
    # 检查 Excel 文件
    excel_path = Path(args.url_excel)
    if not excel_path.exists():
        print(f"[ERROR] Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)
    
    # 确定快照目录
    snapshot_dir = excel_path.parent / f"{excel_path.stem}-snapshot"
    if not snapshot_dir.exists():
        print(f"[ERROR] Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[INFO] 快照目录: {snapshot_dir}")
    
    # 读取 URL
    print(f"[EXTRACT] 读取 Excel 文件...")
    
    try:
        urls, actual_end_row = read_urls_from_excel(
            excel_path,
            sheet_name,
            args.name_column,
            url_columns,
            start_row,
            end_row
        )
        
        # 打印实际读取范围
        if end_row is None:
            print(f"[INFO] 实际读取行范围: {start_row}-{actual_end_row}")
        
    except Exception as e:
        print(f"[ERROR] Failed to read Excel: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[EXTRACT] 读取到 {len(urls)} 个 URL（去重后）")
    
    if not urls:
        print("[WARNING] No URLs found", file=sys.stderr)
        sys.exit(0)
    
    # 获取 URL 对应的 hash 目录和状态
    print(f"[EXTRACT] 检查快照状态...")
    url_info = get_url_hash_dirs(snapshot_dir, urls, args.extract_method, args.force)
    
    # 统计各种状态
    ready_urls = [(url, path) for url, path, status in url_info if status == 'ready']
    already_extracted = [(url, path) for url, path, status in url_info if status == 'already_extracted']
    no_snapshot = [(url, path) for url, path, status in url_info if status == 'no_snapshot']
    
    print(f"[EXTRACT] 跳过 {len(already_extracted)} 个已提取的 URL")
    print(f"[EXTRACT] 跳过 {len(no_snapshot)} 个无快照的 URL")
    
    if no_snapshot:
        for url, _ in no_snapshot[:5]:  # 只显示前5个
            print(f"[WARNING] 无快照: {url}")
        if len(no_snapshot) > 5:
            print(f"[WARNING] ... 还有 {len(no_snapshot) - 5} 个无快照的 URL")
    
    if not ready_urls:
        print("[OK] 所有 URL 已完成提取")
        sys.exit(0)
    
    print(f"[EXTRACT] 开始处理 {len(ready_urls)} 个 URL，并行数={parallel}")
    
    # 初始化日志
    log_file = snapshot_dir / "extract-log.csv"
    init_log_file(log_file)
    
    # 并行处理
    success_count = 0
    failed_count = 0
    method_stats = {'langextract': 0, 'regexp': 0}  # 统计各方法的使用次数
    
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        # 提交任务
        future_to_url = {
            executor.submit(process_url, url, hash_dir, config, args.extract_method, retry_times, retry_delay): (url, hash_dir)
            for url, hash_dir in ready_urls
        }
        
        # 使用进度条
        if TQDM_AVAILABLE:
            progress = tqdm(total=len(ready_urls), desc="[PROGRESS]", unit="url")
        
        # 处理完成的任务
        for future in as_completed(future_to_url):
            url, hash_dir = future_to_url[future]
            
            try:
                result = future.result()
                
                # 记录日志
                log_result(log_file, result)
                
                # 统计
                if result['status'] == 'success':
                    success_count += 1
                    # 统计方法使用次数
                    method = result.get('extract_method', '')
                    if method in method_stats:
                        method_stats[method] += 1
                else:
                    failed_count += 1
                    print(f"\n[FAILED] {url}: {result.get('error_type', 'unknown')}")
                
                # 更新进度
                if TQDM_AVAILABLE:
                    progress.update(1)
            
            except Exception as e:
                print(f"\n[ERROR] Exception processing {url}: {e}", file=sys.stderr)
                failed_count += 1
                
                # 记录异常到日志
                log_result(log_file, {
                    'hash': hash_dir.name,
                    'url': url,
                    'extract_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'status': 'failed',
                    'extract_method': '',
                    'error_type': 'unknown',
                    'error_message': str(e)[:200]
                })
                
                if TQDM_AVAILABLE:
                    progress.update(1)
        
        if TQDM_AVAILABLE:
            progress.close()
    
    # 输出统计
    print(f"\n[OK] 提取完成")
    if args.extract_method == 'auto' and success_count > 0:
        # auto 模式下显示方法统计
        method_detail = f"langextract: {method_stats['langextract']}, regexp: {method_stats['regexp']}"
        print(f"     成功: {success_count} ({method_detail})")
    else:
        print(f"     成功: {success_count}")
    print(f"     失败: {failed_count}")
    print(f"     跳过: {len(already_extracted) + len(no_snapshot)} (已提取: {len(already_extracted)}, 无快照: {len(no_snapshot)})")
    print(f"     日志: {log_file}")


if __name__ == "__main__":
    main()
