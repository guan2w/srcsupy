#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_snapshot.py

按 Excel 行构造搜索关键字，调用 ScrapingBee Google Search API，
取前 3 条 URL 做截图快照，并将过程记录到 log.csv 中。

依赖：
    pip install openpyxl requests scrapingbee

使用示例：
    python search_snapshot.py \
        --input-file=/path/to/file.xlsx \
        --sheet=Sheet1 \
        --search-columns=C*,D \
        --rows=3+ \
        --debug

配置文件：
    同目录下可选 config.toml，结构示例：

    [scrapingbee]
    timeout_seconds = 120
    concurrency = 3
    retry_times = 1

环境变量：
    当前目录 .env 文件中可设置：
        SCRAPINGBEE_API_KEY=xxxxxx
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any

import requests
from openpyxl import load_workbook
from scrapingbee import ScrapingBeeClient

# --- toml 解析：兼容 3.11+ 的 tomllib 与 3.10 的 tomli ---
try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # 需要 pip install tomli
    except ImportError:
        tomllib = None  # 后面代码会处理这个情况

# ----------------- 全局状态 -----------------

DEBUG = False

# 搜索缓存：keywords -> dict(search_result_json, search_error, urls)
search_cache_lock = threading.Lock()
search_cache: Dict[str, Dict[str, Any]] = {}

# 快照缓存：url -> relative_path
snapshot_cache_lock = threading.Lock()
snapshot_cache: Dict[str, str] = {}

# 已完成行： (sheet_name, row_number)
row_done_lock = threading.Lock()
row_done_set: set[Tuple[str, int]] = set()

# 进度统计
progress_lock = threading.Lock()
total_tasks = 0
finished_tasks = 0
success_tasks = 0
failed_tasks = 0


# ----------------- 工具函数 -----------------

def debug_print(*args, **kwargs):
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)


def log_print(*args, **kwargs):
    """普通控制台输出，带时间前缀"""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}]", *args, **kwargs)


def load_env_file(path: str = ".env"):
    """简单解析 .env 文件，将 KEY=VALUE 写入 os.environ（若不存在则跳过）"""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # 去掉包围的引号
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        log_print("加载 .env 文件出错：", e)


def load_config(config_path: str) -> Dict[str, Any]:
    """读取 config.toml 中 [scrapingbee] 配置，不存在则使用默认值"""
    default_cfg = {
        "timeout_seconds": 120,
        "concurrency": 1,
        "retry_times": 1,
    }
    if not os.path.exists(config_path):
        debug_print("config.toml 不存在，使用默认配置。")
        return default_cfg

    if tomllib is None:
        log_print("警告：未安装 tomllib/tomli，无法解析 config.toml，使用默认配置。")
        return default_cfg

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        bee_cfg = data.get("scrapingbee", {}) or {}
        for key in default_cfg:
            if key in bee_cfg:
                default_cfg[key] = bee_cfg[key]
        debug_print("加载 config.toml 成功：", default_cfg)
        return default_cfg
    except Exception as e:
        log_print("解析 config.toml 出错，使用默认配置。错误：", e)
        return default_cfg


def column_letters_to_index(letters: str) -> int:
    """将 Excel 列字母（如 'A', 'C', 'AA'）转换为 1-based 列索引"""
    letters = letters.upper()
    result = 0
    for ch in letters:
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"非法列字母: {letters}")
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result


def parse_search_columns(spec: str) -> List[Tuple[int, bool]]:
    """
    解析 --search-columns 参数，如 "C*,D,AA*"
    返回列表 [(col_index, exact_match), ...]
    exact_match=True 表示需要加双引号
    """
    result: List[Tuple[int, bool]] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        exact = token.endswith("*")
        col_letters = token[:-1] if exact else token
        col_index = column_letters_to_index(col_letters)
        result.append((col_index, exact))
    if not result:
        raise ValueError("search-columns 解析结果为空，请检查参数。")
    return result


