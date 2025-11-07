#!/usr/bin/env python3
"""
LLM 调用模块 - llm_call.py

支持 OpenAI 兼容接口的大模型调用，用于期刊主办单位联网搜索
"""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[ERROR] openai package not installed. Run: pip install openai")


# ========== Prompt 模板 ==========

SEARCH_PROMPT_TEMPLATE = """期刊《{journal_name}》的主办单位是什么？ 

请提供信息来源和判断依据，优先从官方权威网站查找最新的信息（主办方可能变更），如期刊官网、主办单位官网的期刊主页或简介页面，禁用 wikipedia 或新闻类网站。

回答格式要使用 JSON 数组，包含以下字段：

1. 期刊名称
2. 主办单位，该期刊的主办方，要求直接从网页中提取，必须完全忠实于原文（不可省略、增补或做指代替换），该名称会出现在关键句子中
3. 关键句子，网页中出现的主办单位名称所在的完整句子，用于人工核验正确性，要求可以在网页上准确匹配到相应的字符串
4. 判断依据，为何判断关键句子中出现的这个单位就是主办方，逻辑是什么
5. 来源链接，信息来源网页"""


# ========== JSON 解析 ==========

def extract_json_from_text(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    从文本中提取 JSON 数组，支持多种格式
    
    Args:
        text: 可能包含 JSON 的文本
    
    Returns:
        解析后的 JSON 数组，或 None（如果解析失败）
    """
    # 策略 1: 直接解析整个文本
    try:
        data = json.loads(text.strip())
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # 如果是单个对象，包装成数组
            return [data]
    except json.JSONDecodeError:
        pass
    
    # 策略 2: 提取 ```json...``` 或 ```...``` 代码块
    json_block_pattern = r'```(?:json)?\s*([\s\S]*?)```'
    matches = re.findall(json_block_pattern, text)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            continue
    
    # 策略 3: 查找 JSON 数组（以 [ 开头，] 结尾）
    array_pattern = r'\[\s*\{[\s\S]*?\}\s*\]'
    matches = re.findall(array_pattern, text)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue
    
    # 策略 4: 查找单个 JSON 对象（以 { 开头，} 结尾）
    object_pattern = r'\{\s*"[\s\S]*?\}'
    matches = re.findall(object_pattern, text)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            continue
    
    return None


def validate_result_item(item: Dict[str, Any]) -> bool:
    """
    验证结果项是否包含所有必需字段
    
    Args:
        item: 结果项字典
    
    Returns:
        是否有效
    """
    required_fields = ["期刊名称", "主办单位", "关键句子", "判断依据", "来源链接"]
    
    for field in required_fields:
        if field not in item or not item[field]:
            return False
    
    return True


# ========== LLM 调用 ==========

def call_llm_search(
    journal_name: str,
    model_id: str,
    api_key: str,
    api_base: str,
    timeout: int = 120,
    logger = None
) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], str, float, Optional[str], Optional[str]]:
    """
    调用大模型进行联网搜索
    
    Args:
        journal_name: 期刊名称
        model_id: 模型 ID
        api_key: API Key
        api_base: API Base URL
        timeout: 请求超时时间（秒）
        logger: 日志对象（可选）
    
    Returns:
        (成功标志, 结果列表, token使用统计, token来源, 耗时, 错误类型, 错误消息)
        - 成功标志: bool
        - 结果列表: List[Dict] 或 None
        - token统计: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int} 或 None
        - token来源: "api"（API返回，精确）或 "none"（无统计）
        - 耗时: float（秒）
        - 错误类型: str 或 None
        - 错误消息: str 或 None
    """
    if not OPENAI_AVAILABLE:
        return False, None, None, "none", 0.0, "library_error", "openai package not installed"
    
    # 构造 prompt
    prompt = SEARCH_PROMPT_TEMPLATE.format(journal_name=journal_name)
    
    # 记录请求日志
    if logger:
        logger.info(f"\n{'='*60}")
        logger.info(f"[REQUEST] 期刊名称: {journal_name}")
        logger.info(f"[PROMPT]\n{prompt}")
        logger.info(f"{'='*60}\n")
    
    try:
        # 初始化客户端
        client = OpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout
        )
        
        # 调用 API
        start_time = time.time()
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
        )
        elapsed_time = time.time() - start_time
        
        # 提取响应内容
        content = response.choices[0].message.content
        
        # 提取 token 使用统计
        usage = None
        usage_source = "none"  # 'api' 或 'none'
        
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            usage_source = "api"
        
        # 记录响应日志
        if logger:
            logger.info(f"\n{'='*60}")
            logger.info(f"[RESPONSE] 期刊名称: {journal_name}")
            logger.info(f"[耗时] {elapsed_time:.2f} 秒")
            if usage:
                logger.info(f"[TOKEN] 输入: {usage['prompt_tokens']}, 输出: {usage['completion_tokens']}, 总计: {usage['total_tokens']} (来自API返回)")
            else:
                logger.info(f"[TOKEN] API 未返回 token 使用统计")
            logger.info(f"[CONTENT]\n{content}")
            logger.info(f"{'='*60}\n")
        
        # 解析 JSON
        parsed_data = extract_json_from_text(content)
        
        if parsed_data is None:
            # JSON 解析失败
            if logger:
                logger.error(f"[JSON 解析失败] 无法从响应中提取有效的 JSON")
                logger.error(f"[原始响应]\n{content}\n")
            
            return False, None, usage, usage_source, elapsed_time, "json_parse_error", "Failed to extract JSON from response"
        
        # 验证结果项
        valid_items = []
        invalid_count = 0
        
        for item in parsed_data:
            if validate_result_item(item):
                valid_items.append(item)
            else:
                invalid_count += 1
                if logger:
                    logger.warning(f"[无效结果项] 缺少必需字段: {item}")
        
        if not valid_items:
            # 所有结果项都无效
            if logger:
                logger.error(f"[验证失败] 所有结果项都缺少必需字段")
            
            return False, None, usage, usage_source, elapsed_time, "validation_error", "No valid result items found"
        
        if invalid_count > 0 and logger:
            logger.warning(f"[部分有效] 有效结果: {len(valid_items)}, 无效结果: {invalid_count}")
        
        return True, valid_items, usage, usage_source, elapsed_time, None, None
    
    except json.JSONDecodeError as e:
        error_msg = f"JSON decode error: {str(e)}"
        if logger:
            logger.error(f"[JSON 解析错误] {error_msg}")
        return False, None, None, "none", 0.0, "json_error", error_msg
    
    except Exception as e:
        error_msg = str(e)
        error_type = "unknown_error"
        
        # 检查是否是频率限制错误
        if 'rate' in error_msg.lower() or 'limit' in error_msg.lower() or '429' in error_msg:
            error_type = "rate_limit"
        # 检查是否是超时错误
        elif 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
            error_type = "timeout"
        # 检查是否是网络错误
        elif 'connection' in error_msg.lower() or 'network' in error_msg.lower():
            error_type = "network_error"
        # 检查是否是认证错误
        elif 'auth' in error_msg.lower() or 'unauthorized' in error_msg.lower() or '401' in error_msg:
            error_type = "auth_error"
        
        if logger:
            logger.error(f"[API 错误] {error_type}: {error_msg}")
        
        return False, None, None, "none", 0.0, error_type, error_msg


# ========== 成本计算 ==========

def calculate_cost(
    usage: Optional[Dict[str, int]],
    price_per_1m_input: float,
    price_per_1m_output: float
) -> Optional[float]:
    """
    计算 API 调用成本
    
    Args:
        usage: token 使用统计
        price_per_1m_input: 输入 token 单价（每 1M tokens，美元）
        price_per_1m_output: 输出 token 单价（每 1M tokens，美元）
    
    Returns:
        成本（美元）或 None
    """
    if not usage:
        return None
    
    input_cost = (usage.get('prompt_tokens', 0) / 1_000_000.0) * price_per_1m_input
    output_cost = (usage.get('completion_tokens', 0) / 1_000_000.0) * price_per_1m_output
    
    return input_cost + output_cost


# ========== 测试 ==========

if __name__ == "__main__":
    import os
    import logging
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # 测试参数
    journal_name = "Nature"
    model_id = os.environ.get("MODEL_ID", "qwen-plus")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    api_base = os.environ.get("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    if not api_key:
        print("[ERROR] Please set OPENAI_API_KEY environment variable")
        exit(1)
    
    print(f"[TEST] 测试期刊: {journal_name}")
    print(f"[TEST] 模型: {model_id}")
    print(f"[TEST] API Base: {api_base}")
    print()
    
    success, results, usage, usage_source, elapsed_time, error_type, error_msg = call_llm_search(
        journal_name=journal_name,
        model_id=model_id,
        api_key=api_key,
        api_base=api_base,
        logger=logger
    )
    
    if success:
        print(f"\n[SUCCESS] 提取 {len(results)} 条结果")
        for i, item in enumerate(results, 1):
            print(f"\n结果 {i}:")
            print(f"  期刊名称: {item.get('期刊名称', '')}")
            print(f"  主办单位: {item.get('主办单位', '')}")
            print(f"  关键句子: {item.get('关键句子', '')[:100]}...")
            print(f"  判断依据: {item.get('判断依据', '')[:100]}...")
            print(f"  来源链接: {item.get('来源链接', '')}")
        
        print(f"\n[耗时] {elapsed_time:.2f} 秒")
        
        if usage:
            token_source_label = "API返回（精确）" if usage_source == "api" else "未知"
            print(f"\n[USAGE] Token 来源: {token_source_label}")
            print(f"  输入 tokens: {usage['prompt_tokens']}")
            print(f"  输出 tokens: {usage['completion_tokens']}")
            print(f"  总计 tokens: {usage['total_tokens']}")
            
            cost = calculate_cost(usage, 2.75, 22.0)
            if cost:
                print(f"  估算成本: ${cost:.4f}")
        else:
            print(f"\n[USAGE] Token 来源: 无统计")
    else:
        print(f"\n[FAILED] {error_type}: {error_msg}")
