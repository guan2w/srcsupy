# 🧩 项目名称

**期刊主办单位自动抽取工具**

包含单文件处理工具（extract.py）和批量处理工具（batch_snapshot.py、batch_extract.py）

---

## 一、项目背景与目标

从期刊官网或 Markdown 格式的介绍文本（如 About 页面）中，自动识别并结构化提取出期刊的“主办单位/出版方/版权方”等信息。
主要用于学术期刊信息抽取、数据库入库、出版方统计等任务。

---

## 二、输入输出规范

### 输入

* **输入文件**：本地 `.md` 文件（Markdown 格式）

  * 内容通常包含期刊的 About 页面文本
  * 示例：

    ```
    Allergy, the official journal of the European Academy of Allergy and Clinical Immunology (EAACI), ...
    Copyright © 1999-2025 John Wiley & Sons, Inc or related companies.
    ```

* **CLI 参数**

  | 参数名          | 必填 | 说明                                                    |
  | ------------ | -- | ----------------------------------------------------- |
  | `--input`    | ✅  | 输入 Markdown 文件路径                                      |
  | `--model-id` | ⛔  | 使用的 LangExtract 模型 ID（如 `qwen3-vl-32b-instruct`, `gpt-4o-mini` 等） |
  | `--output`   | ⛔  | 输出 JSON 文件路径（若不提供，则打印到 stdout）                        |
  | `--api-base` | ⛔  | OpenAI 兼容模型接口地址，如 DashScope 或本地代理                     |
  | `--api-key`  | ⛔  | 模型 API Key                                            |

---

### 输出

* **输出结构（JSON 格式）**

  ```json
  {
    "host_institutions": [
      {
        "name": "European Academy of Allergy and Clinical Immunology (EAACI)",
        "type": "host",
        "source_sentence": "Allergy, the official journal of ...",
        "matched_keyword": "official journal of",
        "char_position": {"start": 10, "end": 85},
        "extraction_method": "langextract"
      },
      {
        "name": "John Wiley & Sons, Inc",
        "type": "publisher",
        "source_sentence": "Copyright 1999-2025 John Wiley & Sons, Inc or related companies.",
        "matched_keyword": "copyright",
        "char_position": {"start": 200, "end": 260},
        "extraction_method": "regexp"
      }
    ]
  }
  ```

* 说明：

  * `name`：机构原文名（已清理 Markdown、版权符号、年份等）
  * `type`：机构类型（`host` 主办方 / `publisher` 出版方 / `copyright` 版权方）
  * `source_sentence`：完整原始句子（**纯文本，不含任何 Markdown 格式字符**）
  * `matched_keyword`：匹配到的关键短语（如 "official journal of"、"copyright" 等）
  * `char_position`：在原文中的字符位置（可选）
  * `extraction_method`：提取方式（`langextract` 或 `regexp`）

* **错误输出格式**

  ```json
  {
    "error": "Failed to connect to API: connection timeout"
  }
  ```

---

## 三、功能设计与处理流程

### 1️⃣ 文本解析与句子定位

* 对 Markdown 文本做清洗：

  * 使用 **`markdown` + `BeautifulSoup4`** 库将 Markdown 转为纯文本（类似 JS 的 `element.textContent`）
  * 完全移除所有格式字符：`**加粗**`、`*斜体*`、`[链接](url)`、`## 标题`、换行符等
  * 切分句子：支持中英文符号（`。!?;.` 等）
* 筛选包含关键短语的句子：

  * **关键短语列表**（支持大小写变体）

    ```
    on behalf of, official journal of, official publication of,
    affiliate, edited by, owned, in association with,
    responsible for, supervised by, sponsored by, patronage,
    compile, in partnership with, in cooperation with,
    the backing of, administrated by, university press,
    funded by, published by, publisher,
    copyright, ©
    ```
  
  * 同时记录匹配到的关键词，便于后续分析

---

### 2️⃣ LangExtract 智能抽取

* 使用 LangExtract 的 few-shot 学习机制定义 prompt：

  * 指明抽取类 `host_institution`
  * 提供两组示例（EAACI 与 Wiley）
  * 规则：

    * 仅当语义确实表示官方主办/出版/版权关系时抽取
    * 必须返回 `source_sentence`
    * 使用原文（不改写名称或句子）

* `model_id` 可对接：

  * OpenAI 模型 (`gpt-4o-mini`, `gpt-4-turbo`)
  * Qwen 模型 (`qwen3-vl-32b-instruct`, `qwen-turbo`)
  * 本地 Ollama 模型