def parse_rows_spec(spec: str, max_row: int) -> Tuple[int, int]:
    """
    解析 --rows 参数：
        '3+'  -> (3, max_row)
        '3-9' -> (3, 9)
    返回 (start_row, end_row)，均为闭区间
    """
    spec = spec.strip()
    if spec.endswith("+"):
        start = spec[:-1]
        if not start.isdigit():
            raise ValueError(f"rows 参数非法：{spec}")
        start_row = int(start)
        end_row = max_row
    else:
        if "-" not in spec:
            raise ValueError(f"rows 参数非法：{spec}")
        parts = spec.split("-", 1)
        if not (parts[0].isdigit() and parts[1].isdigit()):
            raise ValueError(f"rows 参数非法：{spec}")
        start_row = int(parts[0])
        end_row = int(parts[1])
    if start_row < 1 or end_row < start_row:
        raise ValueError(f"rows 范围非法：{start_row}-{end_row}")
    # 同时不允许超过 max_row
    if start_row > max_row:
        raise ValueError(f"rows 起始行 {start_row} 大于 sheet 最大行 {max_row}")
    end_row = min(end_row, max_row)
    return start_row, end_row


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ----------------- ScrapingBee 调用 -----------------

def search_google_once(api_key: str, keywords: str, language: str, timeout: int) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], float]:
    """
    调用一次 ScrapingBee Google Search。
    返回 (organic_results, error_message, duration_seconds)
    error_message 为 None 表示成功。
    """
    url = "https://app.scrapingbee.com/api/v1/google"
    params = {
        "api_key": api_key,
        "search": keywords,
        "language": language,
    }
    start = time.monotonic()
    try:
        response = requests.get(url, params=params, timeout=timeout)
        duration = time.monotonic() - start
        status = response.status_code
        if status != 200:
            try:
                txt = response.text[:200]
            except Exception:
                txt = ""
            return None, f"HTTP {status}: {txt}", duration
        data = response.json()
        organic = data.get("organic_results", [])
        if not isinstance(organic, list):
            return None, "organic_results 非列表", duration
        return organic, None, duration
    except Exception as e:
        duration = time.monotonic() - start
        return None, f"请求异常: {e}", duration


def search_google_with_retry(api_key: str, keywords: str, language: str, timeout: int, retry_times: int) -> Tuple[List[Dict[str, Any]], str, float]:
    """
    带重试的搜索。
    返回 (organic_results_list, error_message, total_duration)
    error_message 为空字符串表示无错误。
    """
    total_duration = 0.0
    last_error = ""
    attempts = 1 + max(retry_times, 0)
    for attempt in range(1, attempts + 1):
        organic, err, dur = search_google_once(api_key, keywords, language, timeout)
        total_duration += dur
        log_print(f"[SEARCH] attempt={attempt}/{attempts} keywords={keywords!r} duration={dur:.3f}s error={err}")
        if err is None:
            return organic, "", total_duration
        last_error = err
        # 简单退避
        time.sleep(min(1.0 * attempt, 5.0))
    return [], last_error, total_duration


def screenshot_once(client: ScrapingBeeClient, url: str, save_full_path: str, timeout: int) -> Optional[str]:
    """
    截图一次；成功返回 None (表示无错误)，失败返回 error_message。
    """
    start = time.monotonic()
    try:
        os.makedirs(os.path.dirname(save_full_path), exist_ok=True)
        response = client.get(
            url,
            params={
                "screenshot": True,
                "screenshot_full_page": True,
            },
            timeout=timeout,
        )
        duration = time.monotonic() - start
        log_print(f"[SCREENSHOT] url={url} duration={duration:.3f}s status={getattr(response, 'status_code', 'N/A')}")
        content = getattr(response, "content", None)
        if not content:
            return f"empty content for url={url}"
        with open(save_full_path, "wb") as f:
            f.write(content)
        return None
    except Exception as e:
        duration = time.monotonic() - start
        log_print(f"[SCREENSHOT] url={url} duration={duration:.3f}s error={e}")
        return f"exception for url={url}: {e}"


