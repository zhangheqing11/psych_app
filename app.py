# --- 部署说明 (重要) ---
# 1. 您的 'requirements.txt' 文件必须包含以下内容：
#    Flask
#    Flask-Cors
#    requests
#    gunicorn
#
# 2. 您的项目文件结构必须如下：
#    / (项目根目录)
#    ├── app.py         (此后端文件)
#    ├── requirements.txt
#    └── static/
#        └── index.html (您的前端文件)
#
# 部署失败或出现白屏通常是因为文件结构不正确。
# -------------------------

# 安装必要的库: pip install Flask Flask-Cors requests gunicorn
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import json
import traceback
import logging
import time
import secrets
import string

# --- Flask 应用设置 ---
# 定义静态文件夹的路径，使其相对于此文件的位置，这在部署时更可靠
static_folder_path = os.path.join(os.path.dirname(__file__), 'static')
app = Flask(__name__, static_folder=static_folder_path)
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
        return {"users": {}, "counselor_data": {"clients": [], "counselors": [], "appointments": []}}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return {"users": {}, "counselor_data": {"clients": [], "counselors": [], "appointments": []}}
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"users": {}, "counselor_data": {"clients": [], "counselors": [], "appointments": []}}

def write_data(data):
    """将数据写入JSON文件。"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def generate_random_key(length=6):
    """生成一个随机的六位字符串作为添加口令。"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

# --- PROMPTS (未更改，为简洁起见已折叠) ---
def get_conceptualization_prompt_text():
    return """..."""

def get_assessment_prompt_text():
    return """..."""
    
def get_supervision_prompt_text():
    return """..."""

# --- 特殊用户 ---
MANAGER_USER = {"username": "Manager", "password": "manager"}

