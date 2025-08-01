import requests
import json

def test_interview_api():
    url = "http://localhost:5000/api/interview/chat"
    
    data = {
        "message": "你好，我想进行心理咨询。",
        "history": []
    }
    
    try:
        print("正在测试初始访谈API...")
        response = requests.post(url, json=data, timeout=30)
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 初始访谈API调用成功!")
            print(f"AI回复: {result.get('response', 'No response field')}")
        else:
            print("❌ 初始访谈API调用失败")
            try:
                error_data = response.json()
                print(f"错误信息: {error_data}")
            except:
                print(f"响应内容: {response.text}")
                
    except requests.exceptions.Timeout:
        print("❌ 请求超时")
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误 - 请确保服务器正在运行")
    except Exception as e:
        print(f"❌ 其他错误: {e}")

if __name__ == "__main__":
    test_interview_api() 