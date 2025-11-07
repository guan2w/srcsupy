# 期刊主办单位自动抽取工具

从期刊官网自动识别并结构化提取"主办单位/出版方/版权方"信息。

**核心工具：**
- **extract.py** - 单文件智能提取（AI + 规则回退）
- **batch_snapshot.py** - 批量网页快照下载
- **batch_extract.py** - 批量智能提取
- **batch_search.py** - 批量联网搜索（LLM 直接搜索）
- **combine_extracted.py** - 数据整合与报告生成

---

## 一、项目特点

- **双层策略**：LangExtract AI 提取 + 正则规则回退
- **多种采集方法**：快照提取、联网搜索
- **并行处理**：高效批量处理，支持断点续传
- **完整追溯**：保留原句、位置、匹配关键词
- **灵活配置**：多层级配置系统，支持多种 LLM 后端

---

## 二、快速开始

### 环境准备

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium  # 仅 batch_snapshot 需要

# 配置 API（编辑 config.toml 或设置环境变量）
export OPENAI_API_KEY="sk-xxx"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

### 配置文件结构

```toml
[snapshot]
parallel = 8              # 快照并行数

[extract]
parallel = 2              # 提取并行数
model_id = "qwen3-vl-32b-instruct"
# 可选：覆盖通用 LLM 配置
# api_key = "sk-xxx"
# api_base = "https://..."

[llm]
# 通用 LLM API 配置（所有任务的默认配置）
api_key = "sk-xxx"
api_base = "https://api.openai.com/v1"

[llm.search]
# 搜索任务专用配置（可覆盖 [llm] 配置）
# api_key = "sk-xxx"      # 可选覆盖
# api_base = "https://..." # 可选覆盖
parallel = 20
model_id = "gemini-2.5-pro-search"  # 联网搜索模型
timeout = 120
price_per_1m_input_tokens = 1.0
price_per_1m_output_tokens = 8.0
```

**配置优先级：**
- `batch_search.py`：命令行参数 > `[llm.search]` > `[llm]` > 环境变量
- `batch_extract.py`：命令行参数 > `[extract]` > `[llm]` > 环境变量

### 单文件提取

```bash
python extract.py \
  --input examples/wiley.md \
  --model-id qwen3-vl-32b-instruct \
  --output out/result.json
```

### 批量处理工作流

```bash
# 1. 下载快照
python batch_snapshot.py \
  --input-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 2. 批量提取
python batch_extract.py \
  --input-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 3. 生成报告
python combine_extracted.py \
  --input-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

### 联网搜索（无需快照）

```bash
python batch_search.py \
  --input-excel journals.xlsx \
  --name-column A \
  --rows 3-99
