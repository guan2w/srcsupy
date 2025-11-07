#!/usr/bin/env python3
"""
数据整合工具 - combine_extracted.py

将提取结果汇总到 Excel 文件中，支持多 URL 列、失败记录、状态标注等功能。
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
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


# ========== 工具函数 ==========

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


# ========== 数据读取 ==========

def read_journal_data(
    excel_path: Path,
    sheet_name: Any,
    name_column: str,
    url_columns: List[str],
    start_row: int,
    end_row: Optional[int]
) -> List[Dict[str, Any]]:
    """
    从 Excel 文件读取期刊名称和 URL
    
    Returns:
        期刊数据列表，每项包含 journal_name 和 urls
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
            excel_path,
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
    journals = []
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
        urls = []
        for col_idx in url_col_indices:
            url = row[col_idx]
            if pd.notna(url):
                url_str = str(url).strip()
                # 过滤无效 URL
                if url_str.startswith('http://') or url_str.startswith('https://'):
                    urls.append(url_str)
        
        # 对 URL 去重（保持顺序）
        seen_urls = set()
        unique_urls = []
        for url in urls:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_urls.append(url)
        
        journals.append({
            'journal_name': str(name).strip(),
            'urls': unique_urls
        })
    
    # 打印实际读取范围
    if end_row is None:
        print(f"[INFO] 实际读取行范围: {start_row}-{actual_end_row}")
    
    return journals


