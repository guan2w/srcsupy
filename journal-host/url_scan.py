#!/usr/bin/env python3
"""
URL 深度扫描工具 - url_scan.py

调用可联网的 LLM 深度扫描期刊官网，提取机构关联信息
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

# 导入 llm_call 模块
sys.path.insert(0, os.path.dirname(__file__))
try:
    from llm_call import call_llm_url_scan, calculate_cost
except ImportError as e:
    print(f"[ERROR] Failed to import llm_call.py: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="URL 深度扫描工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python url_scan.py \\
    --journal-name "Nature" \\
    --url1 "https://www.nature.com/nature/about" \\
    --url2 "https://www.springernature.com/gp/about-us" \\
    --model-id gemini-2.5-pro-search \\
    --output result.json
        """
    )
    
    parser.add_argument(
        '--journal-name',
        required=True,
        help='期刊名称'
    )
    parser.add_argument(
        '--url1',
        required=True,
        help='第一个 URL（期刊官方简介链接）'
    )
    parser.add_argument(
        '--url2',
        required=True,
        help='第二个 URL（主办单位官方链接）'
    )
    parser.add_argument(
        '--model-id',
        default='gemini-2.5-pro-search',
        help='模型 ID（默认: gemini-2.5-pro-search）'
    )
    parser.add_argument(
        '--api-base',
        default=None,
        help='API Base URL'
    )
    parser.add_argument(
        '--api-key',
        default=None,
        help='API Key'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=180,
        help='请求超时时间（秒，默认 180）'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='输出 JSON 文件路径（可选，默认输出到 stdout）'
    )
    
    args = parser.parse_args()
    
    # 获取 API 配置
    api_key = args.api_key or os.environ.get('OPENAI_API_KEY')
    api_base = args.api_base or os.environ.get('OPENAI_API_BASE', 'https://api.openai.com/v1')
    
    if not api_key:
        print("[ERROR] API key not configured. Set --api-key or OPENAI_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)
    
    # 打印参数
    print("=" * 60, file=sys.stderr)
    print("[CONFIG] URL 深度扫描工具", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"期刊名称:      {args.journal_name}", file=sys.stderr)
    print(f"URL1:          {args.url1}", file=sys.stderr)
    print(f"URL2:          {args.url2}", file=sys.stderr)
    print(f"模型 ID:       {args.model_id}", file=sys.stderr)
    print(f"API Base:      {api_base}", file=sys.stderr)
    print(f"超时时间:      {args.timeout} 秒", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print()
    
    # 调用 LLM
    print(f"[SCAN] 开始扫描...", file=sys.stderr)
    
    success, results, usage, usage_source, elapsed_time, error_type, error_msg = call_llm_url_scan(
        journal_name=args.journal_name,
        url1=args.url1,
        url2=args.url2,
        model_id=args.model_id,
        api_key=api_key,
        api_base=api_base,
        timeout=args.timeout
    )
    
    if success and results:
        # 成功
        print(f"\n[SUCCESS] 提取 {len(results)} 条结果", file=sys.stderr)
        
        # 构建输出
        output_data = {
            "journal_name": args.journal_name,
            "url1": args.url1,
            "url2": args.url2,
            "status": "success",
            "results": results,
            "elapsed_time": elapsed_time
        }
        
        # 添加 token 统计
        if usage:
            output_data["usage"] = {
                "prompt_tokens": usage.get('prompt_tokens', 0),
                "completion_tokens": usage.get('completion_tokens', 0),
                "total_tokens": usage.get('total_tokens', 0),
                "source": usage_source
            }
            
            # 估算成本（使用默认价格）
            cost = calculate_cost(usage, 1.0, 8.0)
            if cost:
                output_data["cost_usd"] = cost
            
            print(f"[TOKEN] 输入: {usage['prompt_tokens']}, 输出: {usage['completion_tokens']}, 总计: {usage['total_tokens']} (来自: {usage_source})", file=sys.stderr)
            if cost:
                print(f"[COST] 估算成本: ${cost:.4f}", file=sys.stderr)
        
        print(f"[TIME] 耗时: {elapsed_time:.2f} 秒", file=sys.stderr)
        
        # 输出结果
        json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
        
        if args.output:
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json_str, encoding='utf-8')
            print(f"\n[OK] 结果已保存到: {output_file}", file=sys.stderr)
        else:
            print(json_str)
    else:
        # 失败
        print(f"\n[FAILED] {error_type}: {error_msg}", file=sys.stderr)
        
        # 构建错误输出
        error_data = {
            "journal_name": args.journal_name,
            "url1": args.url1,
            "url2": args.url2,
            "status": "failed",
            "error_type": error_type,
            "error_message": error_msg
        }
        
        json_str = json.dumps(error_data, ensure_ascii=False, indent=2)
        
        if args.output:
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json_str, encoding='utf-8')
        else:
            print(json_str)
        
        sys.exit(1)


if __name__ == "__main__":
    main()

