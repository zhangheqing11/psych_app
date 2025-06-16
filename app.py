# 安装必要的库: pip install Flask flask-cors requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response
from flask_cors import CORS
import requests
import os

# 初始化Flask应用
# 将静态文件夹设置为当前目录 ('.') 以便正确找到index.html
app = Flask(__name__, static_folder='.')

# --- CORS配置 ---
# 允许来自任何来源的跨域请求，这对于本地开发是必须的
CORS(app)

# --- API 密钥配置 ---
# 您的AI模型密钥，建议未来使用环境变量管理
DEEPSEEK_API_KEY = "sk-44e1314da2d94b35b978f0fcd01ed26f"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- 路由定义 ---

# 根路由: 提供前端应用
@app.route('/')
def serve_index():
    # 从当前目录 (在上面被定义为 static_folder) 提供 index.html
    # 添加 no-cache 头确保浏览器总是获取最新版本，这在开发中非常重要
    response = make_response(send_from_directory(app.static_folder, 'index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# API代理路由: 安全地调用DeepSeek AI模型
@app.route('/api/call-ai', methods=['POST'])
def call_ai_proxy():
    data = request.json
    system_prompt = data.get('systemPrompt')
    user_prompt = data.get('userPrompt')
    model = data.get('model', 'deepseek-chat')
    is_streaming = data.get('stream', True)

    if not user_prompt or not system_prompt:
        return jsonify({"error": "缺少必要的参数 'systemPrompt' 或 'userPrompt'"}), 400

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
    }
    payload = {
        'model': model,
        'messages': [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        'stream': is_streaming
    }

    try:
        proxy_response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, stream=True)
        proxy_response.raise_for_status()

        def generate():
            for chunk in proxy_response.iter_content(chunk_size=None):
                if chunk:
                    yield chunk
        
        return Response(generate(), content_type=proxy_response.headers['Content-Type'])

    except requests.exceptions.RequestException as e:
        print(f"调用DeepSeek API时出错: {e}")
        return jsonify({"error": f"调用外部API失败: {e}"}), 502

# --- 启动服务器 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
