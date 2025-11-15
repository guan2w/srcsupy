import pandas as pd
import openpyxl
from collections import defaultdict
import argparse


def print_excel_headers(file_path, sheet_name, header_rows):
    """
    读取 Excel 文件的指定多行表头，并以路径格式打印。

    Args:
        file_path (str): Excel 文件的路径。
        sheet_name (str): 要读取的工作表名称。
        header_rows (int): 表头的行数 (例如, 3 表示前三行为表头)。
    """
    try:
        # 1. 使用 openpyxl 加载工作簿以获取合并单元格信息
        workbook = openpyxl.load_workbook(file_path)
        sheet = workbook[sheet_name]

        # 2. 读取指定范围的表头数据
        # header_rows 是表头所占的行数，我们只读取这部分
        df_header = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=None,
            nrows=header_rows
        )

        # 将 NaN 值替换为空字符串，方便处理
        df_header = df_header.fillna('')

        # 3. 处理合并单元格
        # 创建一个与 df_header 形状相同的副本，用于填充合并后的值
        header_values = df_header.copy()

        # 获取所有合并单元格的范围
        merged_cells = sheet.merged_cells.ranges

        for merged_range in merged_cells:
            # 获取合并区域的边界 (min_row, min_col, max_row, max_col)
            # openpyxl 的行列号从 1 开始，pandas 从 0 开始，需要转换
            min_col, min_row, max_col, max_row = merged_range.bounds

            # 我们只关心表头区域内的合并
            if max_row > header_rows:
                continue

            # 获取合并单元格左上角的值
            top_left_value = header_values.iloc[min_row - 1, min_col - 1]

            # 将该值填充到整个合并区域
            for row in range(min_row - 1, max_row):
                for col in range(min_col - 1, max_col):
                    header_values.iloc[row, col] = top_left_value

        # 4. 向下填充，处理非合并单元格产生的空值
        header_values = header_values.ffill()

        # 5. 生成最终的表头列表
        final_headers = []
        for col in header_values.columns:
            # 将每一列的多行表头用 '/' 连接起来
            column_header = "/".join(header_values[col].astype(str))
            final_headers.append(column_header)

        print("--- 表头列表 ---")
        for i, header in enumerate(final_headers):
            print(f"第 {i + 1} 列: {header}")

    except FileNotFoundError:
        print(f"错误：文件 '{file_path}' 未找到。")
    except Exception as e:
        print(f"发生错误：{e}")


def parse_arguments():
    """
    解析命令行参数
    """
    parser = argparse.ArgumentParser(description='读取 Excel 文件的表头信息')
    parser.add_argument('file_path', help='Excel 文件的路径')
    parser.add_argument('--sheet', '-s', default='Sheet1',
                      help='工作表名称 (默认: Sheet1)')
    parser.add_argument('--rows', '-r', type=int, default=3,
                      help='表头行数 (默认: 3)')
    return parser.parse_args()


if __name__ == '__main__':
    # 解析命令行参数
    args = parse_arguments()
    
    # 运行主函数
    print("=" * 20 + " 开始读取表头 " + "=" * 20)
    print_excel_headers(args.file_path, args.sheet, args.rows)