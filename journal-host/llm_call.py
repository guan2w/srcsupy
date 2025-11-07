#!/usr/bin/env python3
"""
LLM 调用模块 - llm_call.py

通用的 OpenAI 兼容接口调用模块，支持 JSON 格式输出
用于各种需要结构化输出的 LLM 任务
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[ERROR] openai package not installed. Run: pip install openai")


# ========== Prompt 加载 ==========

def load_prompt(filename: str) -> str:
    """
    从 prompts 目录加载 Prompt 模板
    
    Args:
        filename: Prompt 文件名（如 'search.txt'）
    
    Returns:
        Prompt 模板内容
    """
    # 获取当前文件所在目录
    current_dir = Path(__file__).parent
    prompt_file = current_dir / "prompts" / filename
    
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_file}")
    except Exception as e:
        raise Exception(f"加载 Prompt 失败: {e}")


# ========== Prompt 模板（从文件加载）==========

# 尝试从 prompts/ 目录加载，失败则使用内嵌的默认版本
try:
    SEARCH_PROMPT_TEMPLATE = load_prompt('search.txt')
except Exception as e:
    print(f"[WARNING] 无法从文件加载 search prompt，使用内嵌版本: {e}")
    SEARCH_PROMPT_TEMPLATE = """期刊《{journal_name}》的主办单位是什么？ 

请提供信息来源和判断依据，优先从官方权威网站查找最新的信息（主办方可能变更），如期刊官网、主办单位官网的期刊主页或简介页面，禁用 wikipedia 或新闻类网站。

回答格式要使用 JSON 数组，包含以下字段：

1. 期刊名称
2. 主办单位，该期刊的主办方，要求直接从网页中提取，必须完全忠实于原文（不可省略、增补或做指代替换），该名称会出现在关键句子中
3. 关键句子，网页中出现的主办单位名称所在的完整句子，用于人工核验正确性，要求可以在网页上准确匹配到相应的字符串
4. 判断依据，为何判断关键句子中出现的这个单位就是主办方，逻辑是什么
5. 来源链接，信息来源网页"""

try:
    URL_SCAN_PROMPT_TEMPLATE = load_prompt('url_scan.txt')
except Exception as e:
    print(f"[WARNING] 无法从文件加载 url_scan prompt，使用内嵌版本: {e}")
    URL_SCAN_PROMPT_TEMPLATE = """**角色设定**

你是一名精通多语言的学术情报分析专家，具备出色的英语及其他外语文献阅读理解能力。你擅长从全球各地的期刊官网中，精准捕捉并提取机构关联信息，不受语言和网站结构差异的影响。

**核心任务**

我将按照 期刊名称、URL1、URL2 的格式提供信息。你的核心任务是：

1. **深度扫描**：仔细分析给定URL网页的全部文本内容（包括页脚、关于页面、编委信息、作者指南、期刊简介等所有可能区域）。

2. **多语言关键词匹配**：不仅依赖"sponsored by"等标准短语，还需敏锐识别各种语言和文化背景下表示"主办/出版/所属/合作"关系的表达。以下是为您扩展的**多语言关键词库**：

    | 关系类型 | 关键信号词（包括但不限于） |
    | --- | --- |
    | **出版/主办** | `Published by`, `Publisher:`, `Owned by`, `Ownership:`, `journal of`, `publication of`, `A [单位名] publication`, `Imprint of [单位名]`, `Copyright © [单位名]`, `© [单位名]`, `All rights reserved by [单位名]` |
    | **学会/协会主办** | `Society`, `Association`, `Institute`, `Academy`, `On behalf of` ,`Affiliated with`,`Affiliation` |
    | **合作/协办** | `Cooperation partners`, `In cooperation with`, `In collaboration with`, `In association with`, `Partners`, `Societies and partnerships` |
    | **版权** | `Copyright © [单位名]`, `© [单位名]` |
    | **其他关联** | `Edit`, `Affiliate` |
    | **法语** | `Publié par`, `Édité par`, `Revue officielle de`, `Propriété de` |
    | **德语** | `Veröffentlicht von`, `Herausgegeben von`, `Eigentümer:`, `Offizielle Zeitschrift der` |
    | **西班牙语** | `Publicado por`, `Editado por`, `Propiedad de` |