# --- 用户认证API ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    registration_key = data.get('registrationKey')

    if not all([username, password, role]):
        return jsonify({"message": "用户名、密码和角色都是必填项"}), 400

    # 新增：咨询师注册口令验证
    if role == 'counselor':
        if registration_key != 'counselor':
            return jsonify({"message": "注册口令不正确"}), 403
    
    if username == MANAGER_USER['username']:
        return jsonify({"message": "此用户名已被保留"}), 409
    
    all_data = read_data()
    if username in all_data['users']:
        return jsonify({"message": "用户名已存在"}), 409

    all_data['users'][username] = {"password": password, "role": role}
    
    if role == 'client':
        if 'clients' not in all_data['counselor_data']:
            all_data['counselor_data']['clients'] = []
        
        if not any(c.get('username') == username for c in all_data['counselor_data']['clients']):
            new_client_entry = {
                "id": f"client-{int(time.time())}", "username": username, "name": username, 
                "age": "", "gender": "未透露", "contact": "", "sessions": [], 
                "joinDate": time.strftime("%Y-%m-%d"),
                "assignmentKey": generate_random_key() # 新增：为新来访者生成添加口令
            }
            all_data['counselor_data']['clients'].append(new_client_entry)

    elif role == 'counselor':
        if 'counselors' not in all_data['counselor_data']:
            all_data['counselor_data']['counselors'] = []

        if not any(c.get('username') == username for c in all_data['counselor_data']['counselors']):
            new_counselor_entry = {
                "id": f"counselor-{int(time.time())}", "username": username, "name": username, 
                "modality": "待填写",
                "clinicalBackground": "待填写", # 新增：临床和学术背景字段
                "assignedClientIds": []
            }
            all_data['counselor_data']['counselors'].append(new_counselor_entry)

    write_data(all_data)
    
    return jsonify({"message": "注册成功！", "username": username, "role": role}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role_attempt = data.get('role')

    if username == MANAGER_USER['username'] and password == MANAGER_USER['password'] and role_attempt == 'counselor':
        return jsonify({"message": "欢迎回来, Manager!", "username": "Manager", "role": "manager"}), 200

    all_data = read_data()
    user = all_data.get('users', {}).get(username)

    if not user:
        return jsonify({"message": "用户不存在"}), 404
    
    if user['password'] == password and user['role'] == role_attempt:
        return jsonify({"message": f"欢迎回来, {username}!", "username": username, "role": user['role']}), 200
    else:
        return jsonify({"message": "用户名、密码或角色不正确"}), 401

# --- 管理员数据API ---
@app.route('/api/data/manager', methods=['GET'])
def get_manager_data():
    all_data = read_data()
    return jsonify(all_data)

@app.route('/api/data/manager', methods=['POST'])
def save_manager_data():
    new_data = request.get_json()
    write_data(new_data)
    return jsonify({"message": "平台数据已更新"}), 200

# --- 咨询师数据API ---
@app.route('/api/data/counselor/<username>', methods=['GET'])
def get_counselor_data(username):
    all_data = read_data()
    c_data = all_data.get('counselor_data', {})
    
    current_counselor = next((c for c in c_data.get('counselors', []) if c.get('username') == username), None)
    if not current_counselor:
        return jsonify({"message": "咨询师不存在"}), 404

    assigned_client_ids = current_counselor.get('assignedClientIds', [])
    assigned_clients = [client for client in c_data.get('clients', []) if client.get('id') in assigned_client_ids]
    
    all_assigned_ids = set()
    for c in c_data.get('counselors', []):
        all_assigned_ids.update(c.get('assignedClientIds', []))

    unassigned_clients = [client for client in c_data.get('clients', []) if client.get('id') not in all_assigned_ids]
    
    response_data = {
        "counselors": c_data.get('counselors', []),
        "assigned_clients": assigned_clients,
        "unassigned_clients": unassigned_clients,
        "appointments": c_data.get('appointments', [])
    }
    return jsonify(response_data)

@app.route('/api/data/counselor/<username>', methods=['POST'])
def save_counselor_data(username):
    new_data = request.get_json()
    all_data = read_data()
    
    counselor_profile = next((c for c in all_data.get('counselor_data', {}).get('counselors', []) if c.get('username') == username), None)
    if not counselor_profile:
        return jsonify({"message": "无权操作"}), 403

    allowed_client_ids = set(counselor_profile.get('assignedClientIds', []))

    if 'clients' in new_data:
        for updated_client in new_data.get('clients', []):
            if updated_client.get('id') in allowed_client_ids:
                client_index = next((i for i, client in enumerate(all_data['counselor_data']['clients']) if client.get('id') == updated_client.get('id')), -1)
                if client_index != -1:
                    all_data['counselor_data']['clients'][client_index].update(updated_client)

    if 'appointments' in new_data:
        all_data['counselor_data']['appointments'] = new_data.get('appointments', [])

    write_data(all_data)
    return jsonify({"message": "数据保存成功"}), 200

# 新增: 允许咨询师更新自己的档案
@app.route('/api/counselor/profile/<username>', methods=['POST'])
def save_counselor_profile(username):
    """咨询师保存自己的档案信息。"""
    updated_profile_data = request.get_json()
    all_data = read_data()

    counselor_index = next((i for i, c in enumerate(all_data['counselor_data']['counselors']) if c.get('username') == username), -1)
    if counselor_index == -1:
        return jsonify({"message": "咨询师不存在"}), 404
        
    # 定义咨询师可以自己修改的字段
    allowed_fields = ['name', 'modality', 'clinicalBackground']
    for field in allowed_fields:
        if field in updated_profile_data:
            all_data['counselor_data']['counselors'][counselor_index][field] = updated_profile_data[field]
            
    write_data(all_data)
    return jsonify({"message": "您的档案已更新"}), 200

@app.route('/api/counselor/assign', methods=['POST'])
def assign_client_to_counselor():
    data = request.get_json()
    counselor_username = data.get('counselorUsername')
    client_id = data.get('clientId')
    assignment_key = data.get('assignmentKey') # 新增：获取添加口令

    if not all([counselor_username, client_id, assignment_key]):
        return jsonify({"message": "需要提供咨询师、来访者和添加口令信息"}), 400

    all_data = read_data()

    # 验证添加口令
    client_to_assign = next((c for c in all_data['counselor_data']['clients'] if c.get('id') == client_id), None)
    if not client_to_assign:
        return jsonify({"message": "来访者不存在"}), 404
    if client_to_assign.get('assignmentKey') != assignment_key:
        return jsonify({"message": "添加口令不正确"}), 403

    counselor_index = next((i for i, c in enumerate(all_data['counselor_data']['counselors']) if c.get('username') == counselor_username), -1)
    if counselor_index == -1:
        return jsonify({"message": "咨询师不存在"}), 404
        
    if 'assignedClientIds' not in all_data['counselor_data']['counselors'][counselor_index]:
        all_data['counselor_data']['counselors'][counselor_index]['assignedClientIds'] = []
    
    if client_id not in all_data['counselor_data']['counselors'][counselor_index]['assignedClientIds']:
        all_data['counselor_data']['counselors'][counselor_index]['assignedClientIds'].append(client_id)

    write_data(all_data)
    return jsonify({"message": "来访者分配成功"}), 200

# --- 来访者数据API (无变动) ---
@app.route('/api/data/all', methods=['GET'])
def get_all_data_for_client():
    all_data = read_data()
    client_safe_data = {
        "clients": all_data.get('counselor_data', {}).get('clients', []),
        "counselors": all_data.get('counselor_data', {}).get('counselors', []),
        "appointments": all_data.get('counselor_data', {}).get('appointments', [])
    }
    return jsonify(client_safe_data)

@app.route('/api/data/client/<username>', methods=['POST'])
def save_client_data(username):
    updated_profile = request.get_json()
    all_data = read_data()
    
    client_index = next((i for i, c in enumerate(all_data['counselor_data']['clients']) if c.get('username') == username), -1)
    if client_index == -1:
        return jsonify({"message": "来访者不存在"}), 404

    sessions = all_data['counselor_data']['clients'][client_index].get('sessions', [])
    assignment_key = all_data['counselor_data']['clients'][client_index].get('assignmentKey') # 确保口令不被覆盖
    updated_profile['sessions'] = sessions
    updated_profile['assignmentKey'] = assignment_key

    all_data['counselor_data']['clients'][client_index] = updated_profile

    write_data(all_data)
    return jsonify({"message": "您的信息已更新"}), 200

# --- AI 分析 API (无变动) ---
# ... (此部分代码保持不变)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"

def call_gemini_api(system_prompt, user_prompt):
    # ...
    pass
# ... (所有AI相关路由保持不变)

# --- 前端文件服务路由 (无变动) ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
