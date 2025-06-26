#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cookie必要性分析工具
用于确定curl请求中哪些cookie项是必须的
"""

import requests
import json
import re
import sys
import time
import argparse
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from urllib.parse import unquote

class CookieAnalyzer:
    def __init__(self, expected_key: str = "status", delay: float = 0.5, retry_count: int = 3):
        """
        初始化Cookie分析器
        
        Args:
            expected_key: 期望在响应JSON中存在的键
            delay: 请求间隔时间（秒）
            retry_count: 网络异常重试次数
        """
        self.expected_key = expected_key
        self.delay = delay
        self.retry_count = retry_count
        self.session = requests.Session()
        
    def parse_curl_command(self, curl_command: str) -> Tuple[str, Dict[str, str], Dict[str, str]]:
        """
        解析curl命令，提取URL、headers和cookies
        
        Args:
            curl_command: curl命令字符串
            
        Returns:
            (url, headers, cookies)
        """
        # 提取URL
        url_match = re.search(r"curl\s+'([^']+)'", curl_command)
        if not url_match:
            raise ValueError("无法从curl命令中提取URL")
        url = url_match.group(1)
        
        # 提取headers
        headers = {}
        header_pattern = r"-H\s+'([^:]+):\s*([^']+)'"
        for match in re.finditer(header_pattern, curl_command):
            key, value = match.groups()
            headers[key] = value
            
        # 提取cookies
        cookies = {}
        cookie_match = re.search(r"-b\s+'([^']+)'", curl_command)
        if cookie_match:
            cookie_string = cookie_match.group(1)
            cookie_pairs = cookie_string.split('; ')
            for pair in cookie_pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    cookies[key.strip()] = value.strip()
        
        return url, headers, cookies
    
    def _is_network_error(self, exception: Exception) -> bool:
        """
        判断是否为网络相关异常
        
        Args:
            exception: 异常对象
            
        Returns:
            是否为网络异常
        """
        error_message = str(exception).lower()
        network_errors = [
            'read timed out',
            'timeout',
            'connection error',
            'connection timeout',
            'connection refused',
            'network is unreachable',
            'name resolution failed',
            'connection aborted',
            'connection reset'
        ]
        return any(error in error_message for error in network_errors)
    
    def test_request(self, url: str, headers: Dict[str, str], cookies: Dict[str, str], return_data: bool = False) -> Tuple[bool, Optional[Dict]]:
        """
        测试请求是否成功，支持网络异常重试
        
        Args:
            url: 请求URL
            headers: 请求头
            cookies: cookie字典
            return_data: 是否返回响应数据
            
        Returns:
            如果return_data为True，返回(是否成功, 响应数据)
            如果return_data为False，返回(是否成功, None)
        """
        last_exception = None
        
        for attempt in range(self.retry_count + 1):  # 包括第一次尝试
            try:
                response = self.session.get(url, headers=headers, cookies=cookies, timeout=30)
                
                # 检查状态码
                if response.status_code != 200:
                    return False, None
                    
                # 检查响应内容是否为JSON且包含期望的键
                try:
                    json_data = response.json()
                    success = self.expected_key in json_data
                    if return_data and success:
                        return success, json_data
                    else:
                        return success, None
                except (json.JSONDecodeError, KeyError):
                    return False, None
                    
            except Exception as e:
                last_exception = e
                
                # 如果是网络异常且还有重试机会
                if self._is_network_error(e) and attempt < self.retry_count:
                    print(f"    ⚠️  网络异常 (第{attempt + 1}次尝试): {e}")
                    print(f"    🔄 {self.delay}秒后重试...")
                    time.sleep(self.delay)
                    continue
                else:
                    # 非网络异常或已达到最大重试次数
                    if self._is_network_error(e):
                        print(f"    ❌ 网络异常 (已重试{self.retry_count}次): {e}")
                    else:
                        print(f"    ❌ 请求异常: {e}")
                    return False, None
        
        return False, None
    
    def find_necessary_cookies(self, url: str, headers: Dict[str, str], cookies: Dict[str, str]) -> Dict[str, str]:
        """
        通过逐项移除的方式找到必要的cookie
        
        Args:
            url: 请求URL
            headers: 请求头
            cookies: 完整的cookie字典
            
        Returns:
            必要的cookie字典
        """
        print(f"开始分析，共有 {len(cookies)} 个cookie项...")
        print(f"期望响应包含键: {self.expected_key}")
        print("-" * 50)
        
        # 首先测试完整的cookie是否工作
        print("测试完整cookie...")
        if not self.test_request(url, headers, cookies)[0]:
            print("❌ 完整cookie请求失败！请检查curl命令是否正确")
            return {}
        print("✅ 完整cookie请求成功")
        
        necessary_cookies = cookies.copy()
        removed_cookies = []
        
        # 逐个尝试移除cookie
        for cookie_name in list(cookies.keys()):
            print(f"\n尝试移除cookie: {cookie_name}")
            
            # 创建临时cookie字典（移除当前cookie）
            temp_cookies = necessary_cookies.copy()
            if cookie_name in temp_cookies:
                removed_value = temp_cookies.pop(cookie_name)
                
                # 测试移除后是否仍然成功
                time.sleep(self.delay)  # 避免请求过于频繁
                success, data = self.test_request(url, headers, temp_cookies, True)
                if success:
                    print(f"  ✅ 可以移除 '{cookie_name}'")
                    necessary_cookies = temp_cookies
                    removed_cookies.append((cookie_name, removed_value))
                    # 打印指定键的值的前100个字符
                    if data and self.expected_key in data:
                        key_value = str(data[self.expected_key])
                        print(f"    📄 {self.expected_key}: {key_value[:100]}{'...' if len(key_value) > 100 else ''}")
                else:
                    print(f"  ❌ 不能移除 '{cookie_name}' - 这是必要的cookie")
        
        print(f"\n" + "="*60)
        print(f"分析完成！")
        print(f"原始cookie数量: {len(cookies)}")
        print(f"必要cookie数量: {len(necessary_cookies)}")
        print(f"已移除cookie数量: {len(removed_cookies)}")
        
        if removed_cookies:
            print(f"\n已移除的cookie:")
            for name, value in removed_cookies:
                print(f"  - {name}: {value[:50]}...")
        
        if necessary_cookies:
            print(f"\n✅ 必要的cookie:")
            for name, value in necessary_cookies.items():
                print(f"  - {name}: {value[:50]}...")
        
        return necessary_cookies
    
    def generate_minimal_curl(self, url: str, headers: Dict[str, str], necessary_cookies: Dict[str, str]) -> str:
        """
        生成使用最小必要cookie的curl命令
        
        Args:
            url: 请求URL
            headers: 请求头
            necessary_cookies: 必要的cookie字典
            
        Returns:
            最小化的curl命令
        """
        curl_parts = [f"curl '{url}'"]
        
        # 添加headers
        for key, value in headers.items():
            curl_parts.append(f"  -H '{key}: {value}'")
        
        # 添加必要的cookies
        if necessary_cookies:
            cookie_string = '; '.join([f"{k}={v}" for k, v in necessary_cookies.items()])
            curl_parts.append(f"  -b '{cookie_string}'")
        
        return " \\\n".join(curl_parts)

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Cookie必要性分析工具 - 确定curl请求中哪些cookie是必须的",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cookie_analyzer.py                           # 使用默认配置
  python cookie_analyzer.py --delay 2.0               # 设置请求间隔为2秒
  python cookie_analyzer.py --retry 5                 # 设置重试次数为5次
  python cookie_analyzer.py --file my_curls.txt       # 使用自定义curl文件
  python cookie_analyzer.py --output-dir ./my_results # 自定义输出目录
        """
    )
    
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=1.0,
        help="请求间隔时间（秒），默认1.0秒"
    )
    
    parser.add_argument(
        "--retry", "-r", 
        type=int,
        default=3,
        help="网络异常重试次数，默认3次"
    )
    
    parser.add_argument(
        "--file", "-f",
        type=str,
        default="curl.txt",
        help="curl命令文件路径，默认curl.txt"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="result",
        help="结果输出目录，默认result"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="静默模式，减少输出信息"
    )
    
    return parser.parse_args()

