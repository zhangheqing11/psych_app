# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, make_response
import requests
import os
import json
import traceback
import logging

# 初始化Flask应用
app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB file size limit

# 配置日志记录
logging.basicConfig(level=logging.INFO)

# --- API 密钥配置 ---
DEEPSEEK_API_KEY = "sk-44e1314da2d94b35b978f0fcd01ed26f"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- PROMPTS (内容保持不变) ---
def get_conceptualization_prompt_text():
    return """你是一位资深的心理咨询师。根据文件中的咨询逐字稿内容以及来访的基本信息，提供个案概念化报告..."""

def get_assessment_prompt_text():
    return """你是一位资深的心理咨询师。基于文件中咨询逐字稿的内容，并遵循以下我给出的评估维度，对该来访做出专业化的评估..."""
    
def get_supervision_prompt_text():
    return """你是资深心理咨询督导师，采用精神动力学取向整合视角..."""

# --- 核心API调用函数 (已简化为只支持非流式) ---
def call_api_sync(system_prompt, user_prompt, model='deepseek-chat'):
    """
    同步调用API，用于一次性获取完整结果。
    """
    app.logger.info(f"[SYNC_CALL_START] model={model}")
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], 'stream': False}
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        app.logger.info("[SYNC_CALL_SUCCESS] Received non-stream response.")
        content = data.get('choices', [{}])[0].get('message', {}).get('content')
        if content is None:
            raise ValueError(f"AI response did not contain expected content: {data}")
        return content
    except Exception as e:
        app.logger.error(f"--- [ERROR] Exception in call_api_sync: {e} ---")
        traceback.print_exc()
        raise

# --- 路由定义 ---
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/upload-and-analyze', methods=['POST'])
def upload_and_analyze():
    app.logger.info("[ROUTE_HIT] /api/upload-and-analyze")
    if 'transcript' not in request.files: return jsonify({"error": "请求中未找到文件"}), 400
    file = request.files['transcript']
    if file.filename == '': return jsonify({"error": "未选择文件"}), 400

    try:
        transcript_content = file.read().decode('utf-8')
        client_info = json.loads(request.form.get('client_info'))
        user_prompt = f"来访者基本信息:\n{json.dumps(client_info, indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{transcript_content}\n---"
        
        conceptualization_content = call_api_sync(get_conceptualization_prompt_text(), user_prompt)
        assessment_content = call_api_sync(get_assessment_prompt_text(), user_prompt)

        return jsonify({
            "success": True,
            "conceptualization": {"status": "Complete", "content": conceptualization_content},
            "assessment": {"status": "Complete", "content": assessment_content},
            "uploadedFileName": file.filename
        })
    except Exception as e:
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

@app.route('/api/generate-supervision', methods=['POST'])
def generate_supervision():
    app.logger.info("[ROUTE_HIT] /api/generate-supervision")
    try:
        data = request.json
        prompt_for_supervision = f"来访者基本信息:\n{json.dumps(data.get('client_info'), indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n{data.get('transcript_content')}\n\nAI生成的个案概念化:\n{data.get('conceptualization_content')}\n\nAI生成的来访者评估:\n{data.get('assessment_content')}"
        supervision_content = call_api_sync(get_supervision_prompt_text(), prompt_for_supervision)
        return jsonify({"success": True, "supervision": {"status": "Complete", "content": supervision_content}})
    except Exception as e:
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

# 注意：/api/call-ai 路由已被移除

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
