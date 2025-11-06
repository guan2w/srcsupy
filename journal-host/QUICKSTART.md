# 批量处理工具 - 快速开始指南

## 📦 安装依赖

```bash
# 切换到项目目录
cd journal-host

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

---

## ⚙️ 配置文件

编辑 `config.toml` 配置参数：

```toml
[snapshot]
headless = false              # 是否无头模式
proxy = "socks5://172.24.128.1:7890"  # 代理设置
timeout = 60000               # 页面加载超时（毫秒）
wait_after_idle = 0           # 网络空闲后额外等待（毫秒）
parallel = 3                  # 并行下载数量

[extract]
parallel = 2                  # 并行提取数量
model_id = "qwen3-vl-32b-instruct"  # 默认模型
retry_times = 3               # 失败重试次数
retry_delay = 5               # 重试延迟（秒）
watch_interval = 30           # watch 模式扫描间隔（秒）

[api]
# API 配置（可选，也可以通过环境变量或命令行参数指定）
# api_key = "sk-xxx"
# api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

---

## 🚀 使用流程

### Step 1: 批量下载快照

准备一个 Excel 文件（如 `journals.xlsx`），包含期刊名称和网站 URL。

```bash
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

**参数说明：**
- `--url-excel`: Excel 文件路径
- `--name-column`: 期刊名称所在列（如 A 列）
- `--url-columns`: URL 所在列（多列用逗号分隔，如 D,F）
- `--rows`: 行范围
  - `4+`: 从第 4 行开始，遇到空行停止
  - `4-99`: 读取第 4 到 99 行
- `--sheet-name`: （可选）Sheet 名称或索引，默认 0（第一个 sheet）
- `--parallel`: （可选）并行数量，覆盖配置文件

**启动时会打印关键参数方便排错：**
```
============================================================
[CONFIG] 批量快照下载工具 - 启动参数
============================================================
Excel 文件:    journals.xlsx
Sheet 名称:    0
期刊名称列:    A
URL 列:        D,F
行范围:        4+
并行数量:      3
无头模式:      False
代理设置:      socks5://172.24.128.1:7890
超时时间:      60000 ms
配置文件:      config.toml
============================================================
```

**输出：**
- 快照目录：`journals-snapshot/`
- 日志文件：`journals-snapshot/snapshot-log.csv`
- 快照文件：
  - `ab/cd/abcdef.../dom.html` - 页面 DOM
  - `ab/cd/abcdef.../page.mhtml` - 完整页面归档

### Step 2: 批量提取信息

```bash
# 设置 API 密钥（如果配置文件中没有）
export OPENAI_API_KEY="sk-xxx"
export OPENAI_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"

# 批量提取（默认 auto 模式）
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 或指定提取方法
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+ \
  --extract-method langextract

# 强制重新提取
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+ \
  --force
```

**参数说明：**
- `--url-excel`: Excel 文件路径
- `--name-column`: 期刊名称列（如 A 列）
- `--url-columns`: URL 列（多列用逗号分隔，如 D,F）
- `--rows`: 行范围（如 "4+" 或 "4-99"）
- `--extract-method`: （可选）提取方法
  - `auto` - 优先 AI，失败回退规则（默认）
  - `langextract` - 仅使用 AI
  - `regexp` - 仅使用规则
- `--force`: （可选）强制重新提取（忽略已存在的结果）
- `--parallel`: （可选）并行数量
- `--model-id`: （可选）指定模型
- `--api-base`: （可选）API 接口地址
- `--api-key`: （可选）API 密钥

**输出：**
- Markdown 文件：`ab/cd/abcdef.../dom.md`
- 提取结果：
  - `ab/cd/abcdef.../host-langextract.json`（langextract 方法）
  - `ab/cd/abcdef.../host-regexp.json`（regexp 方法）
- 日志文件：`journals-snapshot/extract-log.csv`

### Step 3: 数据整合（生成最终报告）

```bash
# 整合所有提取结果到 Excel 文件
python combine_output.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

**参数说明：**
- `--url-excel`: Excel 文件路径
- `--name-column`: 期刊名称所在列（如 A 列）
- `--url-columns`: URL 所在列（多列用逗号分隔，如 D,F）
- `--rows`: 行范围
  - `4+`: 从第 4 行开始，遇到空行停止
  - `4-99`: 读取第 4 到 99 行

**输出：**
- 输出文件：`journals-snapshot/journals.xlsx-output-251106.143022.xlsx`
- 包含 7 列：期刊名称、来源链接、匹配机构、匹配关键词、匹配句子、提取方法、链接hash
- 包含所有记录（成功和失败），失败记录通过状态标注


---

## 📊 查看结果

### 查看整合输出

数据整合后会生成一个 Excel 文件，包含所有期刊的提取结果：

```bash
# 使用 Excel 或 LibreOffice 打开输出文件
# journals-snapshot/journals.xlsx-output-251106.143022.xlsx

# 或使用命令行查看（需要安装 csvkit）
in2csv journals-snapshot/journals.xlsx-output-*.xlsx | head -20
```

