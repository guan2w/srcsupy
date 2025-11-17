#!/usr/bin/env python3
"""
assemble.py - 从搜索日志和快照日志生成汇总Excel文件
使用: python assemble.py --input-file=file.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2+ --snapshot-prefix="http://server/"
"""

import argparse, csv, datetime as dt, json, os, shutil
from openpyxl import load_workbook

NEW_HEADERS = ["原始行号", "关键词", "搜索时间", "搜索耗时", "搜索结果", "搜索错误",
               "快照状态", "快照错误", "链接1", "快照1", "链接2", "快照2", "链接3", "快照3"]

def load_data(input_file, sheet_name):
    """加载搜索和快照日志数据"""
    base_dir, base_name = os.path.dirname(input_file), os.path.splitext(os.path.basename(input_file))[0]

    search_data, search_path = {}, os.path.join(base_dir, f"{base_name}.search.csv")
    if os.path.exists(search_path):
        with open(search_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("sheet") == sheet_name and row.get("keywords"):
                    search_data[row["keywords"].strip()] = {
                        "search_time": row.get("search_time", ""),
                        "search_duration_ms": int(row.get("search_duration_ms", 0)),
                        "search_result_json": row.get("search_result_json", ""),
                        "search_error": row.get("search_error", ""),
                        "urls": [row.get(f"url{i}", "") for i in range(1, 4)]
                    }

    snapshot_data, snapshot_path = {}, os.path.join(base_dir, f"{base_name}.snapshot.csv")
    if os.path.exists(snapshot_path):
        with open(snapshot_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("url"):
                    snapshot_data[row["url"]] = {
                        "snapshot_path": row.get("snapshot_path", ""),
                        "snapshot_error": row.get("snapshot_error", "")
                    }

    print(f"加载了 {len(search_data)} 条搜索记录，{len(snapshot_data)} 条快照记录")
    return search_data, snapshot_data

def parse_search_columns(spec):
    """解析搜索列配置"""
    result = []
    for token in spec.split(","):
        token = token.strip()
        if not token: continue
        exact = token.endswith("*")
        col_letters = token[:-1] if exact else token
        col_index = sum((ord(c) - ord('A') + 1) * (26 ** i) for i, c in enumerate(reversed(col_letters.upper())))
        result.append((col_index, exact))
    return result

def build_keywords(ws, row_idx, columns_spec):
    """从Excel行构建关键词"""
    parts = []
    for col_index, exact in columns_spec:
        value = ws.cell(row=row_idx, column=col_index).value
        if value is None: continue
        s = str(value).replace("\n", " ").strip()
        if not s: continue
        parts.append(f'"{s}"' if exact else s)
    return " ".join(parts).strip()

def calculate_snapshot_status(search_result_json, urls, snapshot_data):
    """计算快照状态"""
    try:
        results = json.loads(search_result_json) if search_result_json else []
        expected_count = min(len(results), 3)
    except:
        expected_count = 0

    if expected_count == 0: return "0/0", "搜索无结果"

    successful_count, errors = 0, []
    for url in urls[:expected_count]:
        if not url: continue
        snap_info = snapshot_data.get(url)
        if snap_info and snap_info.get("snapshot_path") and not snap_info.get("snapshot_error"):
            successful_count += 1
        elif snap_info and snap_info.get("snapshot_error"):
            errors.append(f"{url}: {snap_info['snapshot_error']}")
        else:
            errors.append(f"{url}: 尚未快照")

    return f"{successful_count}/{expected_count}", "\n".join(errors) if errors else ""

def parse_rows_range(spec, max_row):
    """解析行范围"""
    if spec.endswith("+"):
        start_row = int(spec[:-1])
        end_row = max_row
    else:
        parts = spec.split("-", 1)
        start_row, end_row = int(parts[0]), int(parts[1])
    return start_row, min(end_row, max_row)

def main():
    parser = argparse.ArgumentParser(description="综合日志生成汇总 Excel 文件")
    parser.add_argument("--input-file", required=True, help="输入 Excel 文件路径")
    parser.add_argument("--sheet", required=True, help="Sheet 名称")
    parser.add_argument("--search-columns", required=True, help="搜索列设置，例如 C*,D")
    parser.add_argument("--rows", required=True, help="行范围，例如 3+ 或 3-9")
    parser.add_argument("--snapshot-prefix", required=True, help="快照文件路径前缀")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")

    args = parser.parse_args()
    global DEBUG
    DEBUG = args.debug

    input_file = os.path.abspath(args.input_file)
    if not os.path.exists(input_file):
        print(f"错误：输入文件不存在: {input_file}")
        return

    # 打印配置
    print("=" * 70)
    print("配置信息")
    print(f"  输入文件: {input_file}")
    print(f"  Sheet: {args.sheet}")
    print(f"  搜索列: {args.search_columns}")
    print(f"  行范围: {args.rows}")
    print(f"  快照前缀: {args.snapshot_prefix}")
    print("=" * 70)

    # 加载输入文件
    input_wb = load_workbook(input_file, read_only=True, data_only=True)
    if args.sheet not in input_wb.sheetnames:
        print(f"错误：Excel 中未找到 sheet: {args.sheet}")
        return
    input_ws = input_wb[args.sheet]

    # 解析参数
    columns_spec = parse_search_columns(args.search_columns)
    start_row, end_row = parse_rows_range(args.rows, input_ws.max_row)
    data_row_count = end_row - start_row + 1

    print(f"解析搜索列: {columns_spec}")
    print(f"处理行范围: {start_row}-{end_row} (共 {data_row_count} 行)")

    # 加载数据
    search_data, snapshot_data = load_data(input_file, args.sheet)

    # 创建输出文件
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    timestamp = dt.datetime.now().strftime("%y%m%d.%H%M%S")
    output_filename = f"{base_name}-{data_row_count}-{timestamp}.xlsx"
    output_path = os.path.join(os.path.dirname(input_file), output_filename)

    shutil.copy2(input_file, output_path)
    print(f"已复制输入文件到: {output_path}")

    # 处理输出文件
    output_wb = load_workbook(output_path)
    output_ws = output_wb[args.sheet]

    # 添加新列标题
    last_col = output_ws.max_column
    for i, header in enumerate(NEW_HEADERS, 1):
        output_ws.cell(row=1, column=last_col + i, value=header)

    col_offset = last_col + 1
    processed_count = matched_count = 0

    print(f"开始处理 {data_row_count} 行数据...")

    # 处理每一行
    for row_idx in range(start_row, end_row + 1):
        processed_count += 1
        keywords = build_keywords(input_ws, row_idx, columns_spec)

        if DEBUG: print(f"第 {row_idx} 行关键词: '{keywords}'")

        search_info = search_data.get(keywords)
        if not search_info:
            print(f"警告：第 {row_idx} 行关键词 '{keywords}' 未找到匹配记录")
            output_ws.cell(row=row_idx, column=col_offset, value=row_idx)
            continue

        matched_count += 1

        # 处理搜索结果
        search_error = search_info["search_error"]
        search_result_json = search_info["search_result_json"]
        if not search_error and not search_result_json:
            search_error = "搜索成功但无结果"

        # 计算快照状态
        snapshot_status, snapshot_errors = calculate_snapshot_status(
            search_result_json, search_info["urls"], snapshot_data)

        # 生成快照路径
        snapshot_paths = {}
        for i, url in enumerate(search_info["urls"]):
            if url and snapshot_data.get(url, {}).get("snapshot_path"):
                snapshot_paths[f"snapshot_path_{i}"] = snapshot_data[url]["snapshot_path"]

        # 填充数据
        row_data = {
            "row_number": row_idx, "keywords": keywords,
            "search_time": search_info["search_time"],
            "search_duration_ms": search_info["search_duration_ms"],
            "search_result_json": search_result_json, "search_error": search_error,
            "snapshot_status": snapshot_status, "snapshot_errors": snapshot_errors,
            "urls": search_info["urls"], **snapshot_paths
        }

        # 写入数据
        output_ws.cell(row=row_idx, column=col_offset, value=row_data["row_number"])
        output_ws.cell(row=row_idx, column=col_offset + 1, value=row_data["keywords"])
        output_ws.cell(row=row_idx, column=col_offset + 2, value=row_data["search_time"])
        output_ws.cell(row=row_idx, column=col_offset + 3, value=row_data["search_duration_ms"])
        output_ws.cell(row=row_idx, column=col_offset + 4, value=row_data["search_result_json"])
        output_ws.cell(row=row_idx, column=col_offset + 5, value=row_data["search_error"])
        output_ws.cell(row=row_idx, column=col_offset + 6, value=row_data["snapshot_status"])
        output_ws.cell(row=row_idx, column=col_offset + 7, value=row_data["snapshot_errors"])

        # 链接和快照
        for i, url in enumerate(row_data["urls"]):
            if url:
                output_ws.cell(row=row_idx, column=col_offset + 8 + i*2, value=url)
                if f"snapshot_path_{i}" in snapshot_paths:
                    full_path = args.snapshot_prefix + snapshot_paths[f"snapshot_path_{i}"]
                    output_ws.cell(row=row_idx, column=col_offset + 9 + i*2, value=full_path)

    # 调整列宽
    for col_num in range(col_offset, col_offset + 15):
        col_letter = output_ws.cell(row=1, column=col_num).column_letter
        width = 50 if col_num >= col_offset + 9 else (30 if col_num == col_offset + 7 else
                (10 if col_num in [col_offset, col_offset + 6] else 15))
        output_ws.column_dimensions[col_letter].width = width

    # 保存
    output_wb.save(output_path)
    output_wb.close()
    input_wb.close()

    print(f"输出文件已保存: {output_path}")
    print("[成功] 已添加 14 个新列，列宽已自动调整")
    print("[提示] 在Excel中如看不到新列，请尝试：")
    print("   1. 使用水平滚动条滚动到右侧")
    print("   2. 选择所有列，右键→列宽→设置为合适值")
    print(f"   3. 新增列从第{col_offset}列开始")

    print("\n" + "=" * 70)
    print("处理完成")
    print(f"  处理数据行数: {data_row_count}")
    print(f"  找到匹配记录: {matched_count}")
    print(f"  未匹配行数: {data_row_count - matched_count}")
    print("=" * 70)

if __name__ == "__main__":
    main()