def load_snapshot_log(snapshot_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    加载快照日志
    
    Returns:
        {hash: {url, status, snapshot_time, error_type, error_message}}
    """
    log_file = snapshot_dir / "snapshot-log.csv"
    snapshot_data = {}
    
    if not log_file.exists():
        return snapshot_data
    
    try:
        with open(log_file, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                hash_value = row['hash']
                snapshot_data[hash_value] = {
                    'url': row['url'],
                    'status': row['status'],
                    'snapshot_time': row.get('snapshot_time', ''),
                    'error_type': row.get('error_type', ''),
                    'error_message': row.get('error_message', '')
                }
    except Exception as e:
        print(f"[WARNING] Failed to load snapshot log: {e}", file=sys.stderr)
    
    return snapshot_data


def load_extract_log(snapshot_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    加载提取日志
    
    Returns:
        {hash: {status, institutions_count, extract_time, error_type, error_message}}
    """
    log_file = snapshot_dir / "extract-log.csv"
    extract_data = {}
    
    if not log_file.exists():
        return extract_data
    
    try:
        with open(log_file, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                hash_value = row['hash']
                extract_data[hash_value] = {
                    'status': row['status'],
                    'institutions_count': int(row.get('institutions_count', 0)),
                    'extract_time': row.get('extract_time', ''),
                    'error_type': row.get('error_type', ''),
                    'error_message': row.get('error_message', '')
                }
    except Exception as e:
        print(f"[WARNING] Failed to load extract log: {e}", file=sys.stderr)
    
    return extract_data


def get_hash_path(snapshot_dir: Path, url_hash: str) -> Path:
    """获取 hash 分层目录路径"""
    return snapshot_dir / url_hash[:2] / url_hash[2:4] / url_hash[4:]


def load_host_json(snapshot_dir: Path, url_hash: str) -> Optional[Dict[str, Any]]:
    """
    加载 host.json 文件（支持新旧格式）
    
    优先级：
    1. host-langextract.json（langextract 方法结果）
    2. host-regexp.json（regexp 方法结果）
    
    Returns:
        host_institutions 列表，如果不存在返回 None
    """
    hash_path = get_hash_path(snapshot_dir, url_hash)
    
    # 按优先级尝试读取
    json_files = [
        hash_path / "host-langextract.json",
        hash_path / "host-regexp.json",
    ]
    
    for json_file in json_files:
        if json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('host_institutions', [])
            except Exception as e:
                print(f"[WARNING] Failed to load {json_file}: {e}", file=sys.stderr)
                continue
    
    return None


# ========== 数据整合 ==========

def determine_status(
    url: str,
    snapshot_data: Dict[str, Dict[str, Any]],
    extract_data: Dict[str, Dict[str, Any]],
    institutions: Optional[List[Dict[str, Any]]]
) -> str:
    """
    根据各阶段状态判断最终处理状态
    
    Returns:
        状态字符串：待快照、快照失败、待提取、提取失败、无匹配、成功
    """
    url_hash = sha1_hex(url)
    
    # 优先检查 host.json 是否存在（institutions 不为 None 说明文件存在）
    if institutions is not None:
        # host.json 存在，根据内容判断
        if len(institutions) == 0:
            return "无匹配"
        else:
            return "成功"
    
    # host.json 不存在，检查各阶段状态
    # 检查快照状态
    if url_hash not in snapshot_data:
        return "待快照"
    
    snapshot_status = snapshot_data[url_hash]['status']
    if snapshot_status != 'success':
        error_type = snapshot_data[url_hash].get('error_type', 'unknown')
        return f"快照失败 ({error_type})"
    
    # 快照成功但 host.json 不存在，检查提取状态
    if url_hash not in extract_data:
        return "待提取"
    
    extract_status = extract_data[url_hash]['status']
    if extract_status != 'success':
        error_type = extract_data[url_hash].get('error_type', 'unknown')
        return f"提取失败 ({error_type})"
    
    # 提取成功但 host.json 不存在（异常情况）
    return "数据缺失"


def combine_data(
    journals: List[Dict[str, Any]],
    snapshot_dir: Path,
    snapshot_data: Dict[str, Dict[str, Any]],
    extract_data: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    整合所有数据
    
    Returns:
        输出行列表，每行包含：
        - 期刊名称
        - 来源链接
        - 匹配机构
        - 匹配关键词
        - 匹配句子
        - 提取方法
        - 链接hash
    """
    output_rows = []
    
    for journal in journals:
        journal_name = journal['journal_name']
        urls = journal['urls']
        
        # 如果期刊没有 URL，输出一行
        if not urls:
            output_rows.append({
                '期刊名称': journal_name,
                '来源链接': '',
                '匹配机构': '无URL',
                '匹配关键词': '',
                '匹配句子': '',
                '提取方法': '',
                '链接hash': ''
            })
            continue
        
        # 处理每个 URL
        for url in urls:
            url_hash = sha1_hex(url)
            
            # 加载机构数据
            institutions = load_host_json(snapshot_dir, url_hash)
            
            # 判断状态
            status = determine_status(url, snapshot_data, extract_data, institutions)
            
            # 如果提取成功且有机构，每个机构一行
            if status == "成功" and institutions:
                for inst in institutions:
                    output_rows.append({
                        '期刊名称': journal_name,
                        '来源链接': url,
                        '匹配机构': inst.get('name', ''),
                        '匹配关键词': inst.get('matched_keyword', ''),
                        '匹配句子': inst.get('source_sentence', ''),
                        '提取方法': inst.get('extraction_method', ''),
                        '链接hash': url_hash
                    })
            else:
                # 失败或无数据，输出一行标注状态
                output_rows.append({
                    '期刊名称': journal_name,
                    '来源链接': url,
                    '匹配机构': status,
                    '匹配关键词': '',
                    '匹配句子': '',
                    '提取方法': '',
                    '链接hash': url_hash
                })
    
    return output_rows


# ========== 输出 Excel ==========

def write_output_excel(output_rows: List[Dict[str, Any]], output_file: Path):
    """将数据写入 Excel 文件"""
    try:
        from openpyxl.styles import Border, Side
        
        df = pd.DataFrame(output_rows)
        
        # 确保输出目录存在
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入 Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='提取结果')
            
            # 获取工作表
            worksheet = writer.sheets['提取结果']
            
            # 冻结表头行（第一行）
            worksheet.freeze_panes = 'A2'
            
            # 去除表头边框
            no_border = Border(
                left=Side(style=None),
                right=Side(style=None),
                top=Side(style=None),
                bottom=Side(style=None)
            )
            
            # 遍历表头行（第一行）的所有单元格，去除边框
            for cell in worksheet[1]:
                cell.border = no_border
            
            # 调整列宽
            for idx, col in enumerate(df.columns, 1):
                # 根据列内容长度调整宽度
                if col in ['匹配句子']:
                    worksheet.column_dimensions[chr(64 + idx)].width = 60
                elif col in ['匹配机构', '来源链接']:
                    worksheet.column_dimensions[chr(64 + idx)].width = 40
                elif col in ['链接hash']:
                    worksheet.column_dimensions[chr(64 + idx)].width = 45
                else:
                    worksheet.column_dimensions[chr(64 + idx)].width = 15
        
        print(f"[OK] 输出文件已保存: {output_file}")
        print(f"     总行数: {len(output_rows)}")
        
    except Exception as e:
        print(f"[ERROR] Failed to write output Excel: {e}", file=sys.stderr)
        sys.exit(1)


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(
        description="数据整合工具 - 将提取结果汇总到 Excel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python combine_extracted.py \\
    --input-excel journals.xlsx \\
    --sheet-name 0 \\
    --name-column A \\
    --url-columns D,F \\
    --rows 4+

  python combine_extracted.py \\
    --input-excel journals.xlsx \\
    --name-column A \\
    --url-columns D \\
    --rows 4-99
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
        '--url-columns',
        required=True,
        help='URL 列（多列用逗号分隔），如 "D,F"'
    )
    parser.add_argument(
        '--rows',
        required=True,
        help='行范围，如 "4+" 或 "4-99"'
    )
    
    args = parser.parse_args()
    
    # 打印配置参数
    print("=" * 60)
    print("[CONFIG] 数据整合工具 - 启动参数")
    print("=" * 60)
    print(f"Excel 文件:    {args.input_excel}")
    print(f"Sheet 名称:    {args.sheet_name}")
    print(f"期刊名称列:    {args.name_column}")
    print(f"URL 列:        {args.url_columns}")
    print(f"行范围:        {args.rows}")
    print("=" * 60)
    print()
    
    # 检查 Excel 文件
    excel_path = Path(args.input_excel)
    if not excel_path.exists():
        print(f"[ERROR] Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)
    
    # 确定快照目录
    snapshot_dir = excel_path.parent / f"{excel_path.stem}-snapshot"
    if not snapshot_dir.exists():
        print(f"[ERROR] Snapshot directory not found: {snapshot_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"[INFO] 快照目录: {snapshot_dir}")
    
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
    
    # 读取期刊数据
    print(f"[COMBINE] 读取 Excel 数据...")
    journals = read_journal_data(
        excel_path,
        sheet_name,
        args.name_column,
        url_columns,
        start_row,
        end_row
    )
    
    print(f"[COMBINE] 读取到 {len(journals)} 个期刊")
    total_urls = sum(len(j['urls']) for j in journals)
    print(f"[COMBINE] 共 {total_urls} 个 URL")
    
    # 加载日志数据
    print(f"[COMBINE] 加载快照日志...")
    snapshot_data = load_snapshot_log(snapshot_dir)
    print(f"[COMBINE] 快照记录: {len(snapshot_data)} 个")
    
    print(f"[COMBINE] 加载提取日志...")
    extract_data = load_extract_log(snapshot_dir)
    print(f"[COMBINE] 提取记录: {len(extract_data)} 个")
    
    # 整合数据
    print(f"[COMBINE] 整合数据...")
    output_rows = combine_data(journals, snapshot_dir, snapshot_data, extract_data)
    
    # 生成输出文件名
    timestamp = datetime.now().strftime("%y%m%d.%H%M%S")
    output_filename = f"{excel_path.name}-output-{timestamp}.xlsx"
    output_file = snapshot_dir / output_filename
    
    # 写入 Excel
    print(f"[COMBINE] 写入输出文件...")
    write_output_excel(output_rows, output_file)
    
    # 统计信息
    success_count = sum(1 for row in output_rows if row['匹配机构'] not in ['待快照', '待提取', '无匹配', '无URL'] and not row['匹配机构'].startswith('快照失败') and not row['匹配机构'].startswith('提取失败'))
    failed_count = len(output_rows) - success_count
    
    print(f"\n[OK] 整合完成")
    print(f"     成功提取: {success_count} 行")
    print(f"     失败/待处理: {failed_count} 行")
    print(f"     输出文件: {output_file}")


if __name__ == "__main__":
    main()

