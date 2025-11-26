# Searching 搜索与提取工具

基于 ScrapingBee API 的批量搜索与数据提取工具，支持 Excel 驱动、断点续跑、并发执行。

## 依赖

```bash
pip install openpyxl requests scrapingbee
```

## 配置

### config.toml

```toml
[scrapingbee]
timeout_seconds = 150
concurrency = 25
retry_times = 1
proxy = "http://127.0.0.1:7890"  # 可选

[assemble]
exclude_url_pattern = "news"  # 可选，排除匹配此正则的 URL
```

### 环境变量

```bash
export SCRAPINGBEE_API_KEY=your_api_key
# 或在 .env 文件中配置
```

## 输入文件格式

Excel 文件需包含以下 Sheet：

| Sheet | 说明 |
|-------|------|
| 输入表 | 名称由 `--sheet-name` 指定，表头行由 `--header-row` 指定 |
| meta | 配置表，存储模板和规则 |

### meta 表结构

| key | value |
|-----|-------|
| search | 搜索模板，如 `"{{univ}}" {{unit}} site:{{domain}}` |
| ai_extract_rules | AI 提取规则（JSON），如 `{"学者姓名": "...", "所在学校": "..."}` |

- 第一行为表头：A1="key", B1="value"
- 数据从第二行开始
- `search.py` 需要 `search` key
- `extract.py` 需要 `ai_extract_rules` key

**模板变量**：`{{xxx}}` 对应输入表的列名。

## search.py

执行搜索，结果写入 `{input}-search-log.csv`。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|:----:|--------|------|
| `--input-file` | ✓ | | 输入 Excel 文件 |
| `--sheet-name` | ✓ | | 输入数据 Sheet 名称 |
| `--header-row` | | 1 | 表头行号 |
| `--rows` | ✓ | | 数据行范围，如 `3+` 或 `3-100` |
| `--top-n` | | 0 | 保留前 N 条结果，0=全部 |
| `--concurrency` | | 配置文件值 | 并发数 |
| `--debug` | | | 调试模式 |

### 示例

```bash
python search.py \
    --input-file=data.xlsx \
    --sheet-name=数据表 \
    --header-row=2 \
    --rows=3+ \
    --top-n=5 \
    --concurrency=10
```

### 输出日志格式

每条 organic_result 一行：

| 字段 | 说明 |
|------|------|
| row_number | 输入行号（参考） |
| query | 渲染后的搜索词 |
| search_time | 搜索时间 |
| duration_ms | 搜索耗时(ms) |
| FOUND | 是否有结果 |
| ERROR | 错误信息 |
| number_of_results | 总结果数 |
| number_of_organic_results | 有机结果数 |
| position | 结果位置 |
| url | 链接 |
| displayed_url | 显示链接 |
| description | 描述 |
| title | 标题 |
| domain | 域名 |

**断点续跑**：通过 `query` 字段判断是否已搜索，已存在的查询自动跳过。

## assemble.py

整合输入 Excel 与搜索日志，输出 `{input}-assembled.xlsx`。

支持通过 `config.toml` 中的 `exclude_url_pattern` 配置排除特定 URL（先过滤再取 top-n）。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|:----:|--------|------|
| `--input-file` | ✓ | | 输入 Excel 文件 |
| `--sheet-name` | ✓ | | 输入数据 Sheet 名称 |
| `--header-row` | | 1 | 表头行号 |
| `--rows` | ✓ | | 数据行范围 |
| `--top-n` | | 1 | 整合结果条数 |
| `--columns` | ✓ | | 输出列映射 |
| `--debug` | | | 调试模式 |

### --columns 格式

```
输出列名:日志字段名,输出列名:日志字段名,...
```

可用字段：`url`, `displayed_url`, `description`, `title`, `domain`, `number_of_results`, `number_of_organic_results`

### 示例

```bash
python assemble.py \
    --input-file=data.xlsx \
    --sheet-name=数据表 \
    --header-row=2 \
    --rows=3+ \
    --top-n=3 \
    --columns=来源链接:url,域名:domain,标题:title
```

### 输出列顺序

按结果分组（顺序 A）：

```
--columns=来源链接:url,域名:domain --top-n=3

→ 来源链接1, 域名1, 来源链接2, 域名2, 来源链接3, 域名3
```

