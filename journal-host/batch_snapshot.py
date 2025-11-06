#!/usr/bin/env python3
"""
批量快照下载工具 - batch_snapshot.py

从 Excel 文件读取 URL 列表，批量下载网页快照（dom.html + page.mhtml）
支持并行处理、断点续传、详细日志记录
"""

import argparse
import csv
import hashlib
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[ERROR] playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("[WARNING] tqdm not installed, progress bar disabled. Run: pip install tqdm", file=sys.stderr)


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
            return data.get("snapshot", {})
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


# ========== 日志管理 ==========

def load_completed_urls(log_file: Path) -> Set[str]:
    """从日志文件加载已完成的 URL"""
    completed = set()
    
    if not log_file.exists():
        return completed
    
    try:
        with open(log_file, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('status') == 'success':
                    completed.add(row['url'])
    except Exception as e:
        print(f"[WARNING] Failed to load log file: {e}", file=sys.stderr)
    
    return completed


def init_log_file(log_file: Path):
    """初始化日志文件（如果不存在）"""
    if not log_file.exists():
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['url', 'hash', 'dom_size', 'mhtml_size', 'snapshot_time', 'status', 'error_type', 'error_message'])


def log_result(log_file: Path, result: Dict[str, Any]):
    """记录快照结果到日志"""
    try:
        with open(log_file, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                result['url'],
                result['hash'],
                result.get('dom_size', 0),
                result.get('mhtml_size', 0),
                result.get('snapshot_time', ''),
                result['status'],
                result.get('error_type', ''),
                result.get('error_message', '')
            ])
    except Exception as e:
        print(f"[ERROR] Failed to write log: {e}", file=sys.stderr)


# ========== 快照处理 ==========

def get_hash_path(snapshot_dir: Path, url_hash: str) -> Path:
    """获取 hash 分层目录路径"""
    return snapshot_dir / url_hash[:2] / url_hash[2:4] / url_hash[4:]


