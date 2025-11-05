#!/usr/bin/env python3
# snapshot.py
# Usage:
#   python snapshot.py <url> -o <filename>.html
#   如果 -o 未提供，则使用 url 的 sha1 作为文件名
#   可选配置文件 config.toml 提供 headless / user-agent / proxy 设置

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Dict

import tomllib  # Python 3.11+ 标准库，若为旧版本可用 pip install tomli
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def load_config(path: str = "config.toml") -> Dict[str, Any]:
    """读取配置文件，若不存在则返回空字典"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
            return data.get("snapshot", data)  # 支持顶层或 [snapshot] 节点
    except Exception as e:
        print(f"Warning: failed to load config.toml ({e})", file=sys.stderr)
        return {}


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def ensure_html_suffix(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() != ".html":
        p = p.with_suffix(".html")
    return str(p)


def main():
    parser = argparse.ArgumentParser(
        description="Snapshot a web page's final DOM after network idle."
    )
    parser.add_argument("url", help="Target URL to snapshot")
    parser.add_argument(
        "-o", "--output",
        help="Output HTML filename. If omitted, uses SHA1(url).html",
        default=None
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60000,
        help="Navigation timeout in milliseconds (default: 60000)"
    )
    parser.add_argument(
        "--wait-after-idle",
        type=int,
        default=0,
        help="Extra wait (ms) after network idle before capturing (default: 0)"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Force headed mode (override config)"
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        help="Override User-Agent"
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy URL, e.g. http://127.0.0.1:7890"
    )

    args = parser.parse_args()
    cfg = load_config("config.toml")

    # 合并配置优先级: CLI > config.toml > 默认值
    headless = not args.no_headless and cfg.get("headless", True)
    user_agent = args.user_agent or cfg.get("user_agent")
    proxy = args.proxy or cfg.get("proxy")

    url = args.url
    out_path = ensure_html_suffix(args.output.strip()) if args.output else f"{sha1_hex(url)}.html"

    # 创建输出目录
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            launch_opts = {"headless": headless}
            if proxy:
                launch_opts["proxy"] = {"server": proxy}

            browser = p.chromium.launch(**launch_opts)
            ctx_kwargs = {}
            if user_agent:
                ctx_kwargs["user_agent"] = user_agent
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            page.set_default_timeout(args.timeout)

            try:
                page.goto(url, wait_until="networkidle", timeout=args.timeout)
            except PlaywrightTimeoutError:
                page.goto(url, wait_until="domcontentloaded", timeout=args.timeout)

            if args.wait_after_idle > 0:
                page.wait_for_timeout(args.wait_after_idle)

            html = page.content()

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)

            print(f"✅ Saved snapshot to: {out_path}")
            print(f"   headless={headless}, proxy={proxy or 'none'}")

            context.close()
            browser.close()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
