#!/usr/bin/env python3
"""
期刊主办单位自动抽取工具

使用 LangExtract + OpenAI 兼容接口从期刊介绍文本中抽取主办单位信息。
支持规则回退、名称清洗等功能。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    import langextract as lx
    LANGEXTRACT_AVAILABLE = True
except ImportError:
    LANGEXTRACT_AVAILABLE = False
    print("[WARNING] langextract not installed, will use regexp fallback only", file=sys.stderr)

try:
    import markdown
    from bs4 import BeautifulSoup
    MARKDOWN_PARSER_AVAILABLE = True
except ImportError:
    MARKDOWN_PARSER_AVAILABLE = False
    print("[WARNING] markdown/beautifulsoup4 not installed, text extraction may be less accurate", file=sys.stderr)


# ========== 配置常量 ==========

# 关键短语列表（用于句子筛选）
KEY_PHRASES = [
    "on behalf of", "official journal of", "official publication of",
    "affiliate", "edited by", "owned", "in association with",
    "responsible for", "supervised by", "sponsored by", "patronage",
    "compile", "in partnership with", "in cooperation with",
    "the backing of", "administrated by", "university press",
    "funded by", "published by", "publisher",
    "copyright", "©"
]

# 机构类型关键词映射
TYPE_KEYWORDS = {
    "host": ["official journal of", "official publication of", "on behalf of", 
             "sponsored by", "patronage", "academy", "society"],
    "publisher": ["published by", "publisher", "university press"],
    "copyright": ["copyright", "©", "all rights reserved"]
}

# 机构名称常见后缀（用于正则提取）
INSTITUTION_SUFFIXES = [
    r"Inc\.?", r"Ltd\.?", r"LLC", r"Corp\.?", r"Co\.?",
    r"Society", r"Academy", r"Association", r"Institute",
    r"University", r"Press", r"Foundation", r"Group",
    r"A/S", r"GmbH", r"S\.A\.", r"PLC"
]


# ========== 文本处理函数 ==========

def markdown_to_plain_text(text: str) -> str:
    """
    将 Markdown 文本转换为纯文本（类似 JS 的 element.textContent）
    使用 markdown + BeautifulSoup4 组合
    """
    if not MARKDOWN_PARSER_AVAILABLE:
        # 回退到简单的正则清理
        return clean_markdown(text)
    
    try:
        # 将 Markdown 转为 HTML
        html = markdown.markdown(text)
        # 使用 BeautifulSoup 提取纯文本
        soup = BeautifulSoup(html, 'html.parser')
        plain_text = soup.get_text(separator=' ', strip=True)
        # 清理多余空格
        plain_text = re.sub(r'\s+', ' ', plain_text)
        return plain_text.strip()
    except Exception as e:
        print(f"[WARNING] Failed to parse markdown: {e}, falling back to regex", file=sys.stderr)
        return clean_markdown(text)


def clean_markdown(text: str) -> str:
    """清理 Markdown 标记（简单正则方案，作为回退）"""
    # 移除链接 [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 移除加粗 **text**
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    # 移除斜体 *text*
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    # 移除行内代码 `code`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    return text


def split_sentences(text: str) -> List[Tuple[str, int]]:
    """
    分割句子并返回 (句子, 起始位置) 的列表
    支持中英文标点符号
    改进：先按段落分，再按句子分，避免超长句子
    """
    # 先按段落分割（双换行或多个换行）
    paragraphs = re.split(r'\n\s*\n', text)
    
    sentences = []
    current_pos = 0
    
    for paragraph in paragraphs:
        if not paragraph.strip():
            current_pos += len(paragraph) + 2  # +2 for \n\n
            continue
        
        # 在段落内按句子分割
        # 避免在缩写（如 U.S., Dr., Inc.）处分割
        sentence_pattern = r'[。！？!?]\s+|(?<=[a-z])\.\s+(?=[A-Z])|(?<=[A-Z][a-z]{2})\.\s+'
        last_end = 0
        
        for match in re.finditer(sentence_pattern, paragraph):
            end_pos = match.end()
            sentence = paragraph[last_end:end_pos].strip()
            if sentence and len(sentence) > 10:  # 过滤过短的句子
                sentences.append((sentence, current_pos + last_end))
            last_end = end_pos
        
        # 处理段落最后一句
        if last_end < len(paragraph):
            sentence = paragraph[last_end:].strip()
            if sentence and len(sentence) > 10:
                sentences.append((sentence, current_pos + last_end))
        
        current_pos += len(paragraph) + 2
    
    return sentences


def filter_relevant_sentences(text: str) -> List[Tuple[str, int, str]]:
    """
    筛选包含关键短语的句子，返回 (句子, 位置, 匹配的关键词)
    改进：过滤噪音内容，限制句子长度
    """
    sentences = split_sentences(text)
    relevant = []
    
    for sentence, pos in sentences:
        sentence_lower = sentence.lower()
        
        # 过滤明显的噪音内容
        if is_noise_sentence(sentence):
            continue
        
        # 限制句子长度（避免超长句子）
        if len(sentence) > 800:  # 超过800字符的句子很可能是错误边界
            continue
        
        for phrase in KEY_PHRASES:
            if phrase.lower() in sentence_lower:
                relevant.append((sentence, pos, phrase))
                break
    
    return relevant


def is_noise_sentence(sentence: str) -> bool:
    """判断是否为噪音句子（导航、菜单、列表等）"""
    sentence_lower = sentence.lower()
    
    # 噪音模式
    noise_patterns = [
        r'^\s*[\+\-\*]\s+',  # 列表项开头
        r'^\s*\d+\.\s+',     # 数字列表
        r'(browse|current issue|early view|accepted articles)',  # 导航词
        r'(subscribe|alert|rss|facebook|twitter|x channel)',  # 社交媒体
        r'(submit an article|journal metrics)',  # 操作按钮
        r'^\s*##\s+',  # Markdown 标题残留
        r'png\)|jpg\)|gif\)',  # 图片残留
    ]
    
    for pattern in noise_patterns:
        if re.search(pattern, sentence_lower):
            return True
    
    # 如果句子包含过多列表分隔符，也认为是噪音
    if sentence.count(' + ') > 3 or sentence.count(' - ') > 3:
        return True
    
    return False


def clean_institution_name(name: str, institution_type: str = "host") -> str:
    """
    清洗机构名称
    - 去除 Markdown 标记
    - 去除年份
    - 去除版权符号
    - 去除小写 the，保留大写 The
    
    参数:
        name: 原始机构名称
        institution_type: 机构类型 (host/publisher/copyright)
                         copyright 类型会保留 "or related companies" 等法律声明
    """
    name = clean_markdown(name)
    
    # 去除版权相关前缀
    name = re.sub(r'^.*?(?:copyright|©)\s*(?:\d{4}[-–—]\d{4})?\s*', '', name, flags=re.IGNORECASE)
    
    # 去除 "published by" 等前缀
    name = re.sub(r'^.*?(?:published by|edited by|official journal of)\s+', '', name, flags=re.IGNORECASE)
    
    # 去除年份
    name = re.sub(r'\b\d{4}\b', '', name)
    name = re.sub(r'\d{4}[-–—]\d{4}', '', name)
    
    # 去除 "or related companies" 等后缀（但 copyright 类型保留）
    if institution_type != "copyright":
        name = re.sub(r'\s+(or|and)\s+related\s+\w+.*$', '', name, flags=re.IGNORECASE)
    
    # 去除多余的标点和空格
    # copyright 和 publisher 类型保留逗号（如 "Inc," 或 "Ltd,"）
    if institution_type in ("copyright", "publisher"):
        name = re.sub(r'\s+', ' ', name)  # 只规范化空格
    else:
        name = re.sub(r'[,;:\s]+', ' ', name)  # 替换标点为空格
    
    name = name.strip(' ,-.')
    
    # 去除开头的小写 the，保留大写 The
    name = re.sub(r'^the\s+', '', name)
    
    # 去除明显的噪音词
    noise_words = ['tools', 'submit an article', 'connect with', 'press room', 'network']
    name_lower = name.lower()
    for noise in noise_words:
        if noise in name_lower:
            return ""
    
    return name.strip()


def determine_institution_type(sentence: str, name: str) -> str:
    """根据句子和名称内容判断机构类型"""
    sentence_lower = sentence.lower()
    name_lower = name.lower()
    
    # 优先级：copyright > publisher > host
    for type_name, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in sentence_lower or keyword in name_lower:
                if type_name == "copyright":
                    return "copyright"
    
    for type_name, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in sentence_lower or keyword in name_lower:
                if type_name == "publisher":
                    return "publisher"
    
    for type_name, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in sentence_lower or keyword in name_lower:
                if type_name == "host":
                    return "host"
    
    # 默认返回 host
    return "host"


# ========== LangExtract 抽取 ==========

def extract_with_langextract(
    text: str,
    model_id: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None
) -> List[Dict[str, Any]]:
    """使用 LangExtract 进行智能抽取"""
    
    if not LANGEXTRACT_AVAILABLE:
        return []
    
    # 定义提取指令
    prompt_description = """
    Extract host institutions, publishers, and copyright holders from journal information text.
    Only extract entities that explicitly indicate an official relationship (hosting, publishing, copyright).
    Return the complete source sentence for each extraction.
    Use exact text from the document without paraphrasing.
    """.strip()
    
    # Few-shot 示例
    examples = [
        lx.data.ExampleData(
            text="Allergy, the official journal of the European Academy of Allergy and Clinical Immunology (EAACI), aims to advance research.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="host_institution",
                    extraction_text="European Academy of Allergy and Clinical Immunology (EAACI)",
                    attributes={"type": "host"}
                )
            ]
        ),
        lx.data.ExampleData(
            text="© EAACI and John Wiley and Sons A/S. Published by John Wiley and Sons, Ltd",
            extractions=[
                lx.data.Extraction(
                    extraction_class="host_institution",
                    extraction_text="EAACI and John Wiley and Sons A/S",
                    attributes={"type": "copyright"}
                ),
                lx.data.Extraction(
                    extraction_class="host_institution",
                    extraction_text="John Wiley and Sons, Ltd",
                    attributes={"type": "publisher"}
                )
            ]
        ),
        lx.data.ExampleData(
            text="Copyright © 1999-2025 John Wiley & Sons, Inc or related companies.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="host_institution",
                    extraction_text="John Wiley & Sons, Inc",
                    attributes={"type": "copyright"}
                )
            ]
        )
    ]
    
    try:
        # 配置模型参数
        kwargs = {}
        if api_key:
            kwargs['api_key'] = api_key
        if api_base:
            kwargs['model_url'] = api_base
        
        # 对于非标准模型名（如 qwen*），使用 ModelConfig 明确指定 provider
        if not model_id.startswith(('gpt-', 'gemini-')):
            # 创建 ModelConfig 明确使用 OpenAI provider
            from langextract.providers.openai import OpenAILanguageModel
            
            config = lx.factory.ModelConfig(
                model_id=model_id,
                provider="OpenAILanguageModel",
                provider_kwargs={
                    "api_key": api_key,
                    "base_url": api_base,
                }
            )
            
            model = lx.factory.create_model(
                config=config,
                examples=examples,
                # use_schema_constraints=False, 'use_schema_constraints' is ignored when 'model' is provided. The model should already be configured with schema constraints.
                fence_output=True
            )
            
            # 使用预配置的模型
            result = lx.extract(
                text_or_documents=text,
                prompt_description=prompt_description,
                examples=examples,
                model=model,
                temperature=0,
            )
        else:
            # 标准模型使用常规方式
            result = lx.extract(
                text_or_documents=text,
                prompt_description=prompt_description,
                examples=examples,
                model_id=model_id,
                fence_output=True,
                # use_schema_constraints=False, 'use_schema_constraints' is ignored when 'model' is provided. The model should already be configured with schema constraints.
                temperature=0,
                **kwargs
            )
        
        # 转换为标准格式
        institutions = []
        for extraction in result.extractions:
            # 获取完整句子
            if extraction.char_interval:
                start = extraction.char_interval.start_pos
                end = extraction.char_interval.end_pos
                
                # 找到包含此位置的完整句子
                sentences = split_sentences(text)
                source_sentence = ""
                matched_kw = ""
                for sent, sent_pos in sentences:
                    if sent_pos <= start < sent_pos + len(sent):
                        source_sentence = sent
                        # 查找匹配的关键词
                        sent_lower = sent.lower()
                        for phrase in KEY_PHRASES:
                            if phrase.lower() in sent_lower:
                                matched_kw = phrase
                                break
                        break
                
                if not source_sentence:
                    source_sentence = text[max(0, start-50):min(len(text), end+50)]
            else:
                source_sentence = extraction.extraction_text
                matched_kw = ""
            
            # 转换句子为纯文本
            source_sentence_plain = markdown_to_plain_text(source_sentence)
            
            # 提取类型
            inst_type = extraction.attributes.get("type", "host") if extraction.attributes else "host"
            
            # 清洗名称（根据类型调整清理策略）
            clean_name = clean_institution_name(extraction.extraction_text, institution_type=inst_type)
            
            if clean_name:
                institutions.append({
                    "name": clean_name,
                    "type": inst_type,
                    "source_sentence": source_sentence_plain,
                    "matched_keyword": matched_kw,
                    "char_position": {
                        "start": extraction.char_interval.start_pos,
                        "end": extraction.char_interval.end_pos
                    } if extraction.char_interval else None,
                    "extraction_method": "langextract"
                })
        
        return institutions
    
    except Exception as e:
        print(f"[ERROR] LangExtract failed: {e}", file=sys.stderr)
        return []


# ========== Regexp 规则回退 ==========

def extract_with_regexp(text: str) -> List[Dict[str, Any]]:
    """使用正则表达式规则进行回退抽取"""
    
    institutions = []
    text_clean = clean_markdown(text)
    sentences = filter_relevant_sentences(text_clean)
    
    for sentence, pos, matched_keyword in sentences:
        # 将句子转为纯文本
        sentence_plain = markdown_to_plain_text(sentence)
        
        # 模式 1: 版权行 - Copyright © YYYY-YYYY Company Name
        # 扩展模式以匹配完整的版权声明（包括 "or related companies"）
        copyright_pattern = r'(?:copyright|©)\s*(?:\d{4}[-–—]\d{4})?\s*([A-Z][^.!?;]{5,200}?)(?:\.|$)'
        for match in re.finditer(copyright_pattern, sentence, re.IGNORECASE):
            # 对于版权信息，使用 copyright 类型清理（保留 "or related companies"）
            name = clean_institution_name(match.group(1), institution_type="copyright")
            if name and len(name) > 3:
                institutions.append({
                    "name": name,
                    "type": "copyright",
                    "source_sentence": sentence_plain,
                    "matched_keyword": matched_keyword,
                    "char_position": {"start": pos, "end": pos + len(sentence)},
                    "extraction_method": "regexp"
                })
        
        # 模式 2: official journal of / published by
        official_pattern = r'(?:official (?:journal|publication) of|published by|on behalf of)\s+(?:the\s+)?([A-Z][^.!?;()]{5,100}?)(?:\.|,|\(|$)'
        for match in re.finditer(official_pattern, sentence, re.IGNORECASE):
            name_raw = match.group(1).strip()
            # 只取到第一个括号或"aims to"等结束词
            name_raw = re.split(r'\s+(?:aims|seeks|provides|offers|publishes)', name_raw, flags=re.IGNORECASE)[0]
            inst_type = determine_institution_type(sentence, name_raw)
            name = clean_institution_name(name_raw, institution_type=inst_type)
            if name and len(name) > 5:
                institutions.append({
                    "name": name,
                    "type": inst_type,
                    "source_sentence": sentence_plain,
                    "matched_keyword": matched_keyword,
                    "char_position": {"start": pos, "end": pos + len(sentence)},
                    "extraction_method": "regexp"
                })
        
        # 模式 3: 带常见后缀的机构名
        suffix_pattern = '|'.join(INSTITUTION_SUFFIXES)
        institution_pattern = rf'\b([A-Z][A-Za-z\s&\-,\.]+(?:{suffix_pattern}))\b'
        for match in re.finditer(institution_pattern, sentence):
            inst_type = determine_institution_type(sentence, match.group(1))
            name = clean_institution_name(match.group(1), institution_type=inst_type)
            if name and len(name) > 5:
                # 避免重复
                if not any(inst["name"] == name for inst in institutions):
                    institutions.append({
                        "name": name,
                        "type": inst_type,
                        "source_sentence": sentence_plain,
                        "matched_keyword": matched_keyword,
                        "char_position": {"start": pos, "end": pos + len(sentence)},
                        "extraction_method": "regexp"
                    })
    
    # 去重（基于名称相似度）
    unique_institutions = []
    seen_names = []
    
    for inst in institutions:
        # 检查是否与已有名称过于相似
        is_duplicate = False
        inst_name_lower = inst["name"].lower()
        
        for seen_name in seen_names:
            seen_name_lower = seen_name.lower()
            # 如果一个名称包含另一个名称，认为是重复
            if inst_name_lower in seen_name_lower or seen_name_lower in inst_name_lower:
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen_names.append(inst["name"])
            unique_institutions.append(inst)
    
    return unique_institutions


# ========== 主函数 ==========

def main():
    parser = argparse.ArgumentParser(
        description="期刊主办单位自动抽取工具"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入 Markdown 文件路径"
    )
    parser.add_argument(
        "--model-id", "-m",
        default="gpt-4o-mini",
        help="LangExtract 模型 ID (默认: gpt-4o-mini)"
    )
    parser.add_argument(
        "--output", "-o",
        help="输出 JSON 文件路径（可选，默认输出到 stdout）"
    )
    parser.add_argument(
        "--api-base",
        help="OpenAI 兼容接口地址"
    )
    parser.add_argument(
        "--api-key",
        help="模型 API Key"
    )
    
    args = parser.parse_args()
    
    # 读取输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        result = {"error": f"Input file not found: {args.input}"}
        output_json(result, args.output)
        sys.exit(1)
    
    try:
        text = input_path.read_text(encoding='utf-8')
    except Exception as e:
        result = {"error": f"Failed to read input file: {e}"}
        output_json(result, args.output)
        sys.exit(1)
    
    # 获取 API 配置（优先使用命令行参数，否则使用环境变量）
    api_key = args.api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('LANGEXTRACT_API_KEY')
    api_base = args.api_base or os.environ.get('OPENAI_API_BASE')
    
    # 尝试使用 LangExtract
    institutions = []
    if LANGEXTRACT_AVAILABLE:
        print(f"[INFO] Using LangExtract with model: {args.model_id}", file=sys.stderr)
        institutions = extract_with_langextract(
            text,
            model_id=args.model_id,
            api_key=api_key,
            api_base=api_base
        )
    
    # 回退策略
    if not institutions:
        print("[INFO] LangExtract returned no results, falling back to regexp", file=sys.stderr)
        institutions = extract_with_regexp(text)
    
    # 构建输出
    if institutions:
        result = {"host_institutions": institutions}
        print(f"[OK] Extracted {len(institutions)} institutions using {institutions[0]['extraction_method']}", file=sys.stderr)
    else:
        result = {"host_institutions": []}
        print("[WARNING] No institutions extracted", file=sys.stderr)
    
    # 输出结果
    output_json(result, args.output)


def output_json(data: Dict[str, Any], output_path: Optional[str] = None):
    """输出 JSON 结果"""
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json_str, encoding='utf-8')
        print(f"[OK] Saved to {output_file.absolute()}", file=sys.stderr)
    else:
        # 处理 Windows 终端编码问题
        try:
            print(json_str)
        except UnicodeEncodeError:
            # 回退到 ASCII 编码
            json_str_ascii = json.dumps(data, ensure_ascii=True, indent=2)
            print(json_str_ascii)


if __name__ == "__main__":
    main()

