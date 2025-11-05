# 更新日志

## 2025-11-05 - 批量处理工具改进

### ✨ 新功能

#### 1. **batch_snapshot.py** - 新增 `--sheet-name` 参数

支持指定 Excel 文件的 sheet，可以使用索引或名称：

```bash
# 使用索引（默认 0，即第一个 sheet）
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --url-ranges D4:D99 \
  --sheet-name 0

# 使用名称
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --url-ranges D4:D99 \
  --sheet-name "期刊列表"
```

**使用场景：**
- Excel 文件包含多个 sheet，需要指定特定 sheet
- 不同 sheet 存储不同类型的 URL 列表

#### 2. **启动参数打印**

两个批量处理工具启动时都会打印关键配置参数，方便排错：

**batch_snapshot.py 启动输出：**
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

**batch_extract.py 启动输出：**
```
============================================================
[CONFIG] 批量信息提取工具 - 启动参数
============================================================
输入路径:      journals.xlsx
快照目录:      journals-snapshot/
并行数量:      5
模型 ID:       qwen3-vl-32b-instruct
API Base:      https://dashscope.aliyuncs.com/compatible-mode/v1
重试次数:      2
重试延迟:      5 秒
监听模式:      禁用
配置文件:      config.toml
============================================================
```

**打印信息包括：**
- ✅ 所有命令行参数
- ✅ 从配置文件读取的值
- ✅ 最终生效的配置（命令行参数 > 配置文件 > 默认值）
- ✅ 代理、超时等关键设置
- ✅ API 配置信息

**排错优势：**
1. **快速定位问题**：一眼看出使用的配置是否正确
2. **确认参数生效**：验证命令行参数是否正确覆盖了配置文件
3. **网络排查**：检查代理和超时设置是否合理
4. **API 验证**：确认使用的模型和 API 地址

---

### 🔧 技术细节

#### sheet_name 参数处理

代码会自动判断参数类型：
- 如果是数字字符串（如 "0", "1"），自动转换为整数（sheet 索引）
- 如果是文本（如 "期刊列表"），保持为字符串（sheet 名称）

```python
# 自动类型转换
sheet_name = args.sheet_name
try:
    sheet_name = int(sheet_name)  # 尝试转为整数
except (ValueError, TypeError):
    pass  # 保持为字符串
```

#### pandas 读取 Excel 的 sheet_name 参数

```python
df = pd.read_excel(
    file_path,
    sheet_name=sheet_name,  # 0 或 "Sheet1"
    usecols=[col],
    skiprows=row_start - 1,
    nrows=row_end - row_start + 1,
    header=None,
    engine='openpyxl'
)
```

---

### 📚 文档更新

- ✅ `README.md` - 添加 `--sheet-name` 参数说明和启动输出示例
- ✅ `QUICKSTART.md` - 更新参数说明和使用示例
- ✅ `CHANGELOG.md` - 新增更新日志文件（本文件）

---

### 🎯 使用建议

#### 何时使用 --sheet-name

1. **多 sheet 场景**
   ```bash
   # Sheet 0: 国内期刊
   # Sheet 1: 国际期刊
   python batch_snapshot.py \
     --url-excel journals.xlsx \
     --url-ranges D4:D99 \
     --sheet-name 0
   
   python batch_snapshot.py \
     --url-excel journals.xlsx \
     --url-ranges D4:D99 \
     --sheet-name 1
   ```

2. **命名 sheet**
   ```bash
   python batch_snapshot.py \
     --url-excel journals.xlsx \
     --url-ranges D4:D99 \
     --sheet-name "待处理列表"
   ```

#### 如何验证参数设置

运行脚本后，查看启动输出：
```
============================================================
[CONFIG] 批量快照下载工具 - 启动参数
============================================================
Sheet 名称:    期刊列表    ← 确认这里是否正确
并行数量:      3          ← 确认并行数
代理设置:      socks5://172.24.128.1:7890  ← 确认代理
============================================================
```

---

### ⚠️ 注意事项

1. **Sheet 名称区分大小写**
   - ✅ 正确：`--sheet-name "期刊列表"`
   - ❌ 错误：`--sheet-name "期刊列表"`（空格数量不同）

2. **Sheet 索引从 0 开始**
   - Sheet 1 对应索引 0
   - Sheet 2 对应索引 1

3. **验证 sheet 是否存在**
   如果指定的 sheet 不存在，会报错：
   ```
   [ERROR] Failed to read Excel: Worksheet named '不存在的sheet' not found
   ```

---

### 🔄 向后兼容性

**完全兼容旧版本！**

- 如果不指定 `--sheet-name`，默认读取第一个 sheet（索引 0）
- 现有的所有命令行参数和功能保持不变

```bash
# 旧命令仍然正常工作
python batch_snapshot.py \
  --url-excel journals.xlsx \
  --url-ranges D4:D99,F4:F99
```

---

### 📝 后续计划

- [ ] 支持从多个 sheet 同时读取 URL
- [ ] 支持 CSV 文件作为输入
- [ ] 添加配置验证工具
- [ ] 支持导出配置到文件

---

## 历史版本

### 2025-11-05 - 初始版本

- ✅ batch_snapshot.py - 批量快照下载
- ✅ batch_extract.py - 批量信息提取
- ✅ 并行处理、断点续传
- ✅ 详细日志记录
- ✅ watch 持续监听模式

