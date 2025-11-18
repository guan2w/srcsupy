
运行示例
```sh
conda activate llmcall

# 试跑 3 条
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2-4

# 全部
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2+

python search_snapshot.py \
    --input-file=/Users/eric/dev/working/email-url/emails.xlsx \
    --sheet=Sheet1 \
    --search-columns="G*" \
    --rows=2+ \
    --debug


# 数据汇总
python assemble.py \
    --input-file=D:/dev/working/email-url-1117/emails.xlsx \
    --sheet=Sheet1 \
    --search-columns="G*" \
    --rows=2+ \
    --snapshot-prefix="http://192.168.51.109/snapshot/"

python assemble.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2+ --snapshot-prefix="http://192.168.51.109/snapshot/"


# 11.18 4k 条
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails1118.xlsx --sheet="待清理网页&快照" --search-columns="H*" --rows=2-4


```

## 日志文件

脚本会在输入文件同目录下生成两个 CSV 日志文件：
- `{base_name}.search.csv`：搜索日志，记录每次搜索的关键字、结果和前3个URL
- `{base_name}.snapshot.csv`：快照日志，以URL为唯一键，记录每个URL的快照信息

## 直接下载

对于以下类型的文件，脚本会直接下载而不使用 ScrapingBee 截图：
- PDF: `.pdf`
- Office 文档: `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`
- 压缩文件: `.zip`
- 图片: `.png`, `.jpg`, `.jpeg`, `.gif`

## 代理配置

在 `config.toml` 中可以配置网络代理：

```toml
[scrapingbee]
timeout_seconds = 120
concurrency = 3
retry_times = 1
proxy = "http://127.0.0.1:7890"  # 可选，留空或删除则不使用代理
```

代理配置会应用于：
- Google 搜索 API 请求
- 直接下载文件请求

注意：ScrapingBee 截图 API 的代理配置需要通过 ScrapingBee 客户端库的配置方式设置。

## 代码架构

项目采用函数式编程设计，重构后的 `assemble.py` 采用精简架构：

- **单一主函数**: `main()` 函数处理所有核心逻辑
- **专用工具函数**: 每个功能模块对应一个简洁的工具函数
- **直接数据流**: 避免过度抽象，数据直接在函数间传递

**核心函数**:
- `load_data()`: 加载搜索和快照日志数据
- `parse_search_columns()`: 解析搜索列配置
- `build_keywords()`: 从Excel行构建关键词
- `calculate_snapshot_status()`: 计算快照状态
- `parse_rows_range()`: 解析行范围

这样的设计大幅减少了代码量（254行 vs 原610行），同时保持了所有原有功能，提高了代码的可读性和维护性。