import os
from google import genai
from google.genai import types
import json

# 设置API密钥
os.environ['GEMINI_API_KEY'] = "AIzaSyBGmOLVLWN-CcN6H59ZiUWW2JZ6NBe9txU"

def test_simple_gemini():
    try:
        print("测试基础Gemini API连接...")
        
        # 确保API密钥已正确配置
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            print("❌ API密钥未设置")
            return
        
        print(f"✅ API密钥已设置: {api_key[:10]}...")
        
        # 创建客户端
        client = genai.Client(api_key=api_key)
        print("✅ 客户端创建成功")
        
        # 简单测试
        simple_prompt = "你是一位心理咨询助手。用户说：你好，我想进行心理咨询。请回复。"
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=simple_prompt
        )
        
        print("✅ API调用成功!")
        print(f"回复: {response.text[:100]}...")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_gemini() 