---

### 3️⃣ 回退规则（Rule-based Fallback）

规则回退策略：

* **API 调用失败**：完全回退到 regexp 规则抽取
* **返回空结果**：回退到 regexp 规则抽取
* **返回部分结果**：仅输出 LangExtract 结果（标注 `extraction_method: "langextract"`）

regexp 规则抽取逻辑：

* 匹配版权行：`Copyright ...` / `© ...`
* 匹配 `official journal of`、`in partnership with`、`published by` 等句型
* 在句中抓取机构类名词（含 Inc, Ltd, Society, Academy, etc.）
* 输出结构同 LangExtract 格式（标注 `extraction_method: "regexp"`）

---

### 4️⃣ 结果后处理与优化

#### 🧹 名称清洗

* 去除 Markdown 链接、星号、年份、版权符号等：

  * `1999–2025 [John Wiley & Sons, Inc](https://...)` → `John Wiley & Sons, Inc`
* 保留开头的大写 `The`，去除小写 `the`
* 去掉 `Copyright` 或 `©` 前缀


## 四、模型与后端配置

### 支持多种后端：

| 场景               | 环境变量设置                                                                                        | 示例模型                           |
| ---------------- | --------------------------------------------------------------------------------------------- | ------------------------------ |
| Qwen (DashScope) | `OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`<br>`OPENAI_API_KEY=你的key` | `--model-id qwen3-vl-32b-instruct` |
| OpenAI           | `OPENAI_API_BASE=https://api.openai.com/v1`                                                   | `--model-id gpt-4o-mini`       |
| 本地 Ollama        | `OPENAI_API_BASE=http://localhost:11434/v1`                                                   | `--model-id qwen2:7b-instruct` |

### 或者通过命令行参数直接指定：

```bash
python extract.py \
  --input journal.md \
  --model-id qwen3-vl-32b-instruct \
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key sk-xxxx \
  --output result.json
```

---

## 五、设计特点与关键创新

| 功能模块                       | 特点                                        |
| -------------------------- | ----------------------------------------- |
| **LangExtract + Few-shot** | 兼容长文本抽取、语态变体匹配、高精度源定位                     |
| **双层策略**                   | 优先 LLM 智能抽取 + regexp 规则兜底                 |
| **纯文本提取**                  | 使用 `markdown` + `BeautifulSoup4` 完全去除格式字符  |
| **输出可追溯性**                 | 每条结果保留原句文本、字符位置和匹配关键词                     |
| **机构类型识别**                 | 自动区分主办方(host)、出版方(publisher)、版权方(copyright) |
| **提取方式标注**                 | 明确标注使用 langextract 或 regexp 方式提取         |
| **关键词匹配记录**                | 记录每个提取结果匹配的关键短语                           |
| **跨后端模型支持**                | 统一 OpenAI 接口兼容（Gemini、Qwen、Ollama 等）      |
| **灵活 CLI 接口**              | 支持多种参数、输出到文件或控制台                          |

---

## 六、关键输出示例

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

## 七、关键文件结构

```
journal-host/
├── extract.py             # 主脚本（含智能抽取+规则回退+清洗优化）
├── README.md              # 项目说明
├── requirements.txt       # Python 依赖包
├── examples/
│   └── wiley.md           # 示例期刊文本
└── out/
    └── wiley_host.json    # 输出结果
```

---

## 八、运行示例

### 环境准备

```bash
# 激活 conda 环境（Python 3.13）
conda activate base

# 安装依赖
pip install -r requirements.txt
```

### 使用 Qwen 模型

```bash
# 设置环境变量
export OPENAI_API_KEY="sk-xxxx"
export OPENAI_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"

# 运行抽取
python extract.py \
  --input examples/wiley.md \
  --model-id qwen3-vl-32b-instruct \
  --output out/wiley_host.json
```

### 或直接通过参数指定

```bash
python extract.py \
  --input examples/wiley.md \
  --model-id qwen3-vl-32b-instruct \
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key sk-xxxx \
  --output out/wiley_host.json
```

输出：

```
[OK] Extracted 2 institutions using langextract
[OK] Saved to d:\projects\.pre\supy\journal-host\out\wiley_host.json
```

---

## 九、批量处理工具

### 9.1 概述

批量处理工具包含两个独立脚本：

- **batch_snapshot.py**: 批量下载网页快照
- **batch_extract.py**: 批量提取主办单位信息

两个脚本可独立运行，也可串联使用，支持并行处理、断点续传和进度显示。

