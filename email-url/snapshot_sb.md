# snapshot_sb.py 脚本使用说明

## 1. 简介
`snapshot_sb.py` 是一个用于批量采集网页快照的 Python 脚本。它读取 Excel 文件中的 URL，调用 ScrapingBee API 获取网页截图（PNG）和源代码（HTML），并将结果保存到本地磁盘，同时生成一份包含详细信息的输出 Excel 报告。

## 2. 功能特性
*   **批量采集**: 支持从 Excel 中读取多列 URL 进行处理。
*   **ScrapingBee 集成**: 利用 ScrapingBee 强大的渲染能力（支持 JS 渲染）获取高质量快照。
*   **高并发**: 支持多线程并发采集，大幅提高效率（最高支持 500 并发，可在配置中调整）。
*   **断点续传**: 基于文件存在性判断任务状态。程序中断后再次运行，会自动跳过已下载成功的快照，无需重复消耗 API 配额。
*   **原子性写入**: 采用 "写入临时文件 -> 重命名" 的策略，确保磁盘上的文件完整有效。
*   **自动去重**: 任务开始前对所有待采集 URL 进行去重，避免重复处理。
*   **结构化存储**: 使用 URL 的 SHA1 哈希值分层存储文件，避免单目录文件过多。

## 3. 环境与配置

### 依赖安装
```bash
pip install openpyxl requests scrapingbee
# 可选依赖（用于解析 TOML 配置，Python 3.11+ 内置 tomllib）
pip install tomli
```

### 配置文件 (config.toml)
在脚本同级或父级目录下创建 `config.toml`：

```toml
[scrapingbee]
timeout_seconds = 150   # API 请求超时时间
concurrency = 200       # 并发线程数
retry_times = 3         # 失败重试次数
# proxy = "http://127.0.0.1:7890"  # (可选) 本地代理地址

[snapshot]
dom_html = true         # 是否保存 HTML 源代码
screenshot = true       # 是否保存 PNG 截图
```

### 环境变量
必须设置 `SCRAPINGBEE_API_KEY`。可以通过 `.env` 文件或系统环境变量设置。

```bash
# .env 文件内容
SCRAPINGBEE_API_KEY=你的API密钥
```

## 4. 命令行参数

基本用法：
```bash
python snapshot_sb.py \
    --excel=/path/to/input.xlsx \
    --sheet=Sheet1 \
    --url-columns=url1,url2 \
    --title-row=2 \
    --data-rows=3+ \
    --output=/path/to/output.xlsx
```

| 参数 | 必选 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `--excel` | 是 | 输入 Excel 文件路径 | `/data/file.xlsx` |
| `--sheet` | 是 | 要读取的工作表名称 | `Sheet1` |
| `--url-columns` | 是 | 包含 URL 的列名，多列用逗号分隔 | `链接列,备用链接` |
| `--title-row` | 否 | 表头所在行号 (1-based)，默认为 1 | `2` (表示第2行是表头) |
| `--data-rows` | 是 | 数据行的范围 (1-based) | `3+` (第3行及之后)<br>`3-5` (第3到第5行)<br>`3` (仅第3行) |
| `--output` | 否 | 输出 Excel 路径，默认存为 `{原文件名}-snapshot.xlsx` | `/data/result.xlsx` |
| `--debug` | 否 | 开启调试模式，输出详细日志 | --debug |

## 5. 处理逻辑

1.  **解析输入**: 根据 `title-row` 解析表头，定位 `url-columns` 所在的列索引。
2.  **读取任务**: 遍历 `data-rows` 指定的行，提取 URL。若同一行有多个 URL 列，会生成多个任务。
3.  **去重**: 对提取到的所有 URL 进行去重。
4.  **并发执行**:
    *   计算 URL 的 SHA1 哈希值。
    *   生成存储路径: `{output_dir}/{hash[:2]}/{hash[2:4]}/{hash[4:]}.{png/html}`。
    *   **检查**: 若 PNG 和 HTML 文件都已存在（根据配置），标记为 `skipped` 并跳过。
    *   **请求**: 调用 ScrapingBee API。
    *   **写入**: 下载内容先写入 `.tmp` 文件，成功后重命名为正式文件。
5.  **结果汇总**: 所有任务结束后，生成输出 Excel 文件。

## 6. 输出文件说明

输出文件包含以下列：

| 列名 | 描述 |
| :--- | :--- |
| `original_url` | 原始输入的 URL |
| `source_sheet` | 来源 Sheet 名称 |
| `source_row` | URL 所在的 Excel 行号 |
| `source_column` | URL 所在的 Excel 列名 |
| `snapshot_status` | 任务状态: `success` (成功), `skipped` (已存在跳过), `failed` (失败) |
| `snapshot_image` | 截图文件的相对路径 |
| `snapshot_html` | HTML 文件的相对路径 |
| `snapshot_time` | 快照完成时间 (ISO8601 格式) |
| `duration_ms` | 耗时 (毫秒) |
| `image_size_bytes` | 截图文件大小 (字节) |
| `html_size_bytes` | HTML 文件大小 (字节) |
| `error_message` | 错误信息 (如有) |