```

---

## 三、输出格式

```json
{
  "extraction_metadata": {
    "method": "langextract",
    "model": "gpt-4o-mini",
    "timestamp": "2025-11-06 14:30:22"
  },
  "host_institutions": [
    {
      "name": "European Academy of Allergy and Clinical Immunology (EAACI)",
      "type": "host",
      "source_sentence": "Allergy, the official journal of ...",
      "matched_keyword": "official journal of",
      "char_position": {"start": 10, "end": 85},
      "extraction_method": "langextract"
    }
  ]
}
```

**字段说明：**
- `type`: `host`(主办) / `publisher`(出版) / `copyright`(版权)
- `extraction_method`: `langextract`(AI) / `regexp`(规则)
- `source_sentence`: 完整原句（纯文本，已去除 Markdown 格式）

---

## 四、核心功能

### 1. 智能提取（extract.py）

**特点：**
- LangExtract AI 提取（few-shot learning）
- 正则规则回退（无需 API）
- Markdown 文本清洗（去除所有格式）
- 关键词匹配与句子定位

**提取方法：**
- `--extract-method auto`: AI 优先 + 规则回退（默认）
- `--extract-method langextract`: 仅 AI
- `--extract-method regexp`: 仅规则

### 2. 批量快照（batch_snapshot.py）

**特点：**
- Playwright 浏览器自动化
- 并行下载（共享浏览器实例）
- Hash 分层存储（避免单目录过多文件）
- 断点续传

**输出：**
- `dom.html`: 页面 DOM
- `page.mhtml`: 完整页面归档（含资源）
- `snapshot-log.csv`: 快照日志

### 3. 批量提取（batch_extract.py）

**特点：**
- 自动转换 HTML → Markdown
- 并行提取（多线程）
- 失败重试（API 频率限制处理）
- 支持强制重新提取

**输出：**
- `host-langextract.json` / `host-regexp.json`: 提取结果
- `extract-log.csv`: 提取日志

### 4. 联网搜索（batch_search.py）

**特点：**
- 直接调用联网 LLM（无需快照）
- 自动解析 JSON 数组
- Token 使用统计与成本计算
- 断点续传

**输出：**
- `{excel}-output-{model}-{timestamp}.xlsx`: 搜索结果
- `batch_search-{model}-{timestamp}.log`: LLM 交互日志
- `{excel}-search-log.csv`: 断点续传日志

### 5. 数据整合（combine_extracted.py）

**特点：**
- 关联快照、提取、搜索日志
- 多 URL 列支持
- 失败记录标注（待快照、快照失败、待提取等）
- 一个机构一行

**输出：**
- `{excel}-output-{timestamp}.xlsx`: 完整报告（7列）

---

## 五、关键输出示例

**输入示例：**

```
Allergy, the official journal of the European Academy of Allergy and Clinical Immunology (EAACI), ...
Copyright © 1999-2025 John Wiley & Sons, Inc or related companies.
```

**输出结果：**

```json
{
  "host_institutions": [
    {
      "name": "EAACI and John Wiley and Sons A/S",
      "type": "copyright",
      "source_sentence": "Allergy Edited By: Cezmi Akdis Online ISSN:1398-9995| Print ISSN:0105-4538| © EAACI and John Wiley and Sons A/S.",
      "matched_keyword": "edited by",
      "char_position": {"start": 673, "end": 828},
      "extraction_method": "regexp"
    },
    {
      "name": "John Wiley and Sons Ltd",
      "type": "publisher",
      "source_sentence": "Published by John Wiley and Sons, Ltd !",
      "matched_keyword": "published by",
      "char_position": {"start": 829, "end": 870},
      "extraction_method": "regexp"
    },
    {
      "name": "European Academy of Allergy and Clinical Immunology",
      "type": "host",
      "source_sentence": "Allergy, the official journal of the European Academy of Allergy and Clinical Immunology (EAACI), aims to advance...",
      "matched_keyword": "official journal of",
      "char_position": {"start": 1754, "end": 2423},
      "extraction_method": "regexp"
    }
  ]
}
```

---

## 六、文件结构

```
journal-host/
├── extract.py              # 单文件智能提取
├── batch_snapshot.py       # 批量快照下载
├── batch_extract.py        # 批量智能提取
├── batch_search.py         # 批量联网搜索
├── combine_extracted.py    # 数据整合与报告生成
├── llm_call.py             # 通用 LLM 调用模块（JSON 输出）
├── snapshot.py             # 单页面快照工具
├── config.toml             # 多层级配置文件
├── README.md               # 本文档
└── requirements.txt        # 依赖包
```

---

## 七、批量处理详细说明

### 7.1 batch_search.py - 批量联网搜索

**功能：** 直接调用联网 LLM 搜索主办单位（无需下载快照）

**参数：**

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--input-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0 |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--rows` | ✅ | 行范围，如 "3-99" |
| `--parallel` | ⛔ | 并行数量（覆盖配置文件） |

**配置（config.toml）：**

```toml
[llm.search]
parallel = 20
model_id = "gemini-2.5-pro-search"
timeout = 120
price_per_1m_input_tokens = 1.0
price_per_1m_output_tokens = 8.0
```

**示例：**

```bash
python batch_search.py \
  --input-excel journals.xlsx \
  --name-column A \
  --rows 3-99
```

