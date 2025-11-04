
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 功能：逐行读取 input.txt 的查询值，使用 requests 调用接口，解析 JSON，写出 output.csv
# 改动：
# - 始终对 {q} 做 URL 编码（移除可关闭选项）；
# - 无结果（users 为空）或失败（code != 0 / JSON 非法 / 逻辑失败）时：
#     * 向 stderr 原样打印响应 JSON（不格式化）；
#     * 向 stderr 打印本次请求的信息（method、url、headers、body）。
# - HTTP 层失败（网络/非 2xx）时：打印请求信息与响应体后立即退出。
#
# 用法示例：
#   python batch_requests_to_csv.py \

#       --url-template "https://api.example.com/search?q={q}" \

#       --method GET \

#       --header "Authorization: Bearer XXX" \

#       --input input.txt --output output.csv
#

# python3 batch_requests_to_csv.py --header "Content-Type: application/json" --header "Authorization: Bearer u-****" --url-template "https://open.feishu.cn/open-apis/search/v1/user?query={q}"
import argparse
import csv
import json
import sys
import requests
from urllib.parse import quote_plus
from pathlib import Path

def parse_header(h: str):
    if ":" not in h:
        raise ValueError(f"非法 header（缺少冒号）: {h}")
    k, v = h.split(":", 1)
    return k.strip(), v.strip()

def render_template(tpl: str, q: str, encode: bool = True) -> str:
    return tpl.replace("{q}", quote_plus(q) if encode else q)

def log_request_info(method: str, url: str, headers: dict, json_body, data_body):
    try:
        sys.stderr.write(f"[REQUEST] {method} {url}\n")
        if headers:
            # 不做缩进格式化，尽量单行
            sys.stderr.write(f"[REQUEST-HEADERS] {json.dumps(headers, ensure_ascii=False)}\n")
        if json_body is not None:
            sys.stderr.write(f"[REQUEST-BODY-JSON] {json.dumps(json_body, ensure_ascii=False)}\n")
        elif data_body is not None:
            sys.stderr.write(f"[REQUEST-BODY-DATA] {data_body}\n")
    except Exception as _:
        # 即使日志打印失败也不影响主要流程
        pass

def fetch(method: str, url: str, headers: dict, json_body, data_body, timeout: float) -> str:
    method = method.upper()
    kw = {"headers": headers, "timeout": timeout}
    if json_body is not None:
        kw["json"] = json_body
    elif data_body is not None:
        kw["data"] = data_body
    try:
        resp = requests.request(method, url, **kw)
        resp.raise_for_status()
        return resp.text
    except requests.HTTPError as he:
        # HTTP 层失败：打印请求信息与响应体后退出
        log_request_info(method, url, headers, json_body, data_body)
        body = getattr(he.response, "text", "")
        if body:
            sys.stderr.write(body + "\n")
        sys.stderr.write(f"[ERROR] HTTP 请求失败：{he}\n")
        sys.exit(1)
    except requests.RequestException as re:
        log_request_info(method, url, headers, json_body, data_body)
        sys.stderr.write(f"[ERROR] 请求异常：{re}\n")
        sys.exit(1)