---

### 9.2 batch_snapshot.py - 批量快照工具

#### 功能特点

- ✅ 从 Excel 文件读取多列 URL 范围
- ✅ 自动去重、过滤无效 URL
- ✅ 并行下载（共享浏览器实例，多个 BrowserContext）
- ✅ 保存 dom.html + page.mhtml 两种格式
- ✅ Hash 分层存储（避免单目录文件过多）
- ✅ 断点续传（从日志恢复状态）
- ✅ 详细错误分类和日志记录

#### CLI 参数

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--url-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0（第一个 sheet） |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--url-columns` | ✅ | URL 列（多列用逗号分隔），如 "D,F" |
| `--rows` | ✅ | 行范围，如 "4+" 或 "4-99" |
| `--parallel` | ⛔ | 并行数量（覆盖配置文件，默认从 config.toml 读取） |

#### 目录结构

```
输入文件.xlsx
输入文件-snapshot/              # 快照目录
  ├── snapshot-log.csv           # 快照日志
  ├── ab/cd/abcdef123.../        # Hash 分层目录
  │   ├── dom.html               # 页面 DOM 内容
  │   ├── page.mhtml             # 完整页面归档（含资源）
  │   ├── dom.md                 # Markdown 转换结果（extract 阶段生成）
  │   └── host.json              # 提取结果（extract 阶段生成）
  └── ...
```

#### snapshot-log.csv 格式

```csv
url,hash,dom_size,mhtml_size,snapshot_time,status,error_type,error_message
https://example.com,abc123...,12345,56789,2025-11-05 10:00:00,success,,
https://fail.com,def456...,0,0,2025-11-05 10:01:00,failed,timeout,Navigation timeout exceeded
```

#### 运行示例

```bash
# 基础用法（自动遍历到空行）
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 指定固定行范围
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D \
  --rows 4-99

# 指定 sheet 名称
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --sheet-name "期刊列表" \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 指定并行数
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+ \
  --parallel 5

# 断点续传（自动跳过已成功的 URL）
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

**启动时会打印关键参数：**
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

---

### 9.3 batch_extract.py - 批量提取工具

#### 功能特点

- ✅ 自动扫描待提取的快照目录
- ✅ 使用 markitdown 转换 HTML 为 Markdown
- ✅ 调用 extract.py 核心逻辑提取主办单位
- ✅ 并行提取（多线程）
- ✅ 失败重试机制（可配置次数和延迟）
- ✅ 持续监听模式（--watch）
- ✅ 详细错误日志记录

#### CLI 参数

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--url-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0（第一个 sheet） |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--url-columns` | ✅ | URL 列（多列用逗号分隔），如 "D,F" |
| `--rows` | ✅ | 行范围，如 "4+" 或 "4-99" |
| `--parallel` | ⛔ | 并行数量（覆盖配置文件） |
| `--model-id` | ⛔ | LangExtract 模型 ID（覆盖配置文件） |
| `--api-base` | ⛔ | API 接口地址 |
| `--api-key` | ⛔ | API Key |

#### extract-log.csv 格式

```csv
hash,url,snapshot_time,extract_time,status,institutions_count,error_type,error_message
abc123...,https://example.com,2025-11-05 10:00:00,2025-11-05 10:05:00,success,3,,
def456...,https://fail.com,2025-11-05 10:01:00,2025-11-05 10:06:00,failed,0,api_error,Rate limit exceeded
```

#### 运行示例

```bash
# 基础用法（自动遍历到空行）
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 指定固定行范围
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D \
  --rows 4-99

# 指定并行数和模型
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+ \
  --parallel 3 \
  --model-id qwen3-vl-32b-instruct
```

---

### 9.4 配置文件（config.toml）

批量处理工具的配置从 `config.toml` 读取，命令行参数优先级更高。

```toml
[snapshot]
headless = false
proxy = "socks5://172.24.128.1:7890"
timeout = 60000           # 页面加载超时（毫秒）
wait_after_idle = 0       # 网络空闲后额外等待（毫秒）
parallel = 3              # 并行下载数量

[extract]
parallel = 2              # 并行提取数量
model_id = "qwen3-vl-32b-instruct"  # 默认模型
retry_times = 3           # 失败重试次数
retry_delay = 5           # 重试延迟（秒）
watch_interval = 30       # watch 模式扫描间隔（秒）

[api]
# 可选：统一管理 API 配置（命令行参数优先）
# api_key = "sk-xxx"
# api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

---

