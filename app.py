# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response
import requests
import os
import json
import traceback

# 初始化Flask应用
app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- API 密钥配置 ---
DEEPSEEK_API_KEY = "sk-44e1314da2d94b35b978f0fcd01ed26f"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- PROMPTS (内容保持不变) ---
def get_conceptualization_prompt_text():
    return """你是一位资深的心理咨询师...""" # 内容省略

def get_assessment_prompt_text():
    return """你是一位资深的心理咨询师...""" # 内容省略
    
def get_supervision_prompt_text():
    return """你是资深心理咨询督导师...""" # 内容省略

# --- 核心API调用函数 ---
def call_deepseek_api(system_prompt, user_prompt, model='deepseek-chat', stream=False):
    print(f"--- [DEBUG] call_deepseek_api: model={model}, stream={stream} ---")
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], 'stream': stream}
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, stream=stream, timeout=180)
        print(f"--- [DEBUG] DeepSeek API response status: {response.status_code} ---")
        response.raise_for_status()
        
        if stream:
            def generate():
                for chunk in response.iter_content(chunk_size=None):
                    yield chunk
            return Response(generate(), content_type=response.headers.get('Content-Type'))
        else:
            data = response.json()
            print(f"--- [DEBUG] DeepSeek API JSON response (non-stream): {json.dumps(data, ensure_ascii=False, indent=2)} ---")
            content = data.get('choices', [{}])[0].get('message', {}).get('content')
            if content is None:
                raise ValueError("AI response did not contain expected content.")
            return content
            
    except Exception as e:
        print(f"--- [ERROR] Exception in call_deepseek_api: {e} ---")
        traceback.print_exc() # 打印完整的错误堆栈
        raise

# --- 路由定义 ---
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/upload-and-analyze', methods=['POST'])
def upload_and_analyze():
    print("\n--- [DEBUG] Entering /api/upload-and-analyze ---")
    if 'transcript' not in request.files: return jsonify({"error": "请求中未找到文件"}), 400
    file = request.files['transcript']
    if file.filename == '': return jsonify({"error": "未选择文件"}), 400

    try:
        transcript_content = file.read().decode('utf-8')
        client_info = json.loads(request.form.get('client_info'))
        user_prompt = f"来访者基本信息:\n{json.dumps(client_info, indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{transcript_content}\n---"
        
        print("--- [DEBUG] Generating Conceptualization... ---")
        conceptualization_content = call_deepseek_api(get_conceptualization_prompt_text(), user_prompt, stream=False)
        
        print("--- [DEBUG] Generating Assessment... ---")
        assessment_content = call_deepseek_api(get_assessment_prompt_text(), user_prompt, stream=False)

        response_data = {
            "success": True,
            "conceptualization": {"status": "Complete", "content": conceptualization_content},
            "assessment": {"status": "Complete", "content": assessment_content},
            "uploadedFileName": file.filename
        }
        print("--- [DEBUG] Successfully generated all reports. Sending response to front-end. ---")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"--- [ERROR] Exception in /api/upload-and-analyze: {e} ---")
        traceback.print_exc()
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

@app.route('/api/generate-supervision', methods=['POST'])
def generate_supervision():
    print("\n--- [DEBUG] Entering /api/generate-supervision ---")
    try:
        data = request.json
        prompt_for_supervision = f"来访者基本信息:\n{json.dumps(data.get('client_info'), indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n{data.get('transcript_content')}\n\nAI生成的个案概念化:\n{data.get('conceptualization_content')}\n\nAI生成的来访者评估:\n{data.get('assessment_content')}"
        supervision_content = call_deepseek_api(get_supervision_prompt_text(), prompt_for_supervision, stream=False)
        return jsonify({"success": True, "supervision": {"status": "Complete", "content": supervision_content}})
    except Exception as e:
        print(f"--- [ERROR] Exception in /api/generate-supervision: {e} ---")
        traceback.print_exc()
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

@app.route('/api/call-ai', methods=['POST'])
def call_ai_proxy():
    print("\n--- [DEBUG] Entering /api/call-ai (streaming) ---")
    data = request.json
    system_prompt = data.get('systemPrompt')
    user_prompt = data.get('userPrompt')
    model = data.get('model', 'deepseek-chat')
    if not user_prompt or not system_prompt: return jsonify({"error": "缺少必要的参数"}), 400
    return call_deepseek_api(system_prompt, user_prompt, model=model, stream=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

