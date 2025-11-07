#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curl文件读取和解析模块
负责从curl.txt文件中读取和解析curl命令
"""

import os
import re
from typing import List, Dict, Optional, Tuple

class CurlCommand:
    """表示一个curl命令的数据类"""
    
    def __init__(self, name: str, curl_command: str, 
                 expected_json_key: Optional[str] = None, 
                 expected_keyword_re: Optional[str] = None):
        """
        初始化curl命令对象
        
        Args:
            name: 命令名称
            curl_command: curl命令字符串
            expected_json_key: 期望的JSON键名 (与expected_keyword_re互斥)
            expected_keyword_re: 期望的关键字正则表达式 (与expected_json_key互斥)
        """
        if expected_json_key is not None and expected_keyword_re is not None:
            raise ValueError("expected_json_key 和 expected_keyword_re 不能同时设置")
            
        self.name = name
        self.curl_command = curl_command.strip()
        self.expected_json_key = expected_json_key
        self.expected_keyword_re = expected_keyword_re
    
    def __str__(self):
        parts = [f"name='{self.name}'"]
        if self.expected_json_key is not None:
            parts.append(f"expected_json_key='{self.expected_json_key}'")
        if self.expected_keyword_re is not None:
            parts.append(f"expected_keyword_re='{self.expected_keyword_re}'")
        return f"CurlCommand({', '.join(parts)})"
    
    def __repr__(self):
        return self.__str__()

class CurlFileReader:
    """curl.txt文件读取器"""
    
    def __init__(self, file_path: str = "curl.txt"):
        """
        初始化文件读取器
        
        Args:
            file_path: curl.txt文件路径
        """
        self.file_path = file_path
    
    def read_all_commands(self) -> List[CurlCommand]:
        """
        读取所有curl命令
        
        Returns:
            curl命令列表
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"找不到curl配置文件: {self.file_path}")
        
        commands = []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析curl命令块
            blocks = self._parse_curl_blocks(content)
            
            for block in blocks:
                command = self._parse_single_block(block)
                if command:
                    commands.append(command)
                    
        except Exception as e:
            raise RuntimeError(f"读取curl文件失败: {e}")
        
        return commands
    

    
    def _parse_curl_blocks(self, content: str) -> List[str]:
        """
        解析curl命令块
        
        Args:
            content: 文件内容
            
        Returns:
            curl命令块列表
        """
        blocks = []
        lines = content.split('\n')
        current_block = []
        in_block = False
        
        for line in lines:
            line = line.strip()
            
            if line == '[CURL_START]':
                in_block = True
                current_block = []
            elif line == '[CURL_END]':
                if in_block and current_block:
                    blocks.append('\n'.join(current_block))
                in_block = False
                current_block = []
            elif in_block:
                current_block.append(line)
        
        return blocks
    
    def _parse_single_block(self, block: str) -> Optional[CurlCommand]:
        """
        解析单个curl命令块
        
        Args:
            block: 命令块内容
            
        Returns:
            解析后的curl命令对象
        """
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        if not lines:
            return None
        
        name = ""
        expected_json_key: Optional[str] = None
        expected_keyword_re: Optional[str] = None
        curl_lines = []
        
        # 解析配置行和curl命令行
        for line in lines:
            if line.startswith('name='):
                name = line[5:].strip()
            elif line.startswith('expected_json_key='):
                expected_json_key = line[20:].strip()
            elif line.startswith('expected_keyword_re='):
                expected_keyword_re = line[22:].strip()
            elif line.startswith('curl ') or (curl_lines and line.strip()):
                # curl命令行或者续行
                curl_lines.append(line)
        
        if not curl_lines:
            return None
        
        # 如果没有名称，使用URL作为名称
        if not name:
            curl_command = ' '.join(curl_lines)
            url_match = re.search(r"curl\s+'([^']+)'", curl_command)
            if url_match:
                url = url_match.group(1)
                name = f"Command for {url[:50]}..."
            else:
                name = "Unnamed Command"
        
        curl_command = ' '.join(curl_lines)
        try:
            return CurlCommand(name, curl_command, expected_json_key, expected_keyword_re)
        except ValueError as e:
            # 包装错误并提供更多上下文
            raise ValueError(f"命令 '{name}' 的配置无效: {e}")
    


def main():
    """测试curl文件读取功能"""
    reader = CurlFileReader()
    
    try:
        commands = reader.read_all_commands()
        print(f"找到 {len(commands)} 个curl命令:")
        
        for i, cmd in enumerate(commands, 1):
            print(f"{i}. {cmd.name}")
            if cmd.expected_json_key is not None:
                print(f"   期望JSON键名: {cmd.expected_json_key}")
            if cmd.expected_keyword_re is not None:
                print(f"   期望关键字正则: {cmd.expected_keyword_re}")
            print(f"   命令长度: {len(cmd.curl_command)} 字符")
            print()
            
    except Exception as e:
        print(f"读取失败: {e}")

if __name__ == "__main__":
    main() 