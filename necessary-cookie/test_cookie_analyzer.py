#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cookie分析工具测试脚本
"""

from cookie_analyzer import CookieAnalyzer

def test_curl_parsing():
    """测试curl命令解析功能"""
    print("🧪 测试curl命令解析...")
    
    test_curl = """curl 'https://httpbin.org/cookies' \\
  -H 'accept: application/json' \\
  -b 'test_cookie=test_value; another_cookie=another_value'"""
    
    analyzer = CookieAnalyzer()
    
    try:
        url, headers, cookies = analyzer.parse_curl_command(test_curl)
        
        # 验证解析结果
        assert url == "https://httpbin.org/cookies"
        assert "accept" in headers
        assert "test_cookie" in cookies
        assert cookies["test_cookie"] == "test_value"
        
        print("✅ curl命令解析测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ curl命令解析测试失败: {e}")
        return False

def test_with_httpbin():
    """使用httpbin.org进行完整的cookie分析测试"""
    print("\n🧪 使用httpbin.org进行完整测试...")
    
    test_curl = """curl 'https://httpbin.org/cookies' \\
  -H 'accept: application/json' \\
  -b 'session_id=abc123; user_pref=dark_mode; analytics_id=xyz789'"""
    
    analyzer = CookieAnalyzer(expected_key="cookies", delay=0.2)
    
    try:
        url, headers, cookies = analyzer.parse_curl_command(test_curl)
        print(f"解析到 {len(cookies)} 个cookies")
        
        necessary_cookies = analyzer.find_necessary_cookies(url, headers, cookies)
        
        print(f"✅ 完整测试完成！从 {len(cookies)} 个cookie中识别出 {len(necessary_cookies)} 个必要cookie")
        return True
        
    except Exception as e:
        print(f"❌ 完整测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 50)
    print("Cookie分析工具测试套件")
    print("=" * 50)
    
    tests = [
        ("curl命令解析", test_curl_parsing),
        ("httpbin.org完整测试", test_with_httpbin),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} 异常: {e}")
    
    print(f"\n{'='*50}")
    print(f"测试结果: {passed}/{len(tests)} 通过")
    
    if passed == len(tests):
        print("🎉 所有测试通过！")
        print("\n使用方法: python cookie_analyzer.py")
    else:
        print(f"⚠️  有 {len(tests) - passed} 个测试失败")

if __name__ == "__main__":
    main() 