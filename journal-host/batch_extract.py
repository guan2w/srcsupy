#!/usr/bin/env python3
"""
批量信息提取工具 - batch_extract.py

从快照目录批量提取期刊主办单位信息
支持并行处理、失败重试、持续监听模式
"""

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


# ========== 目录扫描 ==========

def find_snapshot_dirs(snapshot_dir: Path) -> List[Path]:
    """
    扫描快照目录，找到包含 dom.html 但没有 host.json 的目录
    
    Returns:
        待提取的目录列表
    """
    targets = []
    
    # 遍历 hash 分层目录结构: ab/cd/abcdef.../
    for level1 in snapshot_dir.iterdir():
        if not level1.is_dir() or len(level1.name) != 2:
            continue
        
        for level2 in level1.iterdir():
            if not level2.is_dir() or len(level2.name) != 2:
                continue
            
            for hash_dir in level2.iterdir():
                if not hash_dir.is_dir():
                    continue
                
                dom_file = hash_dir / "dom.html"
                json_file = hash_dir / "host.json"
                
                # 如果有 dom.html 但没有 host.json，则需要提取
                if dom_file.exists() and not json_file.exists():
                    targets.append(hash_dir)
    
    return targets


def get_snapshot_dir(input_path: str) -> Path:
    """
    根据输入确定快照目录
    
    Args:
        input_path: Excel 文件路径 或 快照目录路径
    
    Returns:
        快照目录的 Path 对象
    """
    input_p = Path(input_path)
    
    if input_p.is_dir():
        # 直接是目录
        return input_p
    elif input_p.suffix == '.xlsx':
        # Excel 文件，推导快照目录
        snapshot_dir = input_p.parent / f"{input_p.stem}-snapshot"
        if not snapshot_dir.exists():
            print(f"[ERROR] Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
            sys.exit(1)
        return snapshot_dir
    else:
        print(f"[ERROR] Invalid input: {input_path}", file=sys.stderr)
        sys.exit(1)


# ========== 日志管理 ==========

def init_log_file(log_file: Path):
    """初始化提取日志文件"""
    if not log_file.exists():
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['hash', 'dom_path', 'snapshot_time', 'extract_time', 
                           'status', 'institutions_count', 'error_type', 'error_message'])