---

### 7.2 batch_snapshot.py - 批量快照下载

**功能：** Playwright 自动化下载网页快照

**参数：**

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--input-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0 |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--url-columns` | ✅ | URL 列（多列用逗号分隔），如 "D,F" |
| `--rows` | ✅ | 行范围，如 "4+" 或 "4-99" |
| `--parallel` | ⛔ | 并行数量（覆盖配置文件） |

**示例：**

```bash
python batch_snapshot.py \
  --input-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

---

### 7.3 batch_extract.py - 批量智能提取

**功能：** 从快照批量提取主办单位

**参数：**

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--input-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0 |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--url-columns` | ✅ | URL 列（多列用逗号分隔），如 "D,F" |
| `--rows` | ✅ | 行范围，如 "4+" 或 "4-99" |
| `--parallel` | ⛔ | 并行数量（覆盖配置文件） |
| `--model-id` | ⛔ | LangExtract 模型 ID（覆盖配置文件） |
| `--api-base` | ⛔ | API 接口地址 |
| `--api-key` | ⛔ | API Key |
| `--extract-method` | ⛔ | 提取方法：`auto`（默认）、`langextract`、`regexp` |
| `--force` | ⛔ | 强制重新提取（忽略已存在的结果文件） |

**示例：**

```bash
python batch_extract.py \
  --input-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

---

### 7.4 combine_extracted.py - 数据整合

**功能：** 整合所有结果，生成完整 Excel 报告

**参数：**

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--input-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0 |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--url-columns` | ✅ | URL 列（多列用逗号分隔），如 "D,F" |
| `--rows` | ✅ | 行范围，如 "4+" 或 "4-99" |

**示例：**

```bash
python combine_extracted.py \
  --input-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

---

## 八、依赖包

```bash
pip install -r requirements.txt
playwright install chromium  # 仅 batch_snapshot 需要
```

**主要依赖：**
- `langextract` - AI 智能提取
- `openai` - LLM API 调用
- `pandas`, `openpyxl` - Excel 处理
- `playwright` - 浏览器自动化
- `markitdown` - HTML 转 Markdown
- `markdown`, `beautifulsoup4` - 文本清洗
- `tqdm` - 进度条

---

## 九、常见问题

**Q: 如何切换不同的 LLM 模型？**
A: 编辑 `config.toml` 中的 `model_id`，或使用命令行参数 `--model-id`。

**Q: API 频率限制如何处理？**
A: 配置文件中设置 `retry_times` 和 `retry_delay`，程序会自动重试。

**Q: 如何只用规则提取，不调用 API？**
A: 使用 `--extract-method regexp` 参数。

**Q: 断点续传如何工作？**
A: 所有批量工具都会记录处理状态到日志文件（CSV），重新运行时自动跳过已成功的记录。

**Q: 如何查看详细的 LLM 交互日志？**
A: 查看 `batch_search-{model}-{timestamp}.log` 文件，包含完整的请求和响应。

---

## 十、技术亮点

- **多层级配置系统**：`[llm]` 通用配置 + `[llm.search]`/`[extract]` 专用配置，支持覆盖
- **通用 LLM 调用模块**：`llm_call.py` 支持任意 JSON 格式输出的 LLM 任务
- **智能回退策略**：AI 提取失败自动切换到规则提取
- **并行处理优化**：Playwright 共享浏览器实例，ThreadPoolExecutor 多线程
- **完整追溯性**：保留原句、位置、匹配关键词、提取方法
- **断点续传**：所有批量工具支持断点续传
- **成本统计**：Token 使用量和成本实时统计（batch_search）

---

## 十一、开发计划

- [ ] 新的采集方法：LLM 深度分析（直接分析网页内容）
- [ ] 采集方法评估：汇总多种方法结果，自动对比评估
- [ ] Web UI：可视化操作界面
- [ ] 结果去重与合并：智能识别重复机构

---

**项目地址：** journal-host/
**文档版本：** 2025-11-07