def handle_response_text(text: str):
    """
    返回 (status, rows)
    status: 'ok' | 'no_match' | 'fail' | 'bad_json'
    rows: [(name, user_id), ...]
    约定：调用者在 'no_match' / 'fail' / 'bad_json' 时，会额外打印请求信息。
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        sys.stderr.write(text + "\n")
        return "bad_json", [("【调用失败】", "")]

    code = obj.get("code")
    try:
        code_int = int(code)
    except Exception:
        code_int = None

    if code_int == 0:
        data = obj.get("data", {}) or {}
        users = data.get("users", []) or []
        if not isinstance(users, list):
            users = []
        if users:
            rows = []
            for u in users:
                if isinstance(u, dict):
                    name = u.get("name", "")
                    user_id = u.get("user_id", "")
                    rows.append((name, user_id))
            return "ok", rows
        else:
            # 无匹配：打印响应 JSON（调用者也会打印请求信息）
            sys.stderr.write(text + "\n")
            return "no_match", [("【无匹配】", "")]
    else:
        # 失败：打印响应 JSON（调用者也会打印请求信息）
        sys.stderr.write(text + "\n")
        return "fail", [("【调用失败】", "")]

def main():
    ap = argparse.ArgumentParser(description="requests 版：逐行请求接口，解析 JSON，写出 output.csv")
    ap.add_argument("--input", default="input.txt", help="输入文件（每行一个查询）")
    ap.add_argument("--output", default="output.csv", help="输出 CSV 文件路径")
    ap.add_argument("--url-template", required=True, help="URL 模板，包含 {q} 占位符（会对 {q} URL 编码）")
    ap.add_argument("--method", default="GET", help="HTTP 方法：GET/POST/PUT/PATCH/DELETE")
    ap.add_argument("--header", action="append", default=[], help="请求头，形如 'K: V'，可多次传入")
    ap.add_argument("--json-template", help="JSON 请求体模板（字符串），可包含 {q}（不再额外 URL 编码）")
    ap.add_argument("--data-template", help="表单/文本请求体模板，可包含 {q}（会 URL 编码）")
    ap.add_argument("--timeout", type=float, default=15.0, help="请求超时（秒），默认 15")
    ap.add_argument("--encoding", default="utf-8", help="input.txt 编码（默认 utf-8）")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    # 解析 headers
    headers = {}
    try:
        for h in args.header:
            k, v = parse_header(h)
            headers[k] = v
    except Exception as e:
        sys.stderr.write(f"[ERROR] 解析 header 失败：{e}\n")
        sys.exit(2)

    if not in_path.exists():
        sys.stderr.write(f"[ERROR] 输入文件不存在：{in_path}\n")
        sys.exit(2)

    with in_path.open("r", encoding=args.encoding, errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip() != ""]

    n = len(lines)
    if n == 0:
        sys.stderr.write("[WARN] 输入为空：没有任何需要处理的行。\n")

    ok_with_match = 0
    ok_no_match = 0
    failed = 0
    written_rows = 0

    with out_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["input", "name", "user_id"])

        for i, q in enumerate(lines, 1):
            print(f"[{i}/{n}] 正在处理：{q}")
            try:
                url = render_template(args.url_template, q, encode=True)
                json_body = None
                data_body = None

                if args.json_template:
                    rendered = render_template(args.json_template, q, encode=False)  # JSON 内不再 URL 编码
                    try:
                        json_body = json.loads(rendered)
                    except json.JSONDecodeError as je:
                        # 模板 JSON 非法：打印请求信息与详细错误，不退出
                        log_request_info(args.method.upper(), url, headers, rendered, None)
                        sys.stderr.write(f"[ERROR] json-template 渲染后不是合法 JSON：{je}\n")
                        sys.stderr.write(f"{rendered}\n")
                        status, rows = "bad_json", [("【调用失败】", "")]
                    else:
                        text = fetch(args.method, url, headers, json_body, None, args.timeout)
                        status, rows = handle_response_text(text)
                        if status in ("no_match", "fail", "bad_json"):
                            log_request_info(args.method.upper(), url, headers, json_body, None)
                else:
                    if args.data_template:
                        data_body = render_template(args.data_template, q, encode=True)  # 对 {q} URL 编码
                    text = fetch(args.method, url, headers, None, data_body, args.timeout)
                    status, rows = handle_response_text(text)
                    if status in ("no_match", "fail", "bad_json"):
                        log_request_info(args.method.upper(), url, headers, None, data_body)

                for name, user_id in rows:
                    writer.writerow([q, name, user_id])
                    written_rows += 1

                if status == "ok":
                    ok_with_match += 1
                elif status == "no_match":
                    ok_no_match += 1
                else:
                    failed += 1

            except SystemExit:
                # fetch 已经打印错误与请求信息
                raise
            except Exception as e:
                # 其它异常（例如运行时错误）打印请求信息，视作失败，但不中断
                log_request_info(args.method.upper(), url, headers, json_body if 'json_body' in locals() else None, data_body if 'data_body' in locals() else None)
                sys.stderr.write(f"[ERROR] 行 {i} 处理异常：{e}\n")
                writer.writerow([q, "【调用失败】", ""])
                written_rows += 1
                failed += 1

    print(f"完成。总计 {n} 行，成功(有匹配) {ok_with_match}，成功(无匹配) {ok_no_match}，失败 {failed}。已写出：{out_path}")

if __name__ == "__main__":
    main()
