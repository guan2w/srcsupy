# Prompt 模板目录

本目录存放所有 LLM 调用的 Prompt 模板，便于统一维护和版本管理。

## 📁 文件说明

### search.txt
- **用途**: 联网搜索主办单位（batch_search.py）
- **参数**: `{journal_name}`
- **输出字段**: 期刊名称、主办单位、关键句子、判断依据、来源链接

### url_scan.txt
- **用途**: 深度扫描指定 URL（batch_url_scan.py）
- **参数**: `{journal_name}`, `{url1}`, `{url2}`
- **输出字段**: 期刊名称、关联单位、关键句子、信息位置、来源链接1、来源链接2

## 🔧 使用方法

Prompt 模板使用 Python 的 `str.format()` 方法进行变量替换：

```python
prompt = load_prompt('search.txt')
filled_prompt = prompt.format(journal_name="Nature")
```

## ✏️ 编辑规范

1. **变量占位符**: 使用 `{variable_name}` 格式
2. **文件编码**: UTF-8
3. **换行符**: 保持一致（建议 LF）
4. **版本控制**: 重大修改建议创建新版本（如 `search_v2.txt`）

## 📝 添加新 Prompt

1. 在本目录创建新的 `.txt` 文件
2. 在 `llm_call.py` 中添加对应的加载函数
3. 更新本 README 文档

## 🔄 版本历史

- 2025-11-07: 初始版本，迁移 search.txt 和 url_scan.txt

