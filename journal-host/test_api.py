#!/usr/bin/env python3
"""
测试脚本：验证 LangExtract API 兼容性

用于测试修复后的代码是否能正常调用 LangExtract API
"""

import sys
import os

# 测试是否可以导入 langextract
try:
    import langextract as lx
    print("✅ langextract 已安装")
    print(f"   版本信息: {lx.__version__ if hasattr(lx, '__version__') else '未知'}")
except ImportError:
    print("❌ langextract 未安装")
    print("   运行: pip install langextract")
    sys.exit(0)

# 测试基本的 extract 调用（不使用真实 API）
print("\n测试 extract 函数参数...")

# 准备测试数据
test_text = "Allergy, the official journal of the European Academy of Allergy and Clinical Immunology (EAACI)."

prompt = "Extract host institutions."

examples = [
    lx.data.ExampleData(
        text="Test journal is the official journal of Test Society.",
        extractions=[
            lx.data.Extraction(
                extraction_class="host_institution",
                extraction_text="Test Society",
                attributes={"type": "host"}
            )
        ]
    )
]

# 检查 extract 函数签名
import inspect
sig = inspect.signature(lx.extract)
print(f"\n📋 extract 函数参数列表:")
for param_name, param in sig.parameters.items():
    default = param.default
    if default == inspect.Parameter.empty:
        print(f"   - {param_name} (必需)")
    else:
        print(f"   - {param_name} = {default}")

# 检查是否接受 show_progress 参数
params = list(sig.parameters.keys())
if 'show_progress' in params:
    print("\n⚠️  警告: extract() 函数接受 'show_progress' 参数")
else:
    print("\n✅ 确认: extract() 函数不接受 'show_progress' 参数（这是预期的）")

# 测试不带 API key 的调用（应该报错但不是因为参数问题）
print("\n🧪 测试函数调用（不提供 API key，应该会报认证错误而非参数错误）...")
try:
    result = lx.extract(
        text_or_documents=test_text,
        prompt_description=prompt,
        examples=examples,
        model_id="gemini-2.5-flash",
        # 注意：不包含 show_progress 参数
        api_key="fake-key-for-testing"  # 假的 key，用于测试参数是否正确
    )
    print("   函数调用成功（但可能 API 认证失败）")
except TypeError as e:
    if 'show_progress' in str(e):
        print(f"   ❌ 错误: 仍然有 show_progress 参数问题: {e}")
    elif 'unexpected keyword argument' in str(e):
        print(f"   ❌ 错误: 参数问题: {e}")
    else:
        print(f"   ⚠️  其他 TypeError: {e}")
except Exception as e:
    error_type = type(e).__name__
    if 'auth' in str(e).lower() or 'api' in str(e).lower() or 'key' in str(e).lower():
        print(f"   ✅ 认证错误（预期的）: {error_type}: {str(e)[:100]}...")
    else:
        print(f"   ⚠️  其他错误: {error_type}: {str(e)[:100]}...")

print("\n" + "="*60)
print("测试完成！")
print("="*60)

print("\n💡 如果看到 '✅ 确认: extract() 函数不接受 show_progress 参数'")
print("   说明代码已经兼容最新的 LangExtract API")

