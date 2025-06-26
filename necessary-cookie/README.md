# Cookie必要性分析工具

自动分析curl请求中哪些cookie是必须的，通过逐项移除cookie来确定最小必要cookie集合。

## 🚀 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 编辑curl.txt添加你的curl命令
# 运行分析
python cookie_analyzer.py

# 查看结果（在result目录中）
ls result/
```

## ✨ 功能特性

- 🔍 **智能解析**: 自动解析curl命令，提取URL、headers和cookies
- 🧪 **逐项测试**: 通过逐项移除cookie来测试其必要性
- ✅ **灵活验证**: 支持自定义响应验证条件（状态码+JSON键）
- 🔄 **网络重试**: 智能识别网络异常并自动重试
- 📊 **详细报告**: 生成详细的分析报告和最小化curl命令
- 📁 **结果管理**: 结果自动保存到时间戳目录，便于管理
- 🎛️ **命令行配置**: 支持命令行参数配置主要选项

## 📋 命令行选项

```bash
python cookie_analyzer.py [选项]

选项:
  -d, --delay FLOAT      请求间隔时间（秒），默认1.0秒
  -r, --retry INT        网络异常重试次数，默认3次
  -f, --file PATH        curl命令文件路径，默认curl.txt
  -o, --output-dir DIR   结果输出目录，默认result
  -q, --quiet           静默模式，减少输出信息
  -h, --help            显示帮助信息
```

### 使用示例

```bash
# 使用默认配置
python cookie_analyzer.py

# 设置请求间隔为2秒
python cookie_analyzer.py --delay 2.0

# 设置重试次数为5次
python cookie_analyzer.py --retry 5

# 使用自定义curl文件
python cookie_analyzer.py --file my_curls.txt

# 自定义输出目录
python cookie_analyzer.py --output-dir ./my_results

# 静默模式运行
python cookie_analyzer.py --quiet

# 组合使用
python cookie_analyzer.py -d 1.5 -r 5 -f prod_curls.txt -o prod_results
```

## 📄 curl.txt文件格式

在 `curl.txt` 文件中按以下格式添加curl命令：

```
[CURL_START]
name=ESI网站分析
expected_key=status
curl 'https://example.com/api' \
  -H 'accept: application/json' \
  -b 'cookie1=value1; cookie2=value2'
[CURL_END]

[CURL_START]
name=测试API
expected_key=data
curl 'https://httpbin.org/cookies' \
  -H 'User-Agent: Test' \
  -b 'test=123; session=abc'
[CURL_END]
```

**格式说明**:
- `name`: 命令的描述性名称
- `expected_key`: 用于验证响应成功的JSON键名
- curl命令可以跨多行

## 📊 结果输出

分析完成后会在指定目录生成以下文件（文件名以时间戳开头）：

```
result/
├── 250125.143022-ESI网站分析_minimal_curl.sh      # 最小化curl命令
├── 250125.143022-ESI网站分析_analysis_result.json # 详细分析结果
├── 250125.150430-测试API_minimal_curl.sh
└── 250125.150430-测试API_analysis_result.json
```

### 输出文件说明

**minimal_curl.sh**: 包含最小化的可执行curl命令
```bash
#!/bin/bash
# 最小化的curl命令: ESI网站分析
# 分析时间: 2025-01-25 14:30:22
# 配置: 延迟=1.0s, 重试=3次

curl 'https://example.com/api' \
  -H 'accept: application/json' \
  -b 'necessary_cookie=value'
```

**analysis_result.json**: 详细的分析数据
```json
{
  "command_name": "ESI网站分析",
  "analysis_time": "2025-01-25 14:30:22",
  "timestamp_prefix": "250125.143022-",
  "config": {
    "delay": 1.0,
    "retry_count": 3,
    "expected_key": "status"
  },
  "original_cookies_count": 36,
  "necessary_cookies_count": 2,
  "necessary_cookies": {...},
  "removed_cookies_count": 34,
  "url": "https://example.com/api"
}
```

## 💡 分析过程示例

```
开始分析，共有 36 个cookie项...
期望响应包含键: status
--------------------------------------------------
测试完整cookie...
✅ 完整cookie请求成功

尝试移除cookie: _ga
  ✅ 可以移除 '_ga'
    📄 status: SUCCESS

尝试移除cookie: session_id
    ⚠️  网络异常 (第1次尝试): Read timed out
    🔄 1.0秒后重试...
  ❌ 不能移除 'session_id' - 这是必要的cookie

============================================================
分析完成！
原始cookie数量: 36
必要cookie数量: 2
已移除cookie数量: 34

✅ 结果已保存:
  📝 result/250125.143022-ESI网站分析_minimal_curl.sh
  📊 result/250125.143022-ESI网站分析_analysis_result.json
```

## 🔧 编程接口

```python
from cookie_analyzer import CookieAnalyzer
from curl_reader import CurlFileReader

# 从文件读取
reader = CurlFileReader("curl.txt")
commands = reader.read_all_commands()
selected_cmd = commands[0]

# 创建分析器
analyzer = CookieAnalyzer(
    expected_key=selected_cmd.expected_key,
    delay=1.0,
    retry_count=3
)

# 执行分析
url, headers, cookies = analyzer.parse_curl_command(selected_cmd.curl_command)
necessary_cookies = analyzer.find_necessary_cookies(url, headers, cookies)

# 生成最小化curl命令
minimal_curl = analyzer.generate_minimal_curl(url, headers, necessary_cookies)
```

## ⚠️ 注意事项

- 🕐 分析时间取决于cookie数量（平均每个cookie 1-2秒）
- 🔒 确保有权限访问目标URL，某些API需要有效session
- 🌐 某些网站有反爬虫措施，建议适当调整请求间隔
- 📝 验证键名需要根据实际API响应调整
- 💾 建议分析前备份重要cookie，避免session失效

## 🗂️ 项目结构

```
necessary-cookie/
├── cookie_analyzer.py      # 核心分析引擎（主程序）
├── curl_reader.py         # curl文件读取模块
├── test_cookie_analyzer.py # 测试套件
├── curl.txt               # curl命令配置文件
├── requirements.txt       # 依赖列表
├── README.md             # 项目说明文档
└── result/               # 结果输出目录
    ├── YYMMDD.hhmmss-*_minimal_curl.sh
    └── YYMMDD.hhmmss-*_analysis_result.json
```


  