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
from typing import Any, Dict, List, Set, Tuple

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


def parse_excel_range(range_str: str) -> Tuple[str, int, int]:
    """
    解析 Excel 范围字符串
    例如: "D4:D99" -> ("D", 4, 99)
    """
    match = re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', range_str.strip())
    if not match:
        raise ValueError(f"Invalid range format: {range_str}")
    
    col_start, row_start, col_end, row_end = match.groups()
    
    if col_start != col_end:
        raise ValueError(f"Range must be single column: {range_str}")
    
    return col_start, int(row_start), int(row_end)


def read_urls_from_excel(file_path: str, range_strings: str, sheet_name=0) -> List[str]:
    """
    从 Excel 文件读取 URL 列表
    
    Args:
        file_path: Excel 文件路径
        range_strings: 范围字符串，如 "D4:D99,F4:F99"
        sheet_name: Sheet 名称或索引（默认 0，即第一个 sheet）
    
    Returns:
        去重后的 URL 列表
    """
    all_urls = []
    
    for range_str in range_strings.split(','):
        range_str = range_str.strip()
        
        try:
            col, row_start, row_end = parse_excel_range(range_str)
            
            # 读取 Excel
            df = pd.read_excel(
                file_path,
                sheet_name=sheet_name,
                usecols=[col],
                skiprows=row_start - 1,
                nrows=row_end - row_start + 1,
                header=None,
                engine='openpyxl'
            )
            
            # 提取 URL
            urls = df.iloc[:, 0].tolist()
            urls = [str(u).strip() for u in urls if pd.notna(u)]
            all_urls.extend(urls)
            
        except Exception as e:
            print(f"[WARNING] Failed to read range {range_str}: {e}", file=sys.stderr)
            continue
    
    # 过滤和去重
    valid_urls = []
    exclude_keywords = ['未找到', '未披露']
    
    for url in all_urls:
        if url.startswith('http://') or url.startswith('https://'):
            valid_urls.append(url)
        elif url not in exclude_keywords:
            print(f"[SKIP] 非 http 开头: {url}")
    
    # 去重并保持顺序
    seen = set()
    unique_urls = []
    for url in valid_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls


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


def snapshot_url(browser, url: str, snapshot_dir: Path, config: Dict[str, Any]) -> Dict[str, Any]:
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
    
    context = None
    page = None
    
    try:
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
    
    return result


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(
        description="批量快照下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python batch_snapshot.py --url-excel journals.xlsx --url-ranges D4:D99,F4:F99
  python batch_snapshot.py --url-excel journals.xlsx --url-ranges D4:D99 --parallel 5
        """
    )
    
    parser.add_argument(
        '--url-excel',
        required=True,
        help='Excel 文件路径'
    )
    parser.add_argument(
        '--url-ranges',
        required=True,
        help='URL 单元格范围，多个范围用逗号分隔，如: D4:D99,F4:F99'
    )
    parser.add_argument(
        '--parallel',
        type=int,
        default=None,
        help='并行数量（覆盖配置文件）'
    )
    parser.add_argument(
        '--sheet-name',
        default=0,
        help='Excel Sheet 名称或索引（默认 0，即第一个 sheet）'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config("config.toml")
    parallel = args.parallel if args.parallel is not None else config.get('parallel', 1)
    
    # 打印关键参数（排错用）
    print("=" * 60)
    print("[CONFIG] 批量快照下载工具 - 启动参数")
    print("=" * 60)
    print(f"Excel 文件:    {args.url_excel}")
    print(f"Sheet 名称:    {args.sheet_name}")
    print(f"URL 范围:      {args.url_ranges}")
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
        # 尝试转换 sheet_name 为整数（如果是数字字符串）
        sheet_name = args.sheet_name
        try:
            sheet_name = int(sheet_name)
        except (ValueError, TypeError):
            pass  # 保持为字符串（sheet 名称）
        
        urls = read_urls_from_excel(str(excel_path), args.url_ranges, sheet_name)
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
    
    # 启动浏览器
    success_count = 0
    failed_count = 0
    
    with sync_playwright() as p:
        # 启动浏览器配置
        launch_opts = {
            "headless": config.get('headless', True)
        }
        if config.get('proxy'):
            launch_opts['proxy'] = {'server': config['proxy']}
        
        browser = p.chromium.launch(**launch_opts)
        
        try:
            # 并行处理
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                # 提交任务
                future_to_url = {
                    executor.submit(snapshot_url, browser, url, snapshot_dir, config): url
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
        
        finally:
            browser.close()
    
    # 输出统计
    print(f"\n[OK] 快照完成")
    print(f"     成功: {success_count}")
    print(f"     失败: {failed_count}")
    print(f"     日志: {log_file}")


if __name__ == "__main__":
    main()

