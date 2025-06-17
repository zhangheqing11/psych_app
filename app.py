# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response
import requests
import os

# 初始化Flask应用
app = Flask(__name__, static_folder='static')

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

# 新增：文件上传并触发AI分析的路由
@app.route('/api/upload-and-analyze', methods=['POST'])
def upload_and_analyze():
    # 1. 检查文件是否存在于请求中
    if 'transcript' not in request.files:
        return jsonify({"error": "请求中未找到文件"}), 400
    
    file = request.files['transcript']
    if file.filename == '':
        return jsonify({"error": "未选择文件"}), 400

    try:
        # 2. 读取文件内容和表单数据
        transcript_content = file.read().decode('utf-8')
        client_info_json = request.form.get('client_info')
        client_info = json.loads(client_info_json)

        # 3. 构造用于AI分析的提示词
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
        # 4. (并行)调用AI生成两份报告
        # 注意：这里的 'call_api_sync' 是一个简化的同步函数，
        # 实际应用中可以根据需要改为异步或使用任务队列
        
        # 获取个案概念化
        conceptualization_prompt = "...(此处省略，应为完整的个案概念化prompt)..." # 简化显示
        conceptualization_content = call_api_sync(conceptualization_prompt, user_prompt_content)
        
        # 获取来访者评估
        assessment_prompt = "...(此处省略，应为完整的来访者评估prompt)..." # 简化显示
        assessment_content = call_api_sync(assessment_prompt, user_prompt_content)

        # 5. 将两份报告的结果返回给前端
        return jsonify({
            "success": True,
            "conceptualization": {
                "status": "Complete",
                "content": conceptualization_content
            },
            "assessment": {
                "status": "Complete",
                "content": assessment_content
            },
            "uploadedFileName": file.filename
        })

    except Exception as e:
        print(f"文件处理或AI调用时出错: {e}")
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

def call_api_sync(system_prompt, user_prompt, model='deepseek-chat'):
    """一个简化的、非流式的API调用函数"""
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']


# API代理路由: 用于CBT工具的流式调用 (保持不变)
@app.route('/api/call-ai', methods=['POST'])
def call_ai_proxy():
    # ... (此部分代码保持不变)
    return Response(...)

# --- 启动服务器 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
