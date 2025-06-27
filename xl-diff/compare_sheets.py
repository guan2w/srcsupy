#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel Sheet 比较工具
高效比较两个Excel文件中的数据差异，支持大数据量处理（10万行+）

作者: AI Assistant
版本: 1.0
"""

import argparse
import pandas as pd
import numpy as np
import sys
from datetime import datetime
from pathlib import Path
import warnings

# 忽略pandas的一些警告信息，保持输出清洁
warnings.filterwarnings('ignore', category=UserWarning)


class ExcelComparator:
    """Excel文件比较器类"""
    
    def __init__(self, file1_path, file2_path, key_columns, 
                 sheet1_name=None, sheet2_name=None, 
                 output_path="comparison_report.xlsx", 
                 engine="auto"):
        """
        初始化比较器
        
        Args:
            file1_path (str): 第一个Excel文件路径
            file2_path (str): 第二个Excel文件路径  
            key_columns (list): 用作唯一键的列名列表
            sheet1_name (str, optional): 第一个文件的Sheet名
            sheet2_name (str, optional): 第二个文件的Sheet名
            output_path (str): 输出报告文件路径
            engine (str): pandas读取引擎
        """
        self.file1_path = Path(file1_path)
        self.file2_path = Path(file2_path)
        self.key_columns = key_columns
        self.sheet1_name = sheet1_name
        self.sheet2_name = sheet2_name
        self.output_path = Path(output_path)
        self.engine = engine
        
        # 比较结果存储
        self.df1 = None
        self.df2 = None
        self.added_df = None
        self.deleted_df = None
        self.modified_df = None
        self.comparison_time = datetime.now()
        
    def _determine_engine(self):
        """确定最佳的pandas读取引擎"""
        if self.engine != "auto":
            return self.engine
            
        try:
            import calamine
            return "calamine"
        except ImportError:
            try:
                import openpyxl
                return "openpyxl"
            except ImportError:
                return None
    
    def _read_excel_file(self, file_path, sheet_name):
        """读取Excel文件"""
        engine = self._determine_engine()
        
        try:
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name, engine=engine)
            else:
                # 如果没有指定sheet名，读取第一个sheet
                df = pd.read_excel(file_path, engine=engine)
            
            print(f"✓ 成功读取文件: {file_path}")
            print(f"  - 数据行数: {len(df)}")
            print(f"  - 数据列数: {len(df.columns)}")
            
            return df
            
        except Exception as e:
            print(f"✗ 读取文件失败: {file_path}")
            print(f"  错误信息: {str(e)}")
            raise
    
    def _validate_key_columns(self):
        """验证唯一键列是否存在"""
        missing_cols_1 = [col for col in self.key_columns if col not in self.df1.columns]
        missing_cols_2 = [col for col in self.key_columns if col not in self.df2.columns]
        
        if missing_cols_1:
            raise ValueError(f"文件1中缺少唯一键列: {missing_cols_1}")
        if missing_cols_2:
            raise ValueError(f"文件2中缺少唯一键列: {missing_cols_2}")
    
    def _preprocess_data(self):
        """数据预处理"""
        print("正在进行数据预处理...")
        
        # 移除唯一键全为空的行
        self.df1.dropna(subset=self.key_columns, how='all', inplace=True)
        self.df2.dropna(subset=self.key_columns, how='all', inplace=True)
        
        # 设置唯一键为索引
        self.df1.set_index(self.key_columns, inplace=True)
        self.df2.set_index(self.key_columns, inplace=True)
        
        print(f"  - 文件1有效数据行数: {len(self.df1)}")
        print(f"  - 文件2有效数据行数: {len(self.df2)}")
    
    def _find_added_deleted_rows(self):
        """查找新增和删除的行"""
        print("正在分析新增和删除的行...")
        
        added_keys = self.df2.index.difference(self.df1.index)
        deleted_keys = self.df1.index.difference(self.df2.index)
        
        self.added_df = self.df2.loc[added_keys].copy() if not added_keys.empty else pd.DataFrame()
        self.deleted_df = self.df1.loc[deleted_keys].copy() if not deleted_keys.empty else pd.DataFrame()
        
        print(f"  - 新增行数: {len(self.added_df)}")
        print(f"  - 删除行数: {len(self.deleted_df)}")
    
    def _find_modified_rows(self):
        """查找修改的行"""
        print("正在分析修改的行...")
        
        # 找到共同的行和列
        common_keys = self.df1.index.intersection(self.df2.index)
        common_columns = self.df1.columns.intersection(self.df2.columns).tolist()
        
        if common_keys.empty or not common_columns:
            self.modified_df = pd.DataFrame()
            print("  - 没有共同的行或列可供比较")
            return
        
        df1_common = self.df1.loc[common_keys, common_columns].copy()
        df2_common = self.df2.loc[common_keys, common_columns].copy()
        
        # 转换为字符串进行精确比较，避免数据类型差异导致的误判
        df1_str = df1_common.astype(str).replace('nan', '')
        df2_str = df2_common.astype(str).replace('nan', '')
        
        # 找出有差异的单元格
        diff_mask = (df1_str != df2_str) & ~(df1_str.isnull() & df2_str.isnull())
        
        # 找到有任何列发生变化的行
        modified_rows_mask = diff_mask.any(axis=1)
        modified_keys = df1_common[modified_rows_mask].index
        
        if not modified_keys.empty:
            # 创建详细的修改记录
            modified_details = []
            for key in modified_keys:
                row_diff = diff_mask.loc[key]
                changed_cols = row_diff[row_diff].index.tolist()
                
                for col in changed_cols:
                    old_val = df1_common.loc[key, col]
                    new_val = df2_common.loc[key, col]
                    
                    # 构建记录
                    record = {}
                    # 添加唯一键信息
                    if isinstance(key, tuple):
                        for i, key_col in enumerate(self.key_columns):
                            record[key_col] = key[i]
                    else:
                        record[self.key_columns[0]] = key
                    
                    # 添加变化信息
                    record.update({
                        '变化的列': col,
                        '旧值': old_val,
                        '新值': new_val
                    })
                    modified_details.append(record)
            
            self.modified_df = pd.DataFrame(modified_details)
        else:
            self.modified_df = pd.DataFrame()
        
        print(f"  - 修改的行数: {len(modified_keys) if not modified_keys.empty else 0}")
        print(f"  - 修改的单元格数: {len(self.modified_df)}")
    
    def _create_summary_data(self):
        """创建总览数据"""
        # 获取实际使用的sheet名称
        sheet1_display = self.sheet1_name or "第一个Sheet"
        sheet2_display = self.sheet2_name or "第一个Sheet"
        
        has_differences = (
            not self.added_df.empty or 
            not self.deleted_df.empty or 
            not self.modified_df.empty
        )
        
        summary_data = {
            '项目': [
                '对比时间',
                '文件1 (旧)',
                '文件2 (新)',
                '唯一键',
                '对比结果',
                '新增行数',
                '删除行数',
                '修改行数'
            ],
            '内容': [
                self.comparison_time.strftime('%Y-%m-%d %H:%M:%S'),
                f"{self.file1_path.name} -> [{sheet1_display}]",
                f"{self.file2_path.name} -> [{sheet2_display}]",
                ', '.join(self.key_columns),
                '发现差异' if has_differences else '数据完全一致',
                len(self.added_df),
                len(self.deleted_df),
                len(self.modified_df.groupby(self.key_columns)) if not self.modified_df.empty else 0
            ]
        }
        
        return pd.DataFrame(summary_data)
    
    def compare(self):
        """执行比较操作"""
        print("=" * 60)
        print("Excel Sheet 数据比较工具")
        print("=" * 60)
        
        try:
            # 1. 读取文件
            print("\n1. 读取Excel文件...")
            self.df1 = self._read_excel_file(self.file1_path, self.sheet1_name)
            self.df2 = self._read_excel_file(self.file2_path, self.sheet2_name)
            
            # 2. 验证唯一键
            print("\n2. 验证唯一键...")
            self._validate_key_columns()
            print(f"✓ 唯一键验证通过: {self.key_columns}")
            
            # 3. 数据预处理
            print("\n3. 数据预处理...")
            self._preprocess_data()
            
            # 4. 查找差异
            print("\n4. 执行数据比较...")
            self._find_added_deleted_rows()
            self._find_modified_rows()
            
            # 5. 生成报告
            print("\n5. 生成差异报告...")
            self._generate_report()
            
            return True
            
        except Exception as e:
            print(f"\n✗ 比较过程中发生错误: {str(e)}")
            return False
    
    def _generate_report(self):
        """生成Excel差异报告"""
        has_differences = (
            not self.added_df.empty or 
            not self.deleted_df.empty or 
            not self.modified_df.empty
        )
        
        if not has_differences:
            print("\n🎉 恭喜！两个文件的数据完全一致，无需生成差异报告。")
            return
        
        try:
            with pd.ExcelWriter(self.output_path, engine='xlsxwriter') as writer:
                # 获取workbook和格式对象，用于美化
                workbook = writer.book
                
                # 定义一些格式
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#4472C4',
                    'font_color': 'white',
                    'border': 1
                })
                
                summary_header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#70AD47',
                    'font_color': 'white',
                    'border': 1
                })
                
                # 1. 差异总览
                summary_df = self._create_summary_data()
                summary_df.to_excel(writer, sheet_name='差异总览', index=False)
                
                worksheet = writer.sheets['差异总览']
                worksheet.set_column('A:A', 15)
                worksheet.set_column('B:B', 50)
                
                # 应用格式到总览表头
                for col_num, value in enumerate(summary_df.columns.values):
                    worksheet.write(0, col_num, value, summary_header_format)
                
                # 2. 新增的行
                if not self.added_df.empty:
                    added_output = self.added_df.reset_index()
                    added_output.to_excel(writer, sheet_name='新增的行', index=False)
                    
                    worksheet = writer.sheets['新增的行']
                    for col_num, value in enumerate(added_output.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        worksheet.set_column(col_num, col_num, 15)
                
                # 3. 删除的行
                if not self.deleted_df.empty:
                    deleted_output = self.deleted_df.reset_index()
                    deleted_output.to_excel(writer, sheet_name='删除的行', index=False)
                    
                    worksheet = writer.sheets['删除的行']
                    for col_num, value in enumerate(deleted_output.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        worksheet.set_column(col_num, col_num, 15)
                
                # 4. 修改的详情
                if not self.modified_df.empty:
                    self.modified_df.to_excel(writer, sheet_name='修改的详情', index=False)
                    
                    worksheet = writer.sheets['修改的详情']
                    for col_num, value in enumerate(self.modified_df.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        worksheet.set_column(col_num, col_num, 15)
            
            print(f"✓ 差异报告已生成: {self.output_path}")
            print(f"  - 新增行数: {len(self.added_df)}")
            print(f"  - 删除行数: {len(self.deleted_df)}")
            print(f"  - 修改行数: {len(self.modified_df.groupby(self.key_columns)) if not self.modified_df.empty else 0}")
            
        except Exception as e:
            print(f"✗ 生成报告时发生错误: {str(e)}")
            raise


def create_sample_files():
    """创建示例文件用于测试"""
    print("正在创建示例文件...")
    
    # 示例数据1
    data1 = {
        '员工ID': [101, 102, 103, 104],
        '姓名': ['张三', '李四', '王五', '赵六'],
        '部门': ['销售部', '技术部', '技术部', '人事部'],
        '薪水': [8000, 15000, 16000, 7000],
        '入职日期': ['2020-01-15', '2019-03-20', '2021-06-10', '2018-12-05']
    }
    
    # 示例数据2 (有变化)
    data2 = {
        '员工ID': [101, 102, 103, 105],  # 104删除，105新增
        '姓名': ['张三', '李四', '王五', '孙七'],
        '部门': ['销售部', '技术部', '技术部', '行政部'],
        '薪水': [8500, 15000, 18000, 9000],  # 101和103薪水变化
        '入职日期': ['2020-01-15', '2019-03-20', '2021-06-10', '2023-10-01']
    }
    
    # 创建Excel文件
    with pd.ExcelWriter('sample_v1.xlsx', engine='xlsxwriter') as writer:
        pd.DataFrame(data1).to_excel(writer, sheet_name='员工数据', index=False)
    
    with pd.ExcelWriter('sample_v2.xlsx', engine='xlsxwriter') as writer:
        pd.DataFrame(data2).to_excel(writer, sheet_name='员工数据', index=False)
    
    print("✓ 示例文件创建完成:")
    print("  - sample_v1.xlsx")
    print("  - sample_v2.xlsx")


def main():
    """主函数 - 命令行入口"""
    parser = argparse.ArgumentParser(
        description='高效比较两个Excel Sheet的数据差异',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s file1.xlsx file2.xlsx -k "员工ID"
  %(prog)s v1.xlsx v2.xlsx -k "姓名" "部门" -s1 "Sheet1" -s2 "数据" -o "报告.xlsx"
  %(prog)s --demo  # 创建示例文件并运行演示
        """
    )
    
    # 位置参数
    parser.add_argument('file1', nargs='?', help='第一个Excel文件的路径')
    parser.add_argument('file2', nargs='?', help='第二个Excel文件的路径')
    
    # 必选参数
    parser.add_argument('-k', '--keys', nargs='+', 
                       help='一个或多个作为唯一键的列名 (表头)')
    
    # 可选参数
    parser.add_argument('-s1', '--sheet1', 
                       help='文件1的工作表名称 (默认为第一个Sheet)')
    parser.add_argument('-s2', '--sheet2', 
                       help='文件2的工作表名称 (默认为第一个Sheet)')
    parser.add_argument('-o', '--output', default='comparison_report.xlsx',
                       help='差异报告输出路径 (默认: comparison_report.xlsx)')
    parser.add_argument('--engine', choices=['auto', 'calamine', 'openpyxl'], 
                       default='auto', help='读取Excel的引擎 (默认: auto)')
    
    # 演示模式
    parser.add_argument('--demo', action='store_true',
                       help='创建示例文件并运行演示')
    
    args = parser.parse_args()
    
    # 演示模式
    if args.demo:
        create_sample_files()
        print("\n" + "="*60)
        print("运行演示比较...")
        print("="*60)
        
        comparator = ExcelComparator(
            file1_path='sample_v1.xlsx',
            file2_path='sample_v2.xlsx',
            key_columns=['员工ID'],
            sheet1_name='员工数据',
            sheet2_name='员工数据',
            output_path='demo_report.xlsx'
        )
        
        success = comparator.compare()
        if success:
            print(f"\n🎉 演示完成！请查看生成的报告文件: demo_report.xlsx")
        return
    
    # 正常模式 - 验证参数
    if not args.file1 or not args.file2:
        parser.error("必须提供两个Excel文件路径，或使用 --demo 运行演示")
    
    if not args.keys:
        parser.error("必须指定至少一个唯一键列名 (-k/--keys)")
    
    # 检查文件是否存在
    for file_path in [args.file1, args.file2]:
        if not Path(file_path).exists():
            print(f"✗ 文件不存在: {file_path}")
            sys.exit(1)
    
    # 执行比较
    comparator = ExcelComparator(
        file1_path=args.file1,
        file2_path=args.file2,
        key_columns=args.keys,
        sheet1_name=args.sheet1,
        sheet2_name=args.sheet2,
        output_path=args.output,
        engine=args.engine
    )
    
    success = comparator.compare()
    
    if success:
        print(f"\n🎉 比较完成！")
    else:
        print(f"\n❌ 比较失败，请检查错误信息。")
        sys.exit(1)


if __name__ == '__main__':
    main()