## 搜索工作流程

```
1. 准备输入 Excel（输入表 + template 表）
2. 执行 search.py → 生成 search-log.csv
3. 执行 assemble.py → 生成 assembled.xlsx
```

支持中断后重跑，search.py 会自动跳过已完成的查询。

---

## extract.py

调用 ScrapingBee AI Extract 从 URL 提取结构化数据，结果写入 `{input}-extract-log.csv`。

### 提取规则配置

从 `meta` 表的 `ai_extract_rules` key 读取提取规则（JSON 格式）。

**规则示例**：
```json
{"学者姓名": "页面中介绍的那个学者/教师的姓名", "所在学校": "学者所在的学校", "任职部门": "学者所在的学校的二级部门"}
```

**支持动态插值**：规则中可使用 `{{列名}}` 引用输入数据的列值：
```json
{"网页类型": "个人主页 or 新闻 or 名单 or 其他", "学者姓名": "页面中介绍的那个学者/教师的姓名，如果不是"{{姓名}}"请留空", "所在学校": "该学者所在的学校"}
```
其中 `{{姓名}}` 会被替换为输入表中"姓名"列的值。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|:----:|--------|------|
| `--input-file` | ✓ | | 输入 Excel 文件 |
| `--sheet-name` | ✓ | | 输入数据 Sheet 名称 |
| `--header-row` | | 1 | 表头行号 |
| `--rows` | ✓ | | 数据行范围 |
| `--url-columns` | ✓ | | URL 列名，多个用逗号分隔 |
| `--concurrency` | | 配置文件值 | 并发数 |
| `--debug` | | | 调试模式 |

### 示例

```bash
python extract.py \
    --input-file=data.xlsx \
    --sheet-name=数据表 \
    --header-row=2 \
    --rows=3+ \
    --url-columns=来源链接1,来源链接2 \
    --concurrency=5
```

### 输出日志格式

| 字段 | 说明 |
|------|------|
| url | 提取的 URL |
| url_column | URL 所在列名 |
| row_number | 输入行号（参考） |
| extract_time | 提取时间 |
| duration_ms | 提取耗时(ms) |
| SUCCESS | 是否成功 |
| ERROR | 错误信息 |
| *规则字段* | 提取结果（动态列） |

**断点续跑**：通过 URL 判断是否已提取，同一 URL 只提取一次。

## extract-assemble.py

整合输入 Excel 与提取日志，在每个 URL 列右侧插入提取结果列，输出 `{input}-extracted.xlsx`。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|:----:|--------|------|
| `--input-file` | ✓ | | 输入 Excel 文件 |
| `--sheet-name` | ✓ | | 输入数据 Sheet 名称 |
| `--header-row` | | 1 | 表头行号 |
| `--rows` | ✓ | | 数据行范围 |
| `--url-columns` | ✓ | | URL 列名，多个用逗号分隔 |
| `--insert-mode` | | after_url | 列插入模式 |
| `--debug` | | | 调试模式 |

### 插入模式

| 模式 | 说明 |
|------|------|
| `after_url` | 在每个 URL 列右侧插入结果列（默认） |
| `append` | 在所有列末尾追加结果列 |

### 示例

```bash
python extract-assemble.py \
    --input-file=data.xlsx \
    --sheet-name=数据表 \
    --header-row=2 \
    --rows=3+ \
    --url-columns=来源链接1,来源链接2
```

### 输出列结构

假设 `--url-columns=来源链接1,来源链接2`，提取规则有 `学者姓名`, `所在学校` 字段：

**after_url 模式**：
```
... | 来源链接1 | 来源链接1-学者姓名 | 来源链接1-所在学校 | ... | 来源链接2 | 来源链接2-学者姓名 | 来源链接2-所在学校 | ...
```

**append 模式**：
```
原始列... | 来源链接1-学者姓名 | 来源链接1-所在学校 | 来源链接2-学者姓名 | 来源链接2-所在学校
```

## 提取工作流程

```
1. 准备输入 Excel（数据表 + ai_extract_rules 表）
2. 执行 extract.py → 生成 extract-log.csv
3. 执行 extract-assemble.py → 生成 extracted.xlsx
```

支持中断后重跑，extract.py 会自动跳过已提取的 URL。

