import sys
import os
sys.path.append('.')

# 直接从app.py导入SYSTEM_PROMPT_INTERVIEW
try:
    from app import SYSTEM_PROMPT_INTERVIEW
    print("✅ 成功导入SYSTEM_PROMPT_INTERVIEW")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    exit()

def test_prompt_building():
    try:
        print("\n=== 测试系统提示构建 ===")
        
        # 尝试构建系统提示
        system_prompt = f"""
{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['role_definition']['persona']}
{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['role_definition']['objective']}

对话规则：
- {SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['conversation_flow']['progression_logic']}
- 语调：{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['constraints_and_guidelines']['tone']}
- {SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['constraints_and_guidelines']['language']}

禁止事项：
""" + "\n".join([f"- {p}" for p in SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['constraints_and_guidelines']['prohibitions']])
        
        print("✅ 系统提示构建成功")
        print(f"提示长度: {len(system_prompt)} 字符")
        print(f"提示预览: {system_prompt[:200]}...")
        
        # 构建完整对话上下文
        user_message = "你好，我想进行心理咨询。"
        history = []
        
        conversation_context = system_prompt + "\n\n"
        
        # 添加历史对话
        for item in history:
            role = "用户" if item['sender'] == 'user' else "助手"
            conversation_context += f"{role}: {item['text']}\n"
        
        # 添加当前用户消息
        conversation_context += f"用户: {user_message}\n助手: "
        
        print(f"✅ 对话上下文构建成功，长度: {len(conversation_context)} 字符")
        
        return conversation_context
        
    except Exception as e:
        print(f"❌ 构建系统提示时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_gemini_with_prompt():
    try:
        from google import genai
        
        conversation_context = test_prompt_building()
        if not conversation_context:
            return
        
        print("\n=== 测试Gemini API调用 ===")
        
        api_key = os.environ.get('GEMINI_API_KEY', "AIzaSyBGmOLVLWN-CcN6H59ZiUWW2JZ6NBe9txU")
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=conversation_context
        )
        
        print("✅ Gemini API调用成功!")
        print(f"回复: {response.text[:200]}...")
        
    except Exception as e:
        print(f"❌ Gemini API调用失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gemini_with_prompt() 