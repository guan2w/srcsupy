# 故障排除指南

## 常见问题与解决方案

### 1. ❌ Ollama API error: Can't find Ollama qwen3-vl-32b-instruct

**错误信息**：
```
[ERROR] LangExtract failed: Ollama API error: Can't find Ollama qwen3-vl-32b-instruct. 
Try: ollama run qwen3-vl-32b-instruct
```

**原因**：
- LangExtract 根据 `model_id` 自动选择 provider
- `qwen3-vl-32b-instruct` 不匹配 OpenAI provider 的命名规则（通常是 `gpt-*`）
- 因此被误判为 Ollama 本地模型

**解决方案**：

✅ **使用 `gpt-4o` 作为 model_id**（推荐）

```bash
python extract.py \
  --input examples/wiley.md \
  --model-id gpt-4o \
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key sk-your-key \
  --output out/wiley_host.json
```

**说明**：
- `model_id=gpt-4o` → 触发 OpenAI provider
- `api_base` → 将请求重定向到 DashScope
- 实际使用的模型由 DashScope 配置决定

📚 详细说明：[QWEN_USAGE.md](QWEN_USAGE.md)

---

### 2. ❌ extract() got an unexpected keyword argument 'show_progress'

**错误信息**：
```
TypeError: extract() got an unexpected keyword argument 'show_progress'
```

**原因**：
- 新版 LangExtract API 不再支持 `show_progress` 参数

**解决方案**：

✅ **已在代码中修复**

如果您使用的是最新版 `extract.py`，此问题已解决。如果仍然遇到，请确保：

```bash
# 更新代码
git pull

# 或重新下载 extract.py
```

📚 详细说明：[API_COMPATIBILITY.md](API_COMPATIBILITY.md)

---

### 3. ❌ No module named 'langextract'

**错误信息**：
```
ModuleNotFoundError: No module named 'langextract'
```

**原因**：
- LangExtract 库未安装

**解决方案**：

```bash
# 安装所有依赖
pip install -r requirements.txt

# 或只安装 LangExtract
pip install langextract
```

---

### 4. ❌ Connection timeout / API error

**错误信息**：
```
[ERROR] LangExtract failed: connection timeout
```

**可能原因**：
1. API 密钥错误
2. 网络连接问题
3. API 地址配置错误
4. API 配额用尽

**解决方案**：

```bash
# 1. 检查 API 密钥
echo $OPENAI_API_KEY

# 2. 测试网络连接
curl -I https://dashscope.aliyuncs.com/compatible-mode/v1

# 3. 验证 API 密钥
curl -H "Authorization: Bearer sk-your-key" \
  https://dashscope.aliyuncs.com/compatible-mode/v1/models

# 4. 查看 API 配额（在 DashScope 控制台）
```

---

### 5. ⚠️ 输出结果为空或不准确

**症状**：
- 提取结果为空 `[]`
- 或提取的机构不准确

**解决方案**：

#### 方案 A：使用 regexp 模式（无需 API）

```bash
# 不提供 API key，自动使用 regexp 回退
python extract.py \
  --input examples/wiley.md \
  --output out/wiley_host.json
```

#### 方案 B：优化 few-shot 示例

修改 `extract.py` 中的 `examples`，提供更贴近您的文档的示例。

#### 方案 C：调整 temperature

```python
# 在 extract.py 中修改
temperature=0,  # 更确定性的输出
```

---

### 6. ❌ Markdown/BeautifulSoup4 未安装

**警告信息**：
```
[WARNING] markdown/beautifulsoup4 not installed, text extraction may be less accurate
```

**影响**：
- 纯文本提取质量下降
- `source_sentence` 可能包含格式字符

**解决方案**：

```bash
pip install markdown beautifulsoup4

# 或
pip install -r requirements.txt
```

---

### 7. 🐛 Windows 编码问题

**症状**：
- 中文输出乱码
- UnicodeEncodeError

**解决方案**：

```bash
# 方案 1：使用 PowerShell（推荐）
pwsh
python extract.py --input examples\wiley.md --output out\wiley_host.json

# 方案 2：设置环境变量
$env:PYTHONIOENCODING="utf-8"
python extract.py --input examples\wiley.md --output out\wiley_host.json

# 方案 3：输出到文件（避免终端编码问题）
python extract.py --input examples\wiley.md --output out\wiley_host.json
```

---

## 测试清单

验证环境配置是否正确：

```bash
# 1. 检查 Python 版本（需要 3.9+）
python --version

# 2. 检查依赖安装
pip list | grep langextract
pip list | grep markdown
pip list | grep beautifulsoup4

# 3. 测试基本功能（regexp 模式）
python extract.py --input examples/wiley.md --output out/test.json

# 4. 检查输出
cat out/test.json

# 5. 测试 LangExtract 模式（需要 API key）
python extract.py \
  --input examples/wiley.md \
  --model-id gpt-4o \
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key sk-test-key \
  --output out/test_langextract.json
```

---

## 获取帮助

如果以上方案都无法解决问题，请检查：

1. 📝 [README.md](README.md) - 完整项目说明
2. 📖 [API_COMPATIBILITY.md](API_COMPATIBILITY.md) - API 兼容性说明
3. 🔧 [QWEN_USAGE.md](QWEN_USAGE.md) - Qwen 模型使用指南
4. 💻 [INSTALL.md](INSTALL.md) - 安装和使用指南

或提交 Issue 并附上：
- 完整的错误信息
- 运行命令
- Python 版本和环境信息
- `pip list` 输出

