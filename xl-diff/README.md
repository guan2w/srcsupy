# Excel 工具包 (xl-diff)

够用的 Excel 工具包，Python 编写，包含以下功能：

1. 打印多行表头
2. 对比 sheets 内容差异

## 🚀 功能特性

- 🔍 **多行表头支持**: 支持读取和处理 Excel 中的多行表头，包括合并单元格
- 🔄 **高效数据比较**: 快速比较两个 Excel 文件的数据差异，支持大数据量处理（10万行+）
- 📊 **详细差异报告**: 自动生成包含新增、删除、修改数据的详细 Excel 报告
- ⚡ **高性能引擎**: 支持多种读取引擎（calamine/openpyxl），优化大数据处理性能
- 🎯 **灵活配置**: 支持自定义唯一键、工作表名称、表头行号等参数
- 📋 **命令行界面**: 简单易用的命令行工具，支持多种使用场景

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

依赖项包括：
- pandas>=2.0.0
- numpy>=1.26.0,<2.0
- xlsxwriter>=3.0.0
- python-calamine>=0.3.2
- openpyxl>=3.1.0

## 🛠️ 工具说明

### 1. 打印多行表头 (show_excel_headers.py)

读取 Excel 文件的指定多行表头，并以路径格式打印。

#### 使用方法

```bash
python show_excel_headers.py <file_path> [--sheet <sheet_name>] [--rows <header_rows>]
```

#### 参数说明

- `file_path`: Excel 文件的路径
- `--sheet` / `-s`: 工作表名称 (默认: Sheet1)
- `--rows` / `-r`: 表头行数 (默认: 3)

#### 使用示例

```bash
# 读取 sample.xlsx 文件的 Sheet1 表的前3行表头
python show_excel_headers.py sample.xlsx

# 读取 sample.xlsx 文件的 Data 表的前5行表头
python show_excel_headers.py sample.xlsx --sheet Data --rows 5
```

### 2. 对比 Sheets 内容差异 (compare_sheets.py)

高效比较两个 Excel 文件中的数据差异，支持大数据量处理。

#### 使用方法

```bash
python compare_sheets.py <file1> <file2> -k <key_columns> [options]
```

#### 参数说明

- `file1`: 第一个 Excel 文件路径
- `file2`: 第二个 Excel 文件路径
- `-k` / `--keys`: 一个或多个作为唯一键的列名
- `-s1` / `--sheet1`: 文件1的工作表名称 (默认为第一个Sheet)
- `-s2` / `--sheet2`: 文件2的工作表名称 (默认为第一个Sheet)
- `--header1`: 文件1的表头行号 (默认为1)
- `--header2`: 文件2的表头行号 (默认为1)
- `-o` / `--output`: 差异报告输出路径 (默认: comparison_report.xlsx)
- `--engine`: 读取Excel的引擎 (可选: auto/calamine/openpyxl，默认: auto)
- `-i` / `--ignore-columns`: 一个或多个在比较时忽略的列名
- `--demo`: 创建示例文件并运行演示

#### 使用示例

```bash
# 基本用法：比较两个文件，以"员工ID"作为唯一键
python compare_sheets.py file1.xlsx file2.xlsx -k "员工ID"

# 指定工作表和多个唯一键
python compare_sheets.py v1.xlsx v2.xlsx -k "姓名" "部门" -s1 "Sheet1" -s2 "数据" -o "报告.xlsx"

# 指定表头行号
python compare_sheets.py file1.xlsx file2.xlsx -k "ID" --header1 3 --header2 5

# 运行演示
python compare_sheets.py --demo

# 比较时忽略某些列
python compare_sheets.py file1.xlsx file2.xlsx -k "ID" -i "更新时间" "备注"
```

## 📊 输出报告说明

当发现差异时，工具会生成一个 Excel 报告文件，包含以下工作表：

1. **差异总览**: 比较的基本信息和统计结果
2. **新增的行**: 在新文件中存在但在旧文件中不存在的行
3. **删除的行**: 在旧文件中存在但在新文件中不存在的行
4. **修改的详情**: 详细列出发生变化的单元格信息

## 💡 使用技巧

1. **选择合适的唯一键**: 确保指定的唯一键能够唯一标识每一行数据
2. **处理大数据**: 对于超过10万行的数据，建议使用 calamine 引擎以获得更好的性能
3. **忽略动态列**: 对于经常变化但不影响业务逻辑的列（如时间戳），可以使用 `--ignore-columns` 参数忽略
4. **表头处理**: 如果 Excel 文件使用了多行表头，请正确指定 `--header1` 和 `--header2` 参数

## 📁 项目结构

```
xl-diff/
├── show_excel_headers.py      # 打印多行表头工具
├── compare_sheets.py          # Excel 文件比较工具
├── requirements.txt           # 依赖列表
├── README.md                 # 项目说明文档
└── sample files              # 示例文件（运行 --demo 时生成）
```