def screenshot_with_retry(client: ScrapingBeeClient, url: str, save_full_path: str, timeout: int, retry_times: int) -> Tuple[bool, List[str]]:
    """
    带重试的截图。
    返回 (success, error_messages_list)
    """
    errors: List[str] = []
    attempts = 1 + max(retry_times, 0)
    for attempt in range(1, attempts + 1):
        err = screenshot_once(client, url, save_full_path, timeout)
        if err is None:
            return True, []
        errors.append(f"attempt {attempt}: {err}")
        time.sleep(min(1.0 * attempt, 5.0))
    return False, errors


# ----------------- log.csv 相关 -----------------

LOG_HEADER = [
    "sheet",
    "row",
    "keywords",
    "search_time",
    "search_duration_ms",
    "search_result_json",
    "search_error",
    "snapshot_status",
    "snapshot_errors",
    "url1",
    "snapshot1_path",
    "url2",
    "snapshot2_path",
    "url3",
    "snapshot3_path",
]


def ensure_log_header(log_path: str):
    """如果 log.csv 不存在，则创建并写入表头"""
    if not os.path.exists(log_path):
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(LOG_HEADER)
        debug_print(f"创建 log 文件并写入 header: {log_path}")


def load_existing_log(log_path: str, snapshot_root: str):
    """
    启动时读取已有 log.csv，更新：
        - row_done_set
        - search_cache (按 keywords)
        - snapshot_cache (按 url)
    """
    if not os.path.exists(log_path):
        debug_print("log.csv 不存在，无需恢复状态。")
        return

    with open(log_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sheet_name = row.get("sheet", "")
            row_no_str = row.get("row", "")
            keywords = (row.get("keywords") or "").strip()
            search_result_json = row.get("search_result_json") or ""
            search_error = row.get("search_error") or ""
            snapshot_status = row.get("snapshot_status") or ""
            snapshot_errors = row.get("snapshot_errors") or ""
            url1 = row.get("url1") or ""
            url2 = row.get("url2") or ""
            url3 = row.get("url3") or ""
            snap1 = row.get("snapshot1_path") or ""
            snap2 = row.get("snapshot2_path") or ""
            snap3 = row.get("snapshot3_path") or ""

            # 行完成判断
            try:
                row_no = int(row_no_str)
            except ValueError:
                row_no = None

            # 解析 snapshot_status，如 "2/3"
            done = False
            if search_error == "":
                if snapshot_status:
                    parts = snapshot_status.split("/")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        num_ok = int(parts[0])
                        num_total = int(parts[1])
                        if num_total == 0:
                            # 没有 URL 也算完成
                            done = True
                        elif num_ok == num_total:
                            done = True

            if done and sheet_name and row_no is not None:
                row_done_set.add((sheet_name, row_no))

            # 搜索缓存
            if keywords and search_result_json:
                with search_cache_lock:
                    if keywords not in search_cache:
                        try:
                            parsed = json.loads(search_result_json)
                        except Exception:
                            parsed = []
                        search_cache[keywords] = {
                            "results": parsed,
                            "search_error": search_error,
                        }

            # 快照缓存：仅在文件真实存在时缓存
            def maybe_add_snapshot(url: str, rel_path: str):
                if not url or not rel_path:
                    return
                full_path = os.path.join(snapshot_root, rel_path)
                if os.path.exists(full_path):
                    with snapshot_cache_lock:
                        if url not in snapshot_cache:
                            snapshot_cache[url] = rel_path

            maybe_add_snapshot(url1, snap1)
            maybe_add_snapshot(url2, snap2)
            maybe_add_snapshot(url3, snap3)

    debug_print(f"恢复状态：{len(row_done_set)} 行已完成，"
                f"{len(search_cache)} 个关键字已有搜索缓存，"
                f"{len(snapshot_cache)} 条 URL 已有快照缓存。")


# ----------------- 核心 worker -----------------

def build_keywords_from_row(ws, row_idx: int, columns_spec: List[Tuple[int, bool]]) -> str:
    """
    从给定行构造搜索关键字字符串。
    columns_spec: [(col_index, exact), ...]
    """
    parts: List[str] = []
    for col_index, exact in columns_spec:
        cell = ws.cell(row=row_idx, column=col_index)
        value = cell.value
        if value is None:
            continue
        s = str(value)
        s = s.replace("\n", " ").strip()
        if not s:
            continue
        if exact:
            parts.append(f'"{s}"')
        else:
            parts.append(s)
    keywords = " ".join(parts).strip()
    return keywords


def process_row_task(
    sheet_name: str,
    row_idx: int,
    ws,
    columns_spec: List[Tuple[int, bool]],
    api_key: str,
    cfg: Dict[str, Any],
    snapshot_root: str,
    log_writer: csv.writer,
    log_file,
    log_lock: threading.Lock,
):
    global finished_tasks, success_tasks, failed_tasks

    # 1. 如果行已完成，直接跳过（一般不会，因为构建任务前已过滤），但这里再保险一次
    with row_done_lock:
        if (sheet_name, row_idx) in row_done_set:
            debug_print(f"行已完成，跳过: {sheet_name}#{row_idx}")
            return

    # 2. 构造关键字
    keywords = build_keywords_from_row(ws, row_idx, columns_spec)
    keywords = keywords.strip()

    if not keywords:
        msg = f"Sheet={sheet_name} Row={row_idx} 搜索列全为空，跳过此行。"
        log_print(msg)
        search_time_iso = dt.datetime.now().astimezone().isoformat()
        search_duration_ms = 0
        search_result_json = ""
        search_error = "empty keywords"
        snapshot_status = "0/0"
        snapshot_errors = ""
        urls = ["", "", ""]
        snapshot_paths = ["", "", ""]
        # 写 log
        with log_lock:
            log_writer.writerow([
                sheet_name,
                row_idx,
                keywords,
                search_time_iso,
                search_duration_ms,
                search_result_json,
                search_error,
                snapshot_status,
                snapshot_errors,
                urls[0],
                snapshot_paths[0],
                urls[1],
                snapshot_paths[1],
                urls[2],
                snapshot_paths[2],
            ])
            log_file.flush()

        with progress_lock:
            finished_tasks += 1
            # 空行，算成功还是失败？这里算成功。
            success_tasks += 1
            log_print(f"进度：{finished_tasks}/{total_tasks} 完成（成功 {success_tasks}, 失败 {failed_tasks}）")
        return

    # 3. 搜索（使用缓存 + 重试）
    timeout = int(cfg["timeout_seconds"])
    retry_times = int(cfg["retry_times"])
    language = "en"  # 目前按照需求固定 en，后续如需配置可从 config 读取

    # 搜索缓存检查
    with search_cache_lock:
        cached = search_cache.get(keywords)

    if cached is not None:
        organic_results = cached["results"]
        search_error = cached.get("search_error", "")
        search_duration_ms = 0
        search_time_iso = dt.datetime.now().astimezone().isoformat()
        debug_print(f"使用已有搜索缓存：keywords={keywords!r}")
    else:
        search_time_iso = dt.datetime.now().astimezone().isoformat()
        organic_results, search_error, dur = search_google_with_retry(
            api_key=api_key,
            keywords=keywords,
            language=language,
            timeout=timeout,
            retry_times=retry_times,
        )
        search_duration_ms = int(dur * 1000)
        # 写入缓存
        with search_cache_lock:
            search_cache[keywords] = {
                "results": organic_results,
                "search_error": search_error,
            }

    # 转成 JSON 保存（仅保存 organic_results 部分）
    try:
        search_result_json = json.dumps(organic_results, ensure_ascii=False)
    except Exception:
        search_result_json = ""

    # 4. 取前 3 条 URL
    urls: List[str] = []
    for item in organic_results[:3]:
        url = item.get("url") if isinstance(item, dict) else None
        if url:
            urls.append(str(url))
    while len(urls) < 3:
        urls.append("")

    # 5. 截图（使用缓存 + 重试）
    snapshot_paths = ["", "", ""]
    snapshot_errors_list: List[str] = []

    if search_error:
        log_print(f"搜索失败（不会截图）：keywords={keywords!r} error={search_error}")
        snapshot_status = "0/0"
    else:
        client = ScrapingBeeClient(api_key=api_key)
        success_count = 0
        total_urls = sum(1 for u in urls if u)

        for idx, url in enumerate(urls):
            if not url:
                continue

            # 快照缓存检查
            with snapshot_cache_lock:
                cached_path = snapshot_cache.get(url)

            if cached_path:
                # 确认文件依然存在
                full_path = os.path.join(snapshot_root, cached_path)
                if os.path.exists(full_path):
                    snapshot_paths[idx] = cached_path
                    success_count += 1
                    debug_print(f"使用已有快照：url={url} path={cached_path}")
                    continue
                else:
                    # 文件不存在了，缓存作废
                    with snapshot_cache_lock:
                        snapshot_cache.pop(url, None)

            # 需要新拍一张
            h = sha1_hex(url)
            rel_path = os.path.join(h[:2], h[2:4], h[4:] + ".png")
            full_path = os.path.join(snapshot_root, rel_path)

            ok, errs = screenshot_with_retry(
                client=client,
                url=url,
                save_full_path=full_path,
                timeout=timeout,
                retry_times=retry_times,
            )
            if ok:
                snapshot_paths[idx] = rel_path
                success_count += 1
                # 更新缓存
                with snapshot_cache_lock:
                    snapshot_cache[url] = rel_path
            else:
                snapshot_paths[idx] = ""
                snapshot_errors_list.extend(errs)

        snapshot_status = f"{success_count}/{total_urls}"

    snapshot_errors = "\n\n".join(snapshot_errors_list)

    # 6. 写 log
    with log_lock:
        log_writer.writerow([
            sheet_name,
            row_idx,
            keywords,
            search_time_iso,
            search_duration_ms,
            search_result_json,
            search_error,
            snapshot_status,
            snapshot_errors,
            urls[0],
            snapshot_paths[0],
            urls[1],
            snapshot_paths[1],
            urls[2],
            snapshot_paths[2],
        ])
        log_file.flush()

    # 7. 更新进度与完成标记
    is_success = (search_error == "" and not snapshot_errors_list)

    with progress_lock:
        finished_tasks += 1
        if is_success:
            success_tasks += 1
        else:
            failed_tasks += 1
        log_print(f"进度：{finished_tasks}/{total_tasks} 完成（成功 {success_tasks}, 失败 {failed_tasks}）")

    # 将已完成的行加入 row_done_set（仅在无错误时）
    if is_success:
        with row_done_lock:
            row_done_set.add((sheet_name, row_idx))


# ----------------- 主函数 -----------------

def main():
    global DEBUG, total_tasks

    parser = argparse.ArgumentParser(description="Excel 驱动的 ScrapingBee 搜索+快照脚本")
    parser.add_argument("--input-file", required=True, help="输入 Excel 文件路径 (.xlsx)")
    parser.add_argument("--sheet", required=True, help="Sheet 名称（不是序号）")
    parser.add_argument("--search-columns", required=True, help="搜索列设置，例如 C*,D")
    parser.add_argument("--rows", required=True, help="行范围，例如 3+ 或 3-9")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    DEBUG = bool(args.debug)

    input_path = os.path.abspath(args.input_file)
    if not os.path.exists(input_path):
        log_print(f"输入文件不存在：{input_path}")
        sys.exit(1)

    base_dir = os.path.dirname(input_path)
    base_name = os.path.splitext(os.path.basename(input_path))[0]

    snapshot_root = os.path.join(base_dir, f"{base_name}-snapshot")
    log_path = os.path.join(base_dir, f"{base_name}.log.csv")
    
    # 配置文件查找顺序：1. 脚本所在目录 2. 输入文件所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.toml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "config.toml")

    log_print(f"Input file: {input_path}")
    log_print(f"Snapshot dir: {snapshot_root}")
    log_print(f"Log file: {log_path}")
    log_print(f"Config file: {config_path}")

    # 1. 加载 .env 和配置
    load_env_file(".env")
    cfg = load_config(config_path)

    api_key = os.environ.get("SCRAPINGBEE_API_KEY", "").strip()
    if not api_key:
        log_print("错误：未找到 SCRAPINGBEE_API_KEY，请在 .env 或环境变量中设置。")
        sys.exit(1)

    # 2. 解析 search-columns
    try:
        columns_spec = parse_search_columns(args.search_columns)
        debug_print("columns_spec =", columns_spec)
    except Exception as e:
        log_print("解析 search-columns 出错：", e)
        sys.exit(1)

    # 3. 打开 Excel
    wb = load_workbook(input_path, read_only=True, data_only=True)
    if args.sheet not in wb.sheetnames:
        log_print("错误：Excel 中未找到 sheet：", args.sheet)
        log_print("可用 sheet:", wb.sheetnames)
        sys.exit(1)
    ws = wb[args.sheet]
    max_row = ws.max_row
    log_print(f"Sheet '{args.sheet}' 最大行号为 {max_row}")

    # 4. 解析 rows 范围
    try:
        start_row, end_row = parse_rows_spec(args.rows, max_row)
    except Exception as e:
        log_print("解析 rows 参数出错：", e)
        sys.exit(1)
    log_print(f"处理行范围：{start_row}-{end_row}")

    # 5. 准备 log 文件 & 恢复状态
    ensure_log_header(log_path)
    load_existing_log(log_path, snapshot_root)

    # 6. 构建任务列表（仅未完成的行）
    tasks: List[int] = []
    for row_idx in range(start_row, end_row + 1):
        with row_done_lock:
            if (args.sheet, row_idx) in row_done_set:
                debug_print(f"行已完成，略过: {args.sheet}#{row_idx}")
                continue
        tasks.append(row_idx)

    total_tasks = len(tasks)
    if total_tasks == 0:
        log_print("指定范围内的行已全部处理完成，无任务可执行。")
        return

    log_print(f"总任务数：{total_tasks}")

    # 7. 打开 log 文件（append 模式），初始化 writer
    log_lock = threading.Lock()
    with open(log_path, "a", newline="", encoding="utf-8") as log_file:
        log_writer = csv.writer(log_file)

        # 8. 并发执行
        concurrency = int(cfg["concurrency"])
        if concurrency < 1:
            concurrency = 1
        log_print(f"并发线程数：{concurrency}")

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_row = {
                executor.submit(
                    process_row_task,
                    args.sheet,
                    row_idx,
                    ws,
                    columns_spec,
                    api_key,
                    cfg,
                    snapshot_root,
                    log_writer,
                    log_file,
                    log_lock,
                ): row_idx
                for row_idx in tasks
            }

            # 等待所有任务完成
            for future in as_completed(future_to_row):
                row_idx = future_to_row[future]
                try:
                    future.result()
                except Exception as e:
                    log_print(f"行 {row_idx} 处理过程中出现未捕获异常：{e}")

    log_print("全部任务执行完毕。")
    log_print(f"最终统计：总任务 {total_tasks}，成功 {success_tasks}，失败 {failed_tasks}")


if __name__ == "__main__":
    main()