输出文件包含 7 列：
1. **期刊名称** - 从原始 Excel 读取
2. **来源链接** - URL
3. **匹配机构** - 机构名称或状态标注
4. **匹配关键词** - 如 "official journal of"
5. **匹配句子** - 完整原始句子
6. **提取方法** - langextract 或 regexp
7. **链接hash** - SHA1 hash

状态标注示例：
- ✅ 成功：显示具体机构名称
- ⏳ 待快照
- ❌ 快照失败 (timeout)
- ⏳ 待提取
- ❌ 提取失败 (api_error)
- ⚠️ 无匹配

### 查看日志

```bash
# 查看快照日志
head -20 journals-snapshot/snapshot-log.csv

# 查看提取日志
head -20 journals-snapshot/extract-log.csv

# 统计成功率
grep -c "success" journals-snapshot/snapshot-log.csv
grep -c "failed" journals-snapshot/snapshot-log.csv
```

### 查看提取结果

```bash
# 查看单个结果
cat journals-snapshot/ab/cd/abcdef.../host.json

# 查找包含特定机构的结果
grep -r "John Wiley" journals-snapshot/ --include="*.json"
```

---

## 🔧 常见问题

### Q1: 快照失败怎么办？

查看 `snapshot-log.csv` 中的错误类型：
- `timeout`: 增加 `config.toml` 中的 `timeout` 值
- `network_error`: 检查网络和代理设置
- `http_error`: URL 可能无效或网站已关闭

### Q2: 提取失败怎么办？

查看 `extract-log.csv` 中的错误类型：
- `rate_limit`: API 频率限制，降低 `extract.parallel` 或增加 `retry_delay`
- `api_error`: 检查 API 密钥和配置
- `conversion_error`: HTML 文件可能损坏
- `config_error`: LangExtract 不可用或 API 密钥未配置

**提取方法选择建议：**
- 使用 `--extract-method auto`（默认）：AI 优先，失败自动回退规则
- 使用 `--extract-method langextract`：仅 AI，质量更高但可能失败
- 使用 `--extract-method regexp`：仅规则，稳定但精度较低

### Q3: 如何断点续传？

批量处理工具自动支持断点续传：
- 快照工具会检查 `snapshot-log.csv`，跳过已成功的 URL
- 提取工具会根据 `--extract-method` 检查对应文件：
  - `langextract` 模式检查 `host-langextract.json`
  - `regexp` 模式检查 `host-regexp.json`
  - `auto` 模式检查两个文件，任意存在则跳过

只需重新运行相同的命令即可。使用 `--force` 可强制重新提取。

### Q4: 如何调整并行数量？

方式一：修改配置文件 `config.toml`

```toml
[snapshot]
parallel = 5

[extract]
parallel = 3
```

方式二：使用命令行参数

```bash
python batch_snapshot.py --url-excel journals.xlsx --url-ranges D4:D99 --parallel 5
python batch_extract.py --input journals-snapshot/ --parallel 3
```

---

## 📝 文件结构说明

```
journals.xlsx                    # 输入的 Excel 文件
journals-snapshot/               # 快照目录
├── snapshot-log.csv             # 快照日志
├── extract-log.csv              # 提取日志
├── ab/                          # Hash 第 1-2 位
│   └── cd/                      # Hash 第 3-4 位
│       └── abcdef123.../        # Hash 第 5 位以后（完整 hash）
│           ├── dom.html         # 页面 DOM 快照
│           ├── page.mhtml       # 完整页面归档
│           ├── dom.md           # Markdown 转换结果
│           ├── host-langextract.json  # AI 提取结果
│           └── host-regexp.json       # 规则提取结果
└── ...
```

---

## 🎯 高级用法

### 只提取特定范围的快照

```bash
# 使用 find 命令配合提取工具
find journals-snapshot/ab/cd/ -name "dom.html" -type f | \
  xargs -I {} python extract.py --input {}
```

### 批量导出所有结果到一个文件

```bash
# 合并所有 JSON 结果
find journals-snapshot/ -name "host.json" -type f -exec cat {} \; > all_results.json
```

### 自定义模型和 API

```bash
python batch_extract.py \
  --input journals-snapshot/ \
  --model-id gpt-4o-mini \
  --api-base https://api.openai.com/v1 \
  --api-key sk-xxx
```

---

## ⚠️ 注意事项

1. **存储空间**: MHTML 文件较大，批量下载前请确保有足够的磁盘空间
2. **API 配额**: 使用 LangExtract 需要 API 密钥，注意配额限制
3. **网络稳定性**: 建议在稳定的网络环境下运行批量下载
4. **并行数量**: 根据机器性能和网络带宽调整，建议：
   - 快照下载：3-5 个并行
   - 信息提取：2-3 个并行（避免 API 频率限制）

---

## 📚 更多文档

- 详细功能说明：参见 `README.md`
- 单文件工具：`snapshot.py`、`extract.py`
- 配置参考：`config.toml`

如有问题，请查看日志文件或联系技术支持。