### 9.5 并行处理技术方案

#### Snapshot 并行策略

使用 **一个 Browser + 多个 BrowserContext** 的方案：

- 共享浏览器进程，资源高效
- 每个 BrowserContext 完全隔离（cookies、storage、sessions）
- 通过 `ThreadPoolExecutor` 实现并发
- 某个任务出错不影响其他任务

参考：[Playwright BrowserContext API](https://playwright.dev/docs/api/class-browsercontext)

#### Extract 并行策略

使用 `ThreadPoolExecutor` 多线程并行：

- 适合 I/O 密集型任务（文件读写、API 调用）
- 通过 `concurrent.futures` 管理任务队列
- 失败重试机制保证鲁棒性

---

### 9.6 完整工作流程示例

```bash
# Step 1: 批量下载快照
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 输出：
# [INFO] 实际读取行范围: 4-152
# [SNAPSHOT] 读取到 150 个 URL（去重后）
# [SNAPSHOT] 跳过 20 个已完成的 URL
# [SNAPSHOT] 开始处理 130 个 URL，并行数=3
# [PROGRESS] ████████████████████ 100% (130/130)
# [OK] 成功: 125, 失败: 5
# [OK] 日志已保存到 journals-snapshot/snapshot-log.csv

# Step 2: 批量提取信息
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+ \
  --model-id qwen3-vl-32b-instruct

# 输出：
# [INFO] 实际读取行范围: 4-152
# [EXTRACT] 读取到 150 个 URL（去重后）
# [EXTRACT] 跳过 45 个已提取的 URL
# [EXTRACT] 跳过 3 个无快照的 URL
# [EXTRACT] 开始处理 102 个 URL，并行数=2
# [PROGRESS] ████████████████████ 100% (102/102)
# [OK] 提取完成
#      成功: 97
#      失败: 5
#      跳过: 48 (已提取: 45, 无快照: 3)
#      日志: journals-snapshot/extract-log.csv

# Step 3: 数据整合（生成最终报告）
python combine_output.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 输出：journals-snapshot/journals.xlsx-output-251106.143022.xlsx
```

---

### 9.7 错误处理与日志

#### 错误分类

**snapshot-log.csv 错误类型：**

- `timeout` - 页面加载超时
- `network_error` - 网络连接错误
- `invalid_url` - 无效的 URL 格式
- `http_error` - HTTP 错误（404, 500 等）
- `unknown` - 未知错误

**extract-log.csv 错误类型：**

- `file_not_found` - dom.html 文件不存在
- `conversion_error` - HTML 转 Markdown 失败
- `api_error` - LangExtract API 调用失败
- `rate_limit` - API 频率限制
- `unknown` - 未知错误

#### 日志查看

```bash
# 查看快照失败的 URL
grep "failed" journals-snapshot/snapshot-log.csv

# 查看提取失败的记录
grep "failed" journals-snapshot/extract-log.csv

# 统计成功率
grep -c "success" journals-snapshot/snapshot-log.csv
```

---

### 9.8 更新后的文件结构

```
journal-host/
├── extract.py              # 单文件提取脚本
├── snapshot.py             # 单页面快照脚本
├── batch_snapshot.py       # 批量快照脚本
├── batch_extract.py        # 批量提取脚本
├── combine_output.py       # 数据整合脚本（新增）
├── config.toml             # 配置文件
├── README.md               # 项目说明
├── requirements.txt        # Python 依赖包
├── examples/
│   └── wiley.md
└── out/
    └── wiley_host.json
```

---

### 9.9 combine_output.py - 数据整合工具

#### 功能特点

- ✅ 从原始 Excel 读取期刊名称和 URL
- ✅ 支持一个期刊对应多个 URL 列（如 D 列和 F 列）
- ✅ 灵活的行范围指定（如 "4+" 遍历到空行，或 "4-99" 固定范围）
- ✅ 关联快照和提取日志，合并生成完整报告
- ✅ 一个 URL 多个机构时，每个机构占一行
- ✅ 包含失败记录，通过状态标注（待快照、快照失败、待提取、提取失败、无匹配等）
- ✅ 自动生成带时间戳的输出文件

#### CLI 参数

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `--url-excel` | ✅ | Excel 文件路径 |
| `--sheet-name` | ⛔ | Sheet 名称或索引，默认 0（第一个 sheet） |
| `--name-column` | ✅ | 期刊名称列，如 "A" |
| `--url-columns` | ✅ | URL 列（多列用逗号分隔），如 "D,F" |
| `--rows` | ✅ | 行范围，如 "4+" 或 "4-99" |

#### 行范围说明

- **"4+"**: 从第 4 行开始读取，直到 name-column 为空时停止（自动遍历）
- **"4-99"**: 读取第 4 行到第 99 行（固定范围）

#### 输出格式

输出 Excel 文件包含以下 7 列：

| 列名 | 说明 |
|------|------|
| 期刊名称 | 从原始 Excel 的 name-column 读取 |
| 来源链接 | URL |
| 匹配机构 | 机构名称（或状态标注） |
| 匹配关键词 | 如 "official journal of"、"copyright" 等 |
| 匹配句子 | 完整原始句子 |
| 提取方法 | langextract 或 regexp |
| 链接hash | URL 的 SHA1 hash |

**状态标注**：
- 待快照
- 快照失败 (timeout/network_error/...)
- 待提取
- 提取失败 (api_error/rate_limit/...)
- 无匹配
- 无URL

#### 运行示例

```bash
# 基础用法（自动遍历到空行）
python combine_output.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 指定固定行范围
python combine_output.py \
  --url-excel journals.xlsx \
  --sheet-name 0 \
  --name-column A \
  --url-columns D \
  --rows 4-99

# 指定 sheet 名称
python combine_output.py \
  --url-excel journals.xlsx \
  --sheet-name "期刊列表" \
  --name-column A \
  --url-columns D,F \
  --rows 4+
```

**输出示例**：
```
============================================================
[CONFIG] 数据整合工具 - 启动参数
============================================================
Excel 文件:    journals.xlsx
Sheet 名称:    0
期刊名称列:    A
URL 列:        D,F
行范围:        4+
============================================================

[INFO] 实际读取行范围: 4-152
[COMBINE] 读取到 149 个期刊
[COMBINE] 共 238 个 URL
[COMBINE] 加载快照日志...
[COMBINE] 快照记录: 235 个
[COMBINE] 加载提取日志...
[COMBINE] 提取记录: 228 个
[COMBINE] 整合数据...
[COMBINE] 写入输出文件...
[OK] 输出文件已保存: journals-snapshot/journals.xlsx-output-251106.143022.xlsx
     总行数: 512

[OK] 整合完成
     成功提取: 456 行
     失败/待处理: 56 行
     输出文件: journals-snapshot/journals.xlsx-output-251106.143022.xlsx
```

#### 输出文件命名规则

`{input-excel}-output-$YYMMDD.hhmmss.xlsx`

例如：
- 输入：`journals.xlsx`
- 输出：`journals.xlsx-output-251106.143022.xlsx`

文件保存在快照目录下（如 `journals-snapshot/`）

#### 数据关联流程

```
原始 Excel (journals.xlsx)
  ├─ 期刊名称列 (A)
  └─ URL 列 (D, F)
       ↓ 计算 SHA1(URL) = hash
       ↓
快照目录 (journals-snapshot/)
  ├─ snapshot-log.csv  (hash -> url, snapshot_status)
  ├─ extract-log.csv   (hash -> extract_status)
  └─ ab/cd/abcdef.../host.json (机构详细信息)
       ↓ 数据整合
       ↓
输出 Excel (journals.xlsx-output-YYMMDD.hhmmss.xlsx)
  └─ 7 列完整报告（包含成功和失败记录）
```

---

### 9.10 完整工作流程（含数据整合）

```bash
# Step 1: 批量下载快照
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# Step 2: 批量提取信息
python batch_extract.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+ \
  --model-id qwen3-vl-32b-instruct

# Step 3: 数据整合（生成最终报告）
python combine_output.py \
  --url-excel journals.xlsx \
  --name-column A \
  --url-columns D,F \
  --rows 4+

# 输出：journals-snapshot/journals.xlsx-output-251106.143022.xlsx
```

---

## 十、依赖包更新

批量处理工具需要额外的依赖包：

```txt
# 原有依赖
langextract>=1.0.0
openai>=1.0.0
regex>=2023.0.0
markdown>=3.4.0
beautifulsoup4>=4.12.0
requests>=2.31.0

# 新增依赖
pandas>=2.0.0              # Excel 处理
openpyxl>=3.1.0            # pandas Excel 引擎
markitdown>=0.0.1          # HTML 转 Markdown
tqdm>=4.66.0               # 进度条
playwright>=1.40.0         # 浏览器自动化
```

安装所有依赖：

```bash
pip install -r requirements.txt
playwright install chromium  # 安装 Chromium 浏览器
```