def log_result(log_file: Path, result: Dict[str, Any]):
    """记录提取结果到日志"""
    try:
        with open(log_file, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                result['hash'],
                result.get('dom_path', ''),
                result.get('snapshot_time', ''),
                result.get('extract_time', ''),
                result['status'],
                result.get('institutions_count', 0),
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


def extract_institutions(md_file: Path, json_file: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 Markdown 文件提取主办单位信息
    
    Returns:
        提取结果字典
    """
    result = {
        'success': False,
        'institutions_count': 0,
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
        
        # 尝试使用 LangExtract
        institutions = []
        if LANGEXTRACT_AVAILABLE and api_key:
            try:
                institutions = extract_with_langextract(
                    text,
                    model_id=model_id,
                    api_key=api_key,
                    api_base=api_base
                )
            except Exception as e:
                error_msg = str(e)
                
                # 检查是否是频率限制
                if 'rate' in error_msg.lower() or 'limit' in error_msg.lower():
                    result['error_type'] = 'rate_limit'
                    result['error_message'] = error_msg
                    print(f"\n[RATE LIMIT] {error_msg}", file=sys.stderr)
                    print("[INFO] 建议在 config.toml 中调整 extract.parallel 或增加 retry_delay", file=sys.stderr)
                    raise  # 抛出异常以便重试
                else:
                    result['error_type'] = 'api_error'
                    result['error_message'] = error_msg
                    print(f"[WARNING] LangExtract failed: {error_msg}", file=sys.stderr)
        
        # 回退到 regexp
        if not institutions:
            institutions = extract_with_regexp(text)
        
        # 保存结果
        output_data = {"host_institutions": institutions}
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        result['success'] = True
        result['institutions_count'] = len(institutions)
        
    except Exception as e:
        if not result['error_type']:  # 如果还没有设置错误类型
            result['error_type'] = 'unknown'
            result['error_message'] = str(e)[:200]
    
    return result


def process_hash_dir(hash_dir: Path, config: Dict[str, Any], retry_times: int = 3, retry_delay: int = 5) -> Dict[str, Any]:
    """
    处理单个 hash 目录
    
    Returns:
        处理结果字典
    """
    hash_name = hash_dir.name
    dom_file = hash_dir / "dom.html"
    md_file = hash_dir / "dom.md"
    json_file = hash_dir / "host.json"
    
    result = {
        'hash': hash_name,
        'dom_path': str(hash_dir.relative_to(hash_dir.parent.parent.parent.parent)),
        'extract_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'failed',
        'institutions_count': 0,
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
    
    # 提取信息（带重试）
    last_exception = None
    for attempt in range(retry_times):
        try:
            extract_result = extract_institutions(md_file, json_file, config)
            
            if extract_result['success']:
                result['status'] = 'success'
                result['institutions_count'] = extract_result['institutions_count']
                return result
            else:
                # 如果是频率限制，等待后重试
                if extract_result['error_type'] == 'rate_limit':
                    if attempt < retry_times - 1:
                        time.sleep(retry_delay * (attempt + 1))  # 递增等待时间
                        continue
                
                # 其他错误直接返回
                result['error_type'] = extract_result['error_type']
                result['error_message'] = extract_result['error_message']
                return result
        
        except Exception as e:
            last_exception = e
            if attempt < retry_times - 1:
                time.sleep(retry_delay)
    
    # 所有重试都失败
    if last_exception:
        result['error_type'] = 'unknown'
        result['error_message'] = str(last_exception)[:200]
    
    return result


# ========== 主函数 ==========

def process_snapshots(snapshot_dir: Path, config: Dict[str, Any], parallel: int, log_file: Path) -> tuple:
    """
    处理快照目录中的所有待提取文件
    
    Returns:
        (success_count, failed_count)
    """
    # 扫描待提取目录
    target_dirs = find_snapshot_dirs(snapshot_dir)
    
    if not target_dirs:
        return 0, 0
    
    print(f"[EXTRACT] 发现 {len(target_dirs)} 个待提取的快照")
    
    extract_config = config.get('extract', {})
    retry_times = extract_config.get('retry_times', 3)
    retry_delay = extract_config.get('retry_delay', 5)
    
    success_count = 0
    failed_count = 0
    
    # 并行处理
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        # 提交任务
        future_to_dir = {
            executor.submit(process_hash_dir, hash_dir, config, retry_times, retry_delay): hash_dir
            for hash_dir in target_dirs
        }
        
        # 使用进度条
        if TQDM_AVAILABLE:
            progress = tqdm(total=len(target_dirs), desc="[PROGRESS]", unit="file")
        
        # 处理完成的任务
        for future in as_completed(future_to_dir):
            hash_dir = future_to_dir[future]
            
            try:
                result = future.result()
                
                # 记录日志
                log_result(log_file, result)
                
                # 统计
                if result['status'] == 'success':
                    success_count += 1
                else:
                    failed_count += 1
                    print(f"\n[FAILED] {hash_dir.name}: {result.get('error_type', 'unknown')}")
                
                # 更新进度
                if TQDM_AVAILABLE:
                    progress.update(1)
            
            except Exception as e:
                print(f"\n[ERROR] Exception processing {hash_dir.name}: {e}", file=sys.stderr)
                failed_count += 1
                
                # 记录异常到日志
                log_result(log_file, {
                    'hash': hash_dir.name,
                    'dom_path': str(hash_dir),
                    'extract_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'status': 'failed',
                    'error_type': 'unknown',
                    'error_message': str(e)[:200]
                })
                
                if TQDM_AVAILABLE:
                    progress.update(1)
        
        if TQDM_AVAILABLE:
            progress.close()
    
    return success_count, failed_count


def main():
    parser = argparse.ArgumentParser(
        description="批量信息提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python batch_extract.py --input journals.xlsx
  python batch_extract.py --input journals-snapshot/
  python batch_extract.py --input journals-snapshot/ --parallel 3
  python batch_extract.py --input journals-snapshot/ --watch
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Excel 文件路径 或 快照目录路径'
    )
    parser.add_argument(
        '--parallel',
        type=int,
        default=None,
        help='并行数量（覆盖配置文件）'
    )
    parser.add_argument(
        '--watch',
        action='store_true',
        help='持续监听模式（定期扫描新文件）'
    )
    parser.add_argument(
        '--watch-interval',
        type=int,
        default=None,
        help='监听模式扫描间隔（秒）'
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
    watch_interval = args.watch_interval if args.watch_interval is not None else extract_config.get('watch_interval', 30)
    
    # 确定快照目录
    snapshot_dir = get_snapshot_dir(args.input)
    
    # 打印关键参数（排错用）
    print("=" * 60)
    print("[CONFIG] 批量信息提取工具 - 启动参数")
    print("=" * 60)
    print(f"输入路径:      {args.input}")
    print(f"快照目录:      {snapshot_dir}")
    print(f"并行数量:      {parallel}")
    print(f"模型 ID:       {extract_config.get('model_id', 'gpt-4o-mini')}")
    print(f"API Base:      {api_config.get('api_base', 'from env')}")
    print(f"重试次数:      {extract_config.get('retry_times', 3)}")
    print(f"重试延迟:      {extract_config.get('retry_delay', 5)} 秒")
    print(f"监听模式:      {'启用' if args.watch else '禁用'}")
    if args.watch:
        print(f"扫描间隔:      {watch_interval} 秒")
    print(f"配置文件:      config.toml")
    print("=" * 60)
    print()
    
    # 初始化日志
    log_file = snapshot_dir / "extract-log.csv"
    init_log_file(log_file)
    
    # 处理模式
    if args.watch:
        print(f"[WATCH] 监听模式启动，每 {watch_interval} 秒扫描一次...")
        print("[WATCH] 按 Ctrl+C 停止监听")
        
        try:
            while True:
                success, failed = process_snapshots(snapshot_dir, config, parallel, log_file)
                
                if success > 0 or failed > 0:
                    print(f"[WATCH] 本轮处理完成 - 成功: {success}, 失败: {failed}")
                
                time.sleep(watch_interval)
        
        except KeyboardInterrupt:
            print("\n[WATCH] 监听已停止")
    
    else:
        # 一次性处理
        print(f"[EXTRACT] 开始提取，并行数={parallel}")
        
        success, failed = process_snapshots(snapshot_dir, config, parallel, log_file)
        
        # 输出统计
        print(f"\n[OK] 提取完成")
        print(f"     成功: {success}")
        print(f"     失败: {failed}")
        print(f"     日志: {log_file}")


if __name__ == "__main__":
    main()

