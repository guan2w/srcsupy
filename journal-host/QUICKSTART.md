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

准备一个 Excel 文件（如 `journals.xlsx`），包含期刊网站的 URL。

```bash
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --url-ranges D4:D99,F4:F99
```

**参数说明：**
- `--url-excel`: Excel 文件路径
- `--url-ranges`: URL 所在的单元格范围（支持多个范围，逗号分隔）
- `--sheet-name`: （可选）Sheet 名称或索引，默认 0（第一个 sheet）
- `--parallel`: （可选）并行数量，覆盖配置文件

**启动时会打印关键参数方便排错：**
```
============================================================
[CONFIG] 批量快照下载工具 - 启动参数
============================================================
Excel 文件:    journals.xlsx
Sheet 名称:    0
URL 范围:      D4:D99,F4:F99
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

# 从 Excel 文件推导快照目录
python batch_extract.py --input journals.xlsx

# 或直接指定快照目录
python batch_extract.py --input journals-snapshot/
```

**参数说明：**
- `--input`: Excel 文件路径 或 快照目录路径
- `--parallel`: （可选）并行数量
- `--model-id`: （可选）指定模型
- `--api-base`: （可选）API 接口地址
- `--api-key`: （可选）API 密钥

**输出：**
- Markdown 文件：`ab/cd/abcdef.../dom.md`
- 提取结果：`ab/cd/abcdef.../host.json`
- 日志文件：`journals-snapshot/extract-log.csv`

### Step 3: 持续监听模式（可选）

如果您希望在快照下载的同时进行提取，可以使用监听模式：

```bash
# 在一个终端运行快照下载
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --url-ranges D4:D99,F4:F99

# 在另一个终端运行持续提取
python batch_extract.py \
  --input journals-snapshot/ \
  --watch

# 监听模式会每 30 秒扫描一次新文件并自动提取
# 按 Ctrl+C 停止监听
```

---

## 📊 查看结果

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

### Q3: 如何断点续传？

批量处理工具自动支持断点续传：
- 快照工具会检查 `snapshot-log.csv`，跳过已成功的 URL
- 提取工具会检查 `host.json` 是否存在，跳过已提取的文件

只需重新运行相同的命令即可。

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
│           └── host.json        # 提取的主办单位信息
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

