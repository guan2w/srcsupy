# 🧩 项目名称

**期刊主办单位自动抽取工具（extract.py）**

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