3. **上下文理解**：即使没有直接的关键词，也能通过分析句子上下文（如"This journal is part of the Springer Nature group"）或章节标题（如"Partners"、"Cooperation partners"）来推断关联单位。**注意**一句话中可能存在多个主办单位

4. **信息聚合**：对同一链接，将所有找到的符合条件的主办单位、合作单位、关键句子和信息位置分别用英文分号隔开，全部采集。**对于合作方信息，需明确标注其关系**（例如：`合作方: AASHE`）。

5. **图像识别** 页面中出现的图片，也需要识别其文字中是否存在所需的信息。

6. **重点关注单词**：需重点关注`Affiliated with [单位名]`,`Affiliation`、`Copyright © [单位名]`, `© [单位名]`这几种情况，这些词语后的单位名一定为关联单位。

7. **`© [单位名]`使用优先级**：优先使用位置最靠上的单位名称作为关联单位。

**输出格式与规则**

输出的结果使用 JSON 格式，各字段要求如下：

| 期刊名称 | 关联单位 | 关键句子 | 信息位置 | 来源链接1 | 来源链接2 |
| --- | --- | --- | --- | --- | --- |
| [名称] | [URL1找到的所有单位及关系; URL2找到的所有单位及关系] | [URL1对应的所有原句; URL2对应的所有原句] | [URL1信息位置; URL2信息位置] |  |  |

**核心处理规则：**

- **独立验证，精确对应**：**必须对每个URL进行完全独立的分析**。"关联单位"、"关键句子"、"信息位置"三列的内容必须严格与"来源链接1"和"来源链接2"横向对应。

- **关联单位列填写规则（最重要修改）**：
    - 在"关联单位"列中，每个分号`;`前面的内容**必须且仅能**来源于对应的URL。
    - **采集范围**：包括出版方/主办方，以及通过"Cooperation partners"等标识的合作机构，也包括从图片文字中识别出的相关单位。
    - **关系标注**：建议在单位前用简短词语标注关系，例如：`出版方: Emerald Publishing; 合作方: AASHE, ...`。
    - **【新增规则】"未明确提及"的使用限制**：**仅当某个URL经过全面扫描后，确实找不到任何关联单位信息时，才在该URL对应的位置填写"未明确提及"。如果该URL包含有效信息，则只输出有效信息。**

- **全面采集**：同一页面内找到的所有符合条件的单位、句子和位置，均需用英文分号`;`隔开，全部填入相应单元格。

- **精准定位**：关键句子必须是网页上的完整原句。"信息位置"需明确。

- **处理缺失**：若某个链接无法访问或内容完全无关，则其对应的"关联单位"、"关键句子"、"信息位置"可留空或标注"链接无效/内容不相关"。**"未明确提及"仅用于链接有效但经分析无相关信息的情况。**

- **输出规则** 同一本期刊，输出结果只能有一行。

**我的输入信息（请开始处理以下期刊）**

