import threading
import queue
import csv
import requests
import time
import os
import sys
from typing import List, Tuple

# --- 配置 ---
INPUT_FILE = 'url-list.txt'
OUTPUT_FILE = 'url-list-check.csv'
CONCURRENCY = 20
REQUEST_TIMEOUT = 10

# --- 新增：定义请求头 ---
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
REQUEST_HEADERS = {
    'User-Agent': USER_AGENT
}
# -------------------------

# --- 共享资源 ---
task_queue = queue.Queue()
results = []
completed_count = 0
results_lock = threading.Lock()
completed_count_lock = threading.Lock()

def check_url():
    """
    工作线程函数，从队列中获取URL并处理，捕获更详细的信息。
    """
    global completed_count
    
    while not task_queue.empty():
        try:
            index, url = task_queue.get_nowait()
        except queue.Empty:
            break

        final_url = url
        success_status = '失败'
        status_code = 'N/A'
        size_kb = 0.0
        error_reason = ''

        try:
            # --- 修改：在请求中加入 headers ---
            response = requests.get(
                url, 
                headers=REQUEST_HEADERS, # 使用我们定义的请求头
                allow_redirects=True, 
                timeout=REQUEST_TIMEOUT
            )
            # ---------------------------------
            
            final_url = response.url
            status_code = response.status_code
            size_kb = round(len(response.content) / 1024, 2)

            if response.ok:
                success_status = '成功'
            else:
                error_reason = response.reason

        except requests.exceptions.RequestException as e:
            error_reason = f"{type(e).__name__}: {str(e).splitlines()[0]}"

        finally:
            with results_lock:
                results.append((index, url, final_url, success_status, status_code, size_kb, error_reason))
            
            with completed_count_lock:
                completed_count += 1
            
            if success_status == '失败':
                print(f"\n[FAIL] {url[:70]:<70} -> {error_reason}")

        task_queue.task_done()

def print_progress(total: int):
    """
    在主线程中运行，用于显示和更新进度条。
    """
    progress_str = ''
    while completed_count < total:
        with completed_count_lock:
            count = completed_count
        
        percentage = (count / total) * 100
        bar_length = 40
        filled_length = int(bar_length * count // total)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        
        progress_str = f'进度: |{bar}| {count}/{total} ({percentage:.2f}%)'
        
        sys.stdout.write('\r' + progress_str)
        sys.stdout.flush()
        
        time.sleep(0.1)

    sys.stdout.write('\r' + ' ' * (len(progress_str) + 5) + '\r')
    sys.stdout.flush()

def main():
    """
    主函数：读取URL，创建线程，处理并写入增强版结果。
    """
    if not os.path.exists(INPUT_FILE):
        print(f"错误：输入文件 '{INPUT_FILE}' 未找到。")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        urls_to_process = [line.strip() for line in f if line.strip()]

    total_urls = len(urls_to_process)
    if total_urls == 0:
        print("输入文件为空，无需处理。")
        return
        
    for index, url in enumerate(urls_to_process):
        task_queue.put((index, url))
    
    print(f"开始检查 {total_urls} 个URL，并发数: {CONCURRENCY}...")
    print(f"使用 User-Agent: {USER_AGENT}") # 提示当前使用的UA
    start_time = time.time()

    worker_threads = []
    for _ in range(CONCURRENCY):
        thread = threading.Thread(target=check_url)
        thread.start()
        worker_threads.append(thread)

    progress_thread = threading.Thread(target=print_progress, args=(total_urls,))
    progress_thread.start()

    for thread in worker_threads:
        thread.join()
    progress_thread.join()

    results.sort()

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', 'URL', '最终URL', '成功状态', '响应状态码', '响应体大小(KB)', '错误原因'])
        
        success_count = 0
        for result_tuple in results:
            writer.writerow([result_tuple[0] + 1] + list(result_tuple[1:]))
            if result_tuple[3] == '成功':
                success_count += 1
    
    end_time = time.time()
    
    total_time = end_time - start_time
    print(f"检查完成！成功 {success_count} / {total_urls}。")
    print(f"总共耗时: {total_time:.2f} 秒。结果已保存到 '{OUTPUT_FILE}'。")

if __name__ == '__main__':
    main()