def snapshot_url(url: str, snapshot_dir: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单个 URL 进行快照
    
    Returns:
        包含快照结果的字典
    """
    url_hash = sha1_hex(url)
    hash_path = get_hash_path(snapshot_dir, url_hash)
    dom_file = hash_path / "dom.html"
    mhtml_file = hash_path / "page.mhtml"
    
    result = {
        'url': url,
        'hash': url_hash,
        'snapshot_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'failed',
        'error_type': '',
        'error_message': ''
    }
    
    # 检查文件是否已存在
    if dom_file.exists() and mhtml_file.exists():
        result['status'] = 'success'
        result['dom_size'] = dom_file.stat().st_size
        result['mhtml_size'] = mhtml_file.stat().st_size
        return result
    
    # 创建目录
    hash_path.mkdir(parents=True, exist_ok=True)
    
    playwright = None
    browser = None
    context = None
    page = None
    
    try:
        # 为每个任务创建独立的浏览器实例
        playwright = sync_playwright().start()
        
        # 启动浏览器配置
        launch_opts = {
            "headless": config.get('headless', True)
        }
        if config.get('proxy'):
            launch_opts['proxy'] = {'server': config['proxy']}
        
        browser = playwright.chromium.launch(**launch_opts)
        
        # 创建浏览器上下文
        context_options = {}
        if config.get('user_agent'):
            context_options['user_agent'] = config['user_agent']
        
        context = browser.new_context(**context_options)
        page = context.new_page()
        page.set_default_timeout(config.get('timeout', 60000))
        
        # 加载页面
        try:
            page.goto(url, wait_until="networkidle", timeout=config.get('timeout', 60000))
        except PlaywrightTimeoutError:
            # 回退到 domcontentloaded
            page.goto(url, wait_until="domcontentloaded", timeout=config.get('timeout', 60000))
        
        # 额外等待
        if config.get('wait_after_idle', 0) > 0:
            page.wait_for_timeout(config['wait_after_idle'])
        
        # 保存 dom.html
        dom_content = page.content()
        with open(dom_file, 'w', encoding='utf-8') as f:
            f.write(dom_content)
        result['dom_size'] = len(dom_content.encode('utf-8'))
        
        # 保存 page.mhtml (通过 CDP)
        try:
            cdp = context.new_cdp_session(page)
            mhtml_result = cdp.send('Page.captureSnapshot', {'format': 'mhtml'})
            mhtml_content = mhtml_result['data']
            
            with open(mhtml_file, 'w', encoding='utf-8') as f:
                f.write(mhtml_content)
            result['mhtml_size'] = len(mhtml_content.encode('utf-8'))
        except Exception as e:
            print(f"[WARNING] Failed to save MHTML for {url}: {e}", file=sys.stderr)
            # MHTML 失败不影响整体成功状态
            result['mhtml_size'] = 0
        
        result['status'] = 'success'
        
    except PlaywrightTimeoutError:
        result['error_type'] = 'timeout'
        result['error_message'] = 'Navigation timeout exceeded'
    except Exception as e:
        error_msg = str(e)
        
        if 'net::' in error_msg or 'NS_ERROR' in error_msg:
            result['error_type'] = 'network_error'
        elif 'HTTP' in error_msg or '404' in error_msg or '500' in error_msg:
            result['error_type'] = 'http_error'
        elif 'invalid' in error_msg.lower() or 'malformed' in error_msg.lower():
            result['error_type'] = 'invalid_url'
        else:
            result['error_type'] = 'unknown'
        
        result['error_message'] = error_msg[:200]  # 限制错误消息长度
    
    finally:
        if context:
            try:
                context.close()
            except:
                pass
        if browser:
            try:
                browser.close()
            except:
                pass
        if playwright:
            try:
                playwright.stop()
            except:
                pass
    
    return result


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(
        description="批量快照下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python batch_snapshot.py \\
    --url-excel journals.xlsx \\
    --name-column A \\
    --url-columns D,F \\
    --rows 4+

  python batch_snapshot.py \\
    --url-excel journals.xlsx \\
    --name-column A \\
    --url-columns D \\
    --rows 4-99 \\
    --parallel 5
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
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config("config.toml")
    parallel = args.parallel if args.parallel is not None else config.get('parallel', 1)
    
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
    print("[CONFIG] 批量快照下载工具 - 启动参数")
    print("=" * 60)
    print(f"Excel 文件:    {args.url_excel}")
    print(f"Sheet 名称:    {args.sheet_name}")
    print(f"期刊名称列:    {args.name_column}")
    print(f"URL 列:        {args.url_columns}")
    print(f"行范围:        {args.rows}")
    print(f"并行数量:      {parallel}")
    print(f"无头模式:      {config.get('headless', True)}")
    print(f"代理设置:      {config.get('proxy', 'none')}")
    print(f"超时时间:      {config.get('timeout', 60000)} ms")
    print(f"配置文件:      config.toml")
    print("=" * 60)
    print()
    
    # 检查 Excel 文件
    excel_path = Path(args.url_excel)
    if not excel_path.exists():
        print(f"[ERROR] Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)
    
    # 读取 URL
    print(f"[SNAPSHOT] 读取 Excel 文件...")
    
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
    
    print(f"[SNAPSHOT] 读取到 {len(urls)} 个 URL（去重后）")
    
    if not urls:
        print("[WARNING] No URLs found", file=sys.stderr)
        sys.exit(0)
    
    # 创建快照目录
    snapshot_dir = excel_path.parent / f"{excel_path.stem}-snapshot"
    snapshot_dir.mkdir(exist_ok=True)
    
    print(f"[INFO] 快照目录: {snapshot_dir}")
    
    # 初始化日志
    log_file = snapshot_dir / "snapshot-log.csv"
    init_log_file(log_file)
    
    # 加载已完成的 URL
    completed_urls = load_completed_urls(log_file)
    remaining_urls = [url for url in urls if url not in completed_urls]
    
    if completed_urls:
        print(f"[SNAPSHOT] 跳过 {len(completed_urls)} 个已完成的 URL")
    
    if not remaining_urls:
        print("[OK] 所有 URL 已完成")
        sys.exit(0)
    
    print(f"[SNAPSHOT] 开始处理 {len(remaining_urls)} 个 URL，并行数={parallel}")
    
    # 并行处理（每个任务创建独立的浏览器实例）
    success_count = 0
    failed_count = 0
    
    # 并行处理
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        # 提交任务
        future_to_url = {
            executor.submit(snapshot_url, url, snapshot_dir, config): url
            for url in remaining_urls
        }
        
        # 使用进度条
        if TQDM_AVAILABLE:
            progress = tqdm(total=len(remaining_urls), desc="[PROGRESS]", unit="url")
        
        # 处理完成的任务
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            
            try:
                result = future.result()
                
                # 记录日志
                log_result(log_file, result)
                
                # 统计
                if result['status'] == 'success':
                    success_count += 1
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
                    'url': url,
                    'hash': sha1_hex(url),
                    'snapshot_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'status': 'failed',
                    'error_type': 'unknown',
                    'error_message': str(e)[:200]
                })
                
                if TQDM_AVAILABLE:
                    progress.update(1)
        
        if TQDM_AVAILABLE:
            progress.close()
    
    # 输出统计
    print(f"\n[OK] 快照完成")
    print(f"     成功: {success_count}")
    print(f"     失败: {failed_count}")
    print(f"     日志: {log_file}")


if __name__ == "__main__":
    main()
