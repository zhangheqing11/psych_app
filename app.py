# 安装必要的库: pip install Flask Flask-Cors requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import json
import traceback
import logging

# 初始化Flask应用
# 'static_folder=None' 避免与我们将要手动处理的静态文件路由冲突
app = Flask(__name__, static_folder=None)
CORS(app)  # 允许跨域请求

# 配置日志记录以更好地进行调试
logging.basicConfig(level=logging.INFO)

# --- 数据文件路径 ---
# 将所有应用数据存储在单个JSON文件中
DATA_FILE = 'database.json'

# --- 辅助函数：读写数据文件 ---
def read_data():
    """从JSON文件读取数据。如果文件不存在或为空，则返回一个默认的数据结构。"""
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "app_data": {}}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return {"users": {}, "app_data": {}}
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"users": {}, "app_data": {}}

def write_data(data):
    """将数据写入JSON文件。"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 用户认证API ---
@app.route('/api/register', methods=['POST'])
def register():
    """处理用户注册。检查用户名是否存在，然后存储新用户。"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"message": "用户名和密码是必填项"}), 400
    
    if len(password) < 6:
        return jsonify({"message": "密码必须至少为6个字符"}), 400

    all_data = read_data()
    if username in all_data['users']:
        return jsonify({"message": "用户名已存在"}), 409

    all_data['users'][username] = {"password": password}
    write_data(all_data)
    
    return jsonify({"message": "注册成功！", "username": username}), 201

@app.route('/api/login', methods=['POST'])
def login():
    """处理用户登录。验证用户名和密码。"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    all_data = read_data()
    user = all_data.get('users', {}).get(username)

    if not user:
        return jsonify({"message": "用户不存在"}), 404
    
    if user['password'] == password:
        return jsonify({"message": f"欢迎回来, {username}!", "username": username}), 200
    else:
        return jsonify({"message": "密码错误"}), 401

# --- 应用数据API ---
@app.route('/api/data/<username>', methods=['GET'])
def get_user_data(username):
    """获取特定用户的所有应用数据。"""
    all_data = read_data()
    user_data = all_data.get('app_data', {}).get(username, {
        "clients": [],
        "counselors": [],
        "appointments": []
    })
    return jsonify(user_data)

@app.route('/api/data/<username>', methods=['POST'])
def save_user_data(username):
    """保存特定用户的所有应用数据。"""
    new_data = request.get_json()
    all_data = read_data()

    if 'app_data' not in all_data:
        all_data['app_data'] = {}

    all_data['app_data'][username] = new_data
    
    write_data(all_data)
    return jsonify({"message": "数据保存成功"}), 200

# --- AI 分析 API ---
# 注意：您需要将 "YOUR_GEMINI_API_KEY" 替换为您的实际Google Gemini API密钥。
# 将密钥存储在环境变量中是更安全的做法。
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

def call_gemini_api(system_prompt, user_prompt):
    """一个通用的辅助函数，用于调用Gemini API。"""
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]
    }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        
        # 从API响应中提取文本内容
        content = data['candidates'][0]['content']['parts'][0]['text']
        return content
    except Exception as e:
        app.logger.error(f"调用Gemini API时出错: {e}")
        traceback.print_exc()
        raise

@app.route('/api/ai/conceptualization', methods=['POST'])
def get_conceptualization():
    """为个案概念化生成AI内容。"""
    data = request.json
    user_prompt = f"来访者基本信息:\n{json.dumps(data.get('client_info'), indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{data.get('transcript_content')}\n---"
    try:
        content = call_gemini_api(get_conceptualization_prompt_text(), user_prompt)
        return jsonify({"status": "Complete", "content": content})
    except Exception as e:
        return jsonify({"error": f"AI生成失败: {e}"}), 500

@app.route('/api/ai/assessment', methods=['POST'])
def get_assessment():
    """为来访者评估生成AI内容。"""
    data = request.json
    user_prompt = f"来访者基本信息:\n{json.dumps(data.get('client_info'), indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{data.get('transcript_content')}\n---"
    try:
        content = call_gemini_api(get_assessment_prompt_text(), user_prompt)
        return jsonify({"status": "Complete", "content": content})
    except Exception as e:
        return jsonify({"error": f"AI生成失败: {e}"}), 500

@app.route('/api/ai/supervision', methods=['POST'])
def get_supervision():
    """为督导报告生成AI内容。"""
    data = request.json
    prompt_for_supervision = f"来访者基本信息:\n{json.dumps(data.get('client_info'), indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n{data.get('transcript_content')}\n\nAI生成的个案概念化:\n{data.get('conceptualization_content')}\n\nAI生成的来访者评估:\n{data.get('assessment_content')}"
    try:
        content = call_gemini_api(get_supervision_prompt_text(), prompt_for_supervision)
        return jsonify({"status": "Complete", "content": content})
    except Exception as e:
        return jsonify({"error": f"AI生成失败: {e}"}), 500

# 这是一个回退路由，用于服务前端应用
# 将所有未匹配的URL都指向index.html
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    # 'static' 应该是存放您的index.html文件的文件夹名称
    # 例如: /your_project_folder/static/index.html
    static_folder_path = os.path.join(os.getcwd(), 'static')
    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        return send_from_directory(static_folder_path, 'index.html')


if __name__ == '__main__':
    # Gunicorn等生产服务器将使用此文件，因此debug模式应为False
    app.run(host='0.0.0.0', port=5000, debug=False)
