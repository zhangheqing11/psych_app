# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response, redirect, session, url_for
import requests
import os
import secrets # 用于生成安全的密钥

# 初始化Flask应用
app = Flask(__name__, static_folder='static')

# --- 密钥配置 (非常重要) ---
# 使用环境变量来安全地管理所有密钥
# 您需要在Render的后台设置这些环境变量
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16)) # 用于加密session
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-44e1314da2d94b35b978f0fcd01ed26f") # 您的AI模型密钥
WECHAT_APPID = os.getenv("WECHAT_APPID") # 您的微信服务号AppID
WECHAT_APPSECRET = os.getenv("WECHAT_APPSECRET") # 您的微信服务号AppSecret

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- 路由定义 ---

# **新增**：微信验证文件路由
# 这个路由会精确匹配微信请求的文件名
@app.route('/MP_verify_rHW1SoTh5BroUoXo.txt')
def wechat_verification():
    # 从 'static' 文件夹中发送这个特定的文件
    return send_from_directory(app.static_folder, 'MP_verify_rHW1SoTh5BroUoXo.txt')

@app.route('/')
def serve_index():
    # 检查用户是否已通过微信登录 (通过session)
    if 'wechat_openid' in session:
        # 如果已登录，正常提供前端应用
        response = make_response(send_from_directory(app.static_folder, 'index.html'))
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    else:
        # 如果未登录，重定向到微信授权流程
        return redirect(url_for('wechat_login'))

# 1. 微信登录入口路由
@app.route('/auth/wechat')
def wechat_login():
    if not WECHAT_APPID:
        return "错误: 微信AppID未配置。", 500

    render_url = os.getenv('RENDER_EXTERNAL_URL')
    if not render_url:
        redirect_uri = url_for('wechat_callback', _external=True)
    else:
        redirect_uri = f"https://{render_url}{url_for('wechat_callback')}"
    
    auth_url = (
        "https://open.weixin.qq.com/connect/oauth2/authorize"
        "?appid={appid}"
        "&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=snsapi_userinfo"
        "&state=STATE#wechat_redirect"
    ).format(appid=WECHAT_APPID, redirect_uri=redirect_uri)
    
    return redirect(auth_url)

# 2. 微信授权回调路由
@app.route('/auth/callback')
def wechat_callback():
    code = request.args.get('code')
    if not code:
        return "授权失败，未能获取code。", 400
    
    if not WECHAT_APPID or not WECHAT_APPSECRET:
        return "错误: 微信AppID或AppSecret未配置。", 500

    token_url = (
        "https://api.weixin.qq.com/sns/oauth2/access_token"
        "?appid={appid}"
        "&secret={secret}"
        "&code={code}"
        "&grant_type=authorization_code"
    ).format(appid=WECHAT_APPID, secret=WECHAT_APPSECRET, code=code)
    
    token_response = requests.get(token_url)
    token_data = token_response.json()
    
    if "errcode" in token_data:
        return f"换取access_token失败: {token_data['errmsg']}", 500
        
    access_token = token_data['access_token']
    openid = token_data['openid']
    
    user_info_url = (
        "https://api.weixin.qq.com/sns/userinfo"
        "?access_token={access_token}"
        "&openid={openid}"
        "&lang=zh_CN"
    ).format(access_token=access_token, openid=openid)
    
    user_info_response = requests.get(user_info_url)
    user_info_response.encoding = 'utf-8'
    user_info = user_info_response.json()

    session['wechat_openid'] = openid
    session['wechat_nickname'] = user_info.get('nickname', '未知用户')
    session['wechat_headimgurl'] = user_info.get('headimgurl')

    print(f"用户登录成功: Nickname={session['wechat_nickname']}, OpenID={session['wechat_openid']}")

    return redirect(url_for('serve_index'))


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

    headers = { 'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {
        'model': model,
        'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
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
