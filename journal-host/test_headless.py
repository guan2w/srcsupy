#!/usr/bin/env python3
"""
测试 headless 配置是否生效
"""

import os
import time

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from playwright.sync_api import sync_playwright

def load_config(path: str = "config.toml"):
    """读取配置文件"""
    if not os.path.exists(path):
        return {}
    
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
            return data.get("snapshot", {})
    except Exception as e:
        print(f"[WARNING] Failed to load config.toml: {e}")
        return {}

# 加载配置
config = load_config("config.toml")

print("=" * 60)
print("测试 headless 配置")
print("=" * 60)
print(f"配置文件内容: {config}")
print(f"headless 值: {config.get('headless', True)}")
print(f"预期行为: {'有头模式（会显示浏览器窗口）' if not config.get('headless', True) else '无头模式（不显示窗口）'}")
print("=" * 60)
print()

# 启动浏览器测试
print("[TEST] 正在启动浏览器...")

with sync_playwright() as p:
    launch_opts = {
        "headless": config.get('headless', True)
    }
    
    if config.get('proxy'):
        launch_opts['proxy'] = {'server': config['proxy']}
    
    print(f"[TEST] 浏览器启动配置: {launch_opts}")
    
    browser = p.chromium.launch(**launch_opts)
    context = browser.new_context()
    page = context.new_page()
    
    print("[TEST] 访问测试页面...")
    page.goto("https://www.baidu.com")
    
    print("[TEST] 页面已加载，等待 5 秒让你观察...")
    print("       如果是有头模式，你应该能看到浏览器窗口")
    print("       如果是无头模式，你看不到任何窗口")
    
    time.sleep(5)
    
    print("[TEST] 关闭浏览器")
    browser.close()
    
print()
print("[OK] 测试完成")
print(f"如果你看到了浏览器窗口，说明 headless=false 生效了")
print(f"如果你没看到浏览器窗口，说明可能有其他问题")