期刊名称：{journal_name}
URL1：{url1}
URL2：{url2}"""

# 必需字段定义
SEARCH_REQUIRED_FIELDS = ["期刊名称", "主办单位", "关键句子", "判断依据", "来源链接"]
SCAN_REQUIRED_FIELDS = ["期刊名称", "关联单位", "关键句子", "信息位置", "来源链接1", "来源链接2"]


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


def validate_result_item(item: Dict[str, Any], required_fields: List[str] = None) -> bool:
    """
    验证结果项是否包含所有必需字段
    
    Args:
        item: 结果项字典
        required_fields: 必需字段列表（默认为搜索任务的字段）
    
    Returns:
        是否有效
    """
    if required_fields is None:
        required_fields = SEARCH_REQUIRED_FIELDS
    
    for field in required_fields:
        if field not in item or not item[field]:
            return False
    
    return True


# ========== 通用 LLM 调用（JSON 输出）==========

def call_llm_with_json_output(
    prompt: str,
    model_id: str,
    api_key: str,
    api_base: str,
    timeout: int = 120,
    temperature: float = 0.1,
    required_fields: Optional[List[str]] = None,
    validator: Optional[Callable[[Dict[str, Any]], bool]] = None,
    logger = None
) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], str, float, Optional[str], Optional[str]]:
    """
    通用的 LLM 调用函数，要求返回 JSON 格式
    
    Args:
        prompt: 提示词
        model_id: 模型 ID
        api_key: API Key
        api_base: API Base URL
        timeout: 请求超时时间（秒）
        temperature: 温度参数
        required_fields: 必需字段列表（用于默认验证）
        validator: 自定义验证函数（优先级高于 required_fields）
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
    
    # 记录请求日志
    if logger:
        logger.info(f"\n{'='*60}")
        logger.info(f"[REQUEST] 模型: {model_id}")
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
            temperature=temperature,
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
            logger.info(f"[RESPONSE] 模型: {model_id}")
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
        
        # 确定使用哪个验证函数
        if validator:
            validate_fn = validator
        elif required_fields:
            validate_fn = lambda item: validate_result_item(item, required_fields)
        else:
            validate_fn = validate_result_item
        
        for item in parsed_data:
            if validate_fn(item):
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


# ========== 向后兼容：保留原有的 call_llm_search 函数 ==========

def call_llm_search(
    journal_name: str,
    model_id: str,
    api_key: str,
    api_base: str,
    timeout: int = 120,
    logger = None
) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], str, float, Optional[str], Optional[str]]:
    """
    调用大模型进行联网搜索（向后兼容函数）
    
    Args:
        journal_name: 期刊名称
        model_id: 模型 ID
        api_key: API Key
        api_base: API Base URL
        timeout: 请求超时时间（秒）
        logger: 日志对象（可选）
    
    Returns:
        (成功标志, 结果列表, token使用统计, token来源, 耗时, 错误类型, 错误消息)
    """
    # 构造 prompt
    prompt = SEARCH_PROMPT_TEMPLATE.format(journal_name=journal_name)
    
    # 调用通用函数
    return call_llm_with_json_output(
        prompt=prompt,
        model_id=model_id,
        api_key=api_key,
        api_base=api_base,
        timeout=timeout,
        temperature=0.1,
        required_fields=SEARCH_REQUIRED_FIELDS,
        logger=logger
    )


def call_llm_url_scan(
    journal_name: str,
    url1: str,
    url2: str,
    model_id: str,
    api_key: str,
    api_base: str,
    timeout: int = 180,
    logger = None
) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], str, float, Optional[str], Optional[str]]:
    """
    调用大模型进行 URL 深度扫描
    
    Args:
        journal_name: 期刊名称
        url1: 第一个 URL（期刊官方简介链接）
        url2: 第二个 URL（主办单位官方链接）
        model_id: 模型 ID
        api_key: API Key
        api_base: API Base URL
        timeout: 请求超时时间（秒）
        logger: 日志对象（可选）
    
    Returns:
        (成功标志, 结果列表, token使用统计, token来源, 耗时, 错误类型, 错误消息)
    """
    # 构造 prompt
    prompt = URL_SCAN_PROMPT_TEMPLATE.format(
        journal_name=journal_name,
        url1=url1,
        url2=url2
    )
    
    # 调用通用函数
    return call_llm_with_json_output(
        prompt=prompt,
        model_id=model_id,
        api_key=api_key,
        api_base=api_base,
        timeout=timeout,
        temperature=0.1,
        required_fields=SCAN_REQUIRED_FIELDS,
        logger=logger
    )


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
