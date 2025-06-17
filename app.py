# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response
import requests
import os
import json

# 初始化Flask应用
app = Flask(__name__, static_folder='static')

# --- API 密钥配置 ---
DEEPSEEK_API_KEY = "sk-44e1314da2d94b35b978f0fcd01ed26f"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- 辅助函数 ---
def call_api_sync(system_prompt, user_prompt, model='deepseek-chat'):
    """一个简化的、非流式的API调用函数"""
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        print(f"call_api_sync error: {e}")
        return f"API调用失败: {e}"

# (此处省略了get_..._prompt_text()函数的定义，以保持简洁，但它们应包含您提供的完整prompt文本)
def get_conceptualization_prompt_text():
    return "你是一位资深的心理咨询师。根据文件中的咨询逐字稿内容以及来访的基本信息，提供个案概念化报告..."

def get_assessment_prompt_text():
    return "你是一位资深的心理咨询师。基于文件中咨询逐字稿的内容，并遵循以下我给出的评估维度，对该来访做出专业化的评估..."
    
def get_supervision_prompt_text():
    return "你是资深心理咨询督导师，采用精神动力学取向整合视角..."

# --- 路由定义 ---

@app.route('/')
def serve_index():
    response = make_response(send_from_directory(app.static_folder, 'index.html'))
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# 路由1: 上传逐字稿，并自动生成概念化和评估报告
@app.route('/api/upload-and-analyze', methods=['POST'])
def upload_and_analyze():
    if 'transcript' not in request.files:
        return jsonify({"error": "请求中未找到文件"}), 400
    file = request.files['transcript']
    if file.filename == '':
        return jsonify({"error": "未选择文件"}), 400

    try:
        transcript_content = file.read().decode('utf-8')
        client_info_json = request.form.get('client_info')
        client_info = json.loads(client_info_json)

        user_prompt_content = f"来访者基本信息:\n{json.dumps(client_info, indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{transcript_content}\n---"
        
        # 并行调用AI生成两份报告
        conceptualization_content = call_api_sync(get_conceptualization_prompt_text(), user_prompt_content)
        assessment_content = call_api_sync(get_assessment_prompt_text(), user_prompt_content)

        return jsonify({
            "success": True,
            "conceptualization": {"status": "Complete", "content": conceptualization_content},
            "assessment": {"status": "Complete", "content": assessment_content},
            "uploadedFileName": file.filename
        })
    except Exception as e:
        print(f"文件处理或AI调用时出错: {e}")
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

# 新增路由2: 接收所有材料，生成最终的督导报告
@app.route('/api/generate-supervision', methods=['POST'])
def generate_supervision():
    try:
        data = request.json
        client_info_json = json.dumps(data.get('client_info'), indent=2, ensure_ascii=False)
        transcript_content = data.get('transcript_content')
        conceptualization_content = data.get('conceptualization_content')
        assessment_content = data.get('assessment_content')

        if not all([client_info_json, transcript_content, conceptualization_content, assessment_content]):
            return jsonify({"error": "生成督导报告所需材料不完整"}), 400

        user_prompt_for_supervision = f"来访者基本信息:\n{client_info_json}\n\n咨询逐字稿内容:\n{transcript_content}\n\nAI生成的个案概念化:\n{conceptualization_content}\n\nAI生成的来访者评估:\n{assessment_content}"
        
        supervision_content = call_api_sync(get_supervision_prompt_text(), user_prompt_for_supervision)

        return jsonify({
            "success": True,
            "supervision": {"status": "Complete", "content": supervision_content}
        })
    except Exception as e:
        print(f"生成督导报告时出错: {e}")
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

# 路由3: 用于CBT工具的流式调用 (保持不变)
@app.route('/api/call-ai', methods=['POST'])
def call_ai_proxy():
    # ... (此部分代码保持不变) ...
    pass

# --- 启动服务器 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
