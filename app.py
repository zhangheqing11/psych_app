# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response
import requests
import os
import json

# 初始化Flask应用
app = Flask(__name__, static_folder='static')

# --- 新增配置：增加允许上传的文件大小限制 ---
# 此处设置为16MB，您可以根据需要调整
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- API 密钥配置 ---
DEEPSEEK_API_KEY = "sk-44e1314da2d94b35b978f0fcd01ed26f"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- 路由定义 ---

@app.route('/')
def serve_index():
    response = make_response(send_from_directory(app.static_folder, 'index.html'))
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
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

        user_prompt_content = f"""
来访者基本信息:
姓名: {client_info.get('name')}
年龄: {client_info.get('age')}
性别: {client_info.get('gender')}
在读年级: {client_info.get('grade')}
性取向: {client_info.get('sexualOrientation')}
既往病史: {client_info.get('historyOfIllness')}
心理状态评分: {client_info.get('mentalStateScore')}/10
残障情况: {client_info.get('disabilityStatus')}
宗教信仰: {client_info.get('religiousBelief')}
种族认同: {client_info.get('ethnicIdentity')}
个人经济: {client_info.get('personalFinance')}
家庭经济: {client_info.get('familyFinance')}

咨询逐字稿内容:
---
{transcript_content}
---
"""
        
        conceptualization_prompt = get_conceptualization_prompt_text()
        conceptualization_content = call_api_sync(conceptualization_prompt, user_prompt_content)
        
        assessment_prompt = get_assessment_prompt_text()
        assessment_content = call_api_sync(assessment_prompt, user_prompt_content)

        return jsonify({
            "success": True,
            "conceptualization": {"status": "Complete", "content": conceptualization_content},
            "assessment": {"status": "Complete", "content": assessment_content},
            "uploadedFileName": file.filename
        })

    except Exception as e:
        print(f"文件处理或AI调用时出错: {e}")
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

def call_api_sync(system_prompt, user_prompt, model='deepseek-chat'):
    """一个简化的、非流式的API调用函数"""
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180) # 增加超时时间
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        return f"API调用失败: {e}"

# (此处省略了get_..._prompt_text()函数的定义，它们保持不变)
def get_conceptualization_prompt_text():
    return """你是一位资深的心理咨询师..."""
def get_assessment_prompt_text():
    return """你是一位资深的心理咨询师..."""
def get_supervision_prompt_text():
    return """你是资深心理咨询督导师..."""

# 路由2: 生成最终的督导报告
@app.route('/api/generate-supervision', methods=['POST'])
def generate_supervision():
    # ... (此部分代码保持不变)
    pass

# 路由3: 用于CBT工具的流式调用
@app.route('/api/call-ai', methods=['POST'])
def call_ai_proxy():
    # ... (此部分代码保持不变)
    pass

# --- 启动服务器 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
