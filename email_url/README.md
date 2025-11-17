
运行示例
```sh
# 试跑 3 条
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2-4

# 全部
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2+

python search_snapshot.py \
    --input-file=/Users/eric/dev/working/email-url/emails.xlsx \
    --sheet=Sheet1 \
    --search-columns='G*' \
    --rows=2+ \
    --debug
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