def ensure_output_dir(output_dir: str) -> str:
    """确保输出目录存在并返回时间戳前缀"""
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成时间戳前缀 YYMMDD.hhmmss-
    timestamp = datetime.now().strftime("%y%m%d.%H%M%S-")
    return timestamp

def main():
    """主函数，从curl.txt文件读取命令并进行分析"""
    args = parse_arguments()
    
    # 确保输出目录存在并获取时间戳前缀
    timestamp_prefix = ensure_output_dir(args.output_dir)
    
    if not args.quiet:
        print("=" * 60)
        print("Cookie必要性分析工具")
        print("=" * 60)
        print(f"配置: 延迟={args.delay}s, 重试={args.retry}次, 文件={args.file}")
        print(f"输出: {args.output_dir}/ (前缀: {timestamp_prefix})")
        print("-" * 60)
    
    try:
        # 动态导入以支持自定义文件路径
        sys.path.insert(0, os.path.dirname(os.path.abspath(args.file)))
        from curl_reader import CurlFileReader
        
        # 读取curl命令
        reader = CurlFileReader(args.file)
        commands = reader.read_all_commands()
        
        if not commands:
            print(f"❌ {args.file}文件中没有找到有效的curl命令")
            print(f"💡 请在{args.file}文件中添加curl命令，格式参考文件注释")
            return
        
        if not args.quiet:
            print(f"从{args.file}读取到 {len(commands)} 个curl命令:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd.name} (期望键: {cmd.expected_key})")
                sys.stdout.flush()  # 强制刷新输出缓冲区
            print()  # 添加空行确保输出完整
        
        # 选择要分析的命令
        if len(commands) == 1:
            selected_cmd = commands[0]
            if not args.quiet:
                print(f"\n自动选择: {selected_cmd.name}")
        else:
            while True:
                try:
                    choice = input(f"\n请选择要分析的命令 (1-{len(commands)}): ").strip()
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(commands):
                        selected_cmd = commands[choice_idx]
                        break
                    else:
                        print(f"请输入1-{len(commands)}之间的数字")
                except ValueError:
                    print("请输入有效的数字")
        
        # 创建分析器并执行分析
        if not args.quiet:
            print(f"\n开始分析: {selected_cmd.name}")
            print("-" * 40)
        
        analyzer = CookieAnalyzer(
            expected_key=selected_cmd.expected_key, 
            delay=args.delay, 
            retry_count=args.retry
        )
        
        # 解析curl命令
        url, headers, cookies = analyzer.parse_curl_command(selected_cmd.curl_command)
        
        if not args.quiet:
            print(f"📍 URL: {url[:60]}{'...' if len(url) > 60 else ''}")
            print(f"📄 Headers: {len(headers)} 个")
            print(f"🍪 Cookies: {len(cookies)} 个")
        
        if len(cookies) == 0:
            print("⚠️  该命令没有cookie，无需分析")
            return
        
        # 分析必要的cookie
        necessary_cookies = analyzer.find_necessary_cookies(url, headers, cookies)
        
        # 生成结果文件
        if necessary_cookies or len(cookies) > 0:
            if not args.quiet:
                print(f"\n" + "="*60)
                print("生成最小化curl命令:")
                print("-" * 60)
            
            minimal_curl = analyzer.generate_minimal_curl(url, headers, necessary_cookies)
            if not args.quiet:
                print(minimal_curl)
            
            # 保存结果到文件（使用时间戳前缀）
            safe_name = selected_cmd.name.replace(' ', '_').replace('/', '_').replace('\\', '_')
            output_prefix = os.path.join(args.output_dir, f"{timestamp_prefix}{safe_name}")
            
            # 保存最小化curl命令
            curl_file = f"{output_prefix}_minimal_curl.sh"
            with open(curl_file, "w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n")
                f.write(f"# 最小化的curl命令: {selected_cmd.name}\n")
                f.write(f"# 分析时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 配置: 延迟={args.delay}s, 重试={args.retry}次\n\n")
                f.write(minimal_curl)
            
            # 保存分析结果
            result_file = f"{output_prefix}_analysis_result.json"
            with open(result_file, "w", encoding="utf-8") as f:
                result = {
                    "command_name": selected_cmd.name,
                    "analysis_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "timestamp_prefix": timestamp_prefix,
                    "config": {
                        "delay": args.delay,
                        "retry_count": args.retry,
                        "expected_key": selected_cmd.expected_key
                    },
                    "original_cookies_count": len(cookies),
                    "necessary_cookies_count": len(necessary_cookies),
                    "necessary_cookies": necessary_cookies,
                    "removed_cookies_count": len(cookies) - len(necessary_cookies),
                    "url": url
                }
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ 结果已保存:")
            print(f"  📝 {curl_file}")
            print(f"  📊 {result_file}")
        else:
            print(f"\n✨ 所有cookie都可以移除，该请求不依赖任何cookie！")
        
    except FileNotFoundError as e:
        print(f"❌ 文件错误: {e}")
        print(f"💡 请确保{args.file}文件存在且格式正确")
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        if not args.quiet:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()