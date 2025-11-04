
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 从 input.txt 读取每一行作为查询参数，逐行调用一个 curl 命令，解析返回的 JSON：
# - 当 code == 0 时，从 data.users[*].name / user_id 提取结果；
# - 若 data.users 为空，则输出一行，name 填【无匹配】，user_id 为空；
# - 若 code != 0 或解析失败/命令失败，则输出一行，name 填【调用失败】，并在 stderr 打印错误详情；
# 输出 CSV 列为：input, name, user_id
# 使用方式（示例）：
#   python batch_curl_to_csv.py \

#       --curl-template "curl -s 'https://api.example.com/search?q={q}' -H 'Authorization: Bearer XXX'" \

#       --input input.txt --output output.csv
# 说明：
# - --curl-template 中用 {q} 作为占位符，脚本会对每一行的输入做 shell 安全转义后替换进去；
# - 若接口需要 POST 或更多 header/数据，请把完整 curl 命令写入 --curl-template，并同样用 {q} 占位；
# - 脚本默认顺序执行（逐行调用）。

import argparse
import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path

def run_curl(curl_template: str, q: str) -> str:
    # 使用 shlex.quote 做 shell 安全转义，再替换到模板中
    safe_q = shlex.quote(q)
    cmd = curl_template.replace("{q}", safe_q)
    # 执行命令
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"curl 命令失败，退出码={proc.returncode}, stderr={proc.stderr.strip()}")
    return proc.stdout

def parse_users(json_text: str):
    try:
        obj = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"返回内容不是合法 JSON：{e}")
    # 允许 code 是数字或字符串（尽量兼容）
    code = obj.get("code")
    try:
        code_int = int(code)
    except Exception:
        code_int = None

    if code_int == 0:
        data = obj.get("data", {})
        users = data.get("users", [])
        if not isinstance(users, list):
            users = []
        # 归一化输出
        rows = []
        if users:
            for u in users:
                if not isinstance(u, dict):
                    continue
                name = u.get("name", "")
                user_id = u.get("user_id", "")
                rows.append((name, user_id))
        else:
            rows.append(("【无匹配】", ""))
        return True, rows  # (成功标志, [(name, user_id), ...])
    else:
        # 非 0 认为失败，尽量取出 message 便于调试
        msg = obj.get("message") or obj.get("msg") or ""
        raise RuntimeError(f"接口返回非零 code（code={code}）：{msg}")

def main():
    parser = argparse.ArgumentParser(description="逐行调用 curl，解析 JSON，写出 output.csv")
    parser.add_argument("--input", default="input.txt", help="输入文件（每行一个查询）")
    parser.add_argument("--output", default="output.csv", help="输出 CSV 文件路径")
    parser.add_argument("--curl-template", required=True, help="curl 命令模板，使用 {q} 作为占位符")
    parser.add_argument("--encoding", default="utf-8", help="输入文件编码（默认 utf-8）")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        print(f"[ERROR] 输入文件不存在：{in_path}", file=sys.stderr)
        sys.exit(2)

    # 读取所有输入行（去掉空行与首尾空白）
    with in_path.open("r", encoding=args.encoding, errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip() != ""]

    if not lines:
        print("[WARN] 输入为空：没有任何需要处理的行。", file=sys.stderr)

    # 写出 CSV，带表头
    with out_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["input", "name", "user_id"])

        for i, q in enumerate(lines, 1):
            try:
                stdout = run_curl(args.curl_template, q)
                ok, rows = parse_users(stdout)
                for name, user_id in rows:
                    writer.writerow([q, name, user_id])
            except Exception as e:
                # 失败情况下也写一行，方便回溯
                writer.writerow([q, "【调用失败】", ""])
                print(f"[ERROR] 第 {i} 行（input='{q}'）处理失败：{e}", file=sys.stderr)

    print(f"完成。已写出：{out_path}")

if __name__ == "__main__":
    main()
