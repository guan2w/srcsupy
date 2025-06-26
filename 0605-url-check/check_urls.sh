#!/bin/bash

# 输入文件
INPUT_FILE="url-list.txt"
# 输出文件
OUTPUT_FILE="url-list-check.csv"
# 计数器
COUNT=0

# 检查输入文件是否存在
if [ ! -f "$INPUT_FILE" ]; then
    echo "错误：输入文件 '$INPUT_FILE' 未找到。"
    exit 1
fi

# 写入 CSV 头部
echo "序号,URL,响应状态码,响应体大小(KB)" > "$OUTPUT_FILE"

# 逐行读取 URL
while IFS= read -r url || [[ -n "$url" ]]; do
    # 过滤空行
    if [ -z "$url" ]; then
        continue
    fi

    # --- 新增的修复代码 ---
    # 移除 URL 变量中可能存在的回车符 (CR)，以兼容 Windows 格式的文本文件
    url="${url//$'\r'/}"
    # --------------------

    ((COUNT++))

    # 使用 curl 获取 HTTP 状态码和下载大小（字节）
    # -o /dev/null：不输出响应体
    # -s：静默模式
    # -L：跟随重定向
    # -w：指定输出格式
    # %{http_code}：HTTP 状态码
    # %{size_download}：下载大小（字节）
    response=$(curl -o /dev/null -s -L -w "%{http_code},%{size_download}" "$url")

    # 分割状态码和大小
    status_code=$(echo "$response" | cut -d, -f1)
    size_bytes=$(echo "$response" | cut -d, -f2)

    # 将字节转换为 KB（使用 awk 进行浮点数计算）
    size_kb=$(awk "BEGIN {printf \"%.2f\", $size_bytes / 1024}")

    # 打印到控制台（可选）
    echo "正在检查: $url -> 状态码: $status_code, 大小: ${size_kb}KB"

    # 写入到 CSV 文件
    echo "$COUNT,\"$url\",$status_code,$size_kb" >> "$OUTPUT_FILE"

done < "$INPUT_FILE"

echo "检查完成！结果已保存到 '$OUTPUT_FILE'。"
