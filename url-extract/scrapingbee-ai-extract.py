import requests
import json

def send_request():
    ai_extract_rules = {
        "blog_posts": {
            "description": "学校的师资队伍列表页面，包含教师信息列表，页面可以进一步点击进入教师个人主页",
            "type": "list",
            "output": {
                "name": "教师/研究者的姓名",
                "title": "教授/院士 等",
                "phone": "这位教师的联系电话",
                "email": "这位教师的邮箱",
                "info_url": "这位教师的个人主页链接，在列表页可能通过姓名、联系方式或头像点击跳转过去"
            }
        }
    }

    response = requests.get(
        url="https://app.scrapingbee.com/api/v1",
        params={
            "api_key": "406C3RBCAXVOMZXVJMF5LO6WKCA9FJ0TGS7SE3O32RZLEEEEH0H11PT1ASPFTAPVJEKE0LZQM39FPPOQ",
            "url": "https://www.arch.tsinghua.edu.cn/column/rw",
            "json_response": "true",
            "ai_extract_rules": json.dumps(ai_extract_rules, ensure_ascii=False),
        },
    )

    print("Response HTTP Status Code:", response.status_code)
    # print("Response HTTP Response Body:", response.content)
    if response.status_code == 200:
        # 1. 获取外层 JSON 响应
        data = response.json()
        
        # 2. 提取 'ai_response' 字段 (注意：这是一个字符串形式的 JSON)
        ai_response_str = data.get("ai_response", "{}")
    
    try:
        # 3. 解析内层 JSON 字符串
        ai_response_data = json.loads(ai_response_str)
        
        # 4. 提取 blog_posts 列表
        blog_posts = ai_response_data.get("blog_posts", [])
        
        # 打印结果或进行后续处理
        print(f"成功提取 {len(blog_posts)} 条记录")
        for post in blog_posts:
            print(post)
            # 例如访问字段: post.get('name'), post.get('email')
            
    except json.JSONDecodeError as e:
        print(f"解析 ai_response 出错: {e}")

send_request()
