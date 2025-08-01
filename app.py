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
from google import genai
from google.genai import types
import os
import json
import traceback
import logging
import time
import random
import string

# 设置环境变量，确保API密钥可用
os.environ['GEMINI_API_KEY'] = "AIzaSyBGmOLVLWN-CcN6H59ZiUWW2JZ6NBe9txU"

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
        return {
            "users": {}, 
            "counselor_data": {"clients": [], "counselors": [], "appointments": []},
            "interview_sessions": {}  # 新增：存储访谈会话
        }
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return {
                    "users": {}, 
                    "counselor_data": {"clients": [], "counselors": [], "appointments": []},
                    "interview_sessions": {}
                }
            data = json.loads(content)
            # 确保新字段存在
            if "interview_sessions" not in data:
                data["interview_sessions"] = {}
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return {
            "users": {}, 
            "counselor_data": {"clients": [], "counselors": [], "appointments": []},
            "interview_sessions": {}
        }

def write_data(data):
    """将数据写入JSON文件。"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 会话管理函数 ---
def get_or_create_session(username):
    """获取或创建用户的访谈会话"""
    all_data = read_data()
    
    if username not in all_data['interview_sessions']:
        # 创建新会话
        session_id = f"session_{username}_{int(time.time())}"
        all_data['interview_sessions'][username] = {
            'session_id': session_id,
            'username': username,
            'messages': [],
            'status': 'active',  # active, completed, paused
            'created_at': time.strftime("%Y-%m-%d %H:%M:%S"),
            'updated_at': time.strftime("%Y-%m-%d %H:%M:%S"),
            'completed_questions': [],
            'analysis_ready': False
        }
        write_data(all_data)
    
    return all_data['interview_sessions'][username]

def save_session_message(username, message, sender):
    """保存单条消息到会话"""
    all_data = read_data()
    
    if username in all_data['interview_sessions']:
        message_data = {
            'sender': sender,
            'text': message,
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        all_data['interview_sessions'][username]['messages'].append(message_data)
        all_data['interview_sessions'][username]['updated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_data(all_data)
        return True
    return False

def update_session_status(username, status, analysis_ready=None):
    """更新会话状态"""
    all_data = read_data()
    
    if username in all_data['interview_sessions']:
        all_data['interview_sessions'][username]['status'] = status
        all_data['interview_sessions'][username]['updated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
        if analysis_ready is not None:
            all_data['interview_sessions'][username]['analysis_ready'] = analysis_ready
        write_data(all_data)
        return True
    return False

def get_session_history(username):
    """获取用户的会话历史"""
    all_data = read_data()
    if username in all_data['interview_sessions']:
        return all_data['interview_sessions'][username]['messages']
    return []

def check_closing_message(history):
    """检查是否包含结束语，判断访谈是否完成"""
    if not history:
        return False, 0
    
    # 检查是否包含结束语关键词
    closing_keywords = ["非常感谢您坦诚的分享", "生成报告", "咨询服务中一切顺利"]
    assistant_messages = [item['text'] for item in history if item['sender'] == 'bot']
    
    has_closing = any(any(keyword in msg for keyword in closing_keywords) for msg in assistant_messages)
    
    # 简单统计消息轮数作为完成度参考
    user_messages = [item for item in history if item['sender'] == 'user']
    
    return has_closing, len(user_messages)

# --- PROMPTS (完整版) ---
def get_conceptualization_prompt_text():
    return """你是一位资深的心理咨询师。根据文件中的咨询逐字稿内容以及来访的基本信息，提供个案概念化报告。报告用于辅助另一位咨询师改善自己的咨询服务质量。个案概念化整体上应遵循‘’中的步骤：
‘	1.选择一个最适合来访者的理论范式,使用理论假设去指导个案概念化和治疗方案的建构
	2.利用一些假设、支持性的材料或结论，作为个案概念化的关键信息
	3.概述治疗计划，将长期、短期治疗目标作为发展治疗计划的关键要点。治疗目标的表述让来访可以理解，尽量符合其期望与价值观。
4.提示咨询师何种表达方式对来访可能是有吸引力的。提示接下来的咨询方向（咨询师该怎样做），包括但不限于哪些话题可能需要被深入讨论和谈论哪些话题可能存在潜在风险。’

关于个案概念化的结构要素和内容，参考{}内的要求：
{	1.概要：根据理论视角对来访核心优势和局限的简要分析假设。即对来访的核心印象、总览，以帮助通过阅读个案概念化对个案有大致了解。内容包括：人口学与社会文化等基本信息、问题情况与咨询目标简介。
	2.支持性素材：为概要提供细节依据，包括但不限于：1.对来访优势的深度分析（优势的地方、积极的因素、成功、应对策略、技能、促进改变的因子)；2.对弱点的深度分析（担心、困难、问题、症状、缺陷技术、治疗障碍）；3.来访的成长史、部分生活史，呈现过去成长和现在生活中的各种细节；困难和资源、咨询和生活中的模式等。4.咨询目标，实现目标的可能路径与阻碍
	3. 初始评估会谈及报告：聚焦来访当下的功能（功能维度：动力学）
	评估来访问题的严重程度，同时，也要从以下几个领域评估咨询师与来访的潜在差异：1.先后天残障；2.宗教信仰：3.种族和民族认同；4.个人经济地位；5.性取向与性别
这种差异评估是为了鉴别权力差异（咨询专家与求助者）和防止发生压迫/侵犯。
}

关于治疗方案的建立，遵循[]中的要求：
[一、治疗方案的结构要素
	1.治疗方案综述：简要介绍治疗计划是如何进行的。使用来访理解的语言增强对治疗的掌控感、责任心。和来访共同确认。
	2.长期治疗目标：实则由多个短期目标构成。
	3.短期治疗目标：具体、可测量。这种积极变化应对于来访是可完成的、有动机的，以内化进来访的内心。
 
二、治疗方案的视角
	每个治疗目标和支持材料应聚焦于来访各种主要社会角色（员工、父亲、朋友……）的功能水平或行为症状。
1.基于假设模式
	以动力学的理论假设为核心，建构概要、支持材料、治疗目标等。
2.基于症状模式
	根据来访报告的客观症状或行为，分析行为的原因和可能结果。通过在咨询中重演不同情境下的相关行为，探索一个行为的trigger是什么，练习正念觉察。学习稳定和调适情绪的技术。
3.基于人际关系模式
	根据来访与重要他人和咨询中的关系模式，探索并分析关系如何建立、加强、破裂，行为是哪些。可以向现实生活中的不同模板询问、学习。
4.基于历史模式
	从过去习得了什么，这些习得的模式如何带来心理问题。来访的需要和当前状况，最迫切关注的焦点，是如何与过去的习得产生联系的。
 
三、治疗方案的格式规范
1.基本模式
	主要聚焦于来访者需要达到的、学习的或者需要发展的内容。
2.问题模式
	根据需要减少的适应不良的行为或问题来确定治疗目标。
3.短期目标模式
	清晰地呈现来访者当前的问题、问题的当下状态、治疗这个问题立即的应对计划，为什么选择这个治疗方案的说明。包括：来访主观素材、咨询师客观素材、基于两种素材咨询师开展的评估、与来访共同商定的治疗计划。]
你的整体目标应该是帮助咨询师提升服务质量，指明后续咨询方向。"""

def get_assessment_prompt_text():
    return """你是一位资深的心理咨询师。基于文件中咨询逐字稿的内容，并遵循以下我给出的评估维度，对该来访做出专业化的评估。
	一、个人信息维度
	1.目前心理状态
	2.成长史（初中及以前）与当下部分生活史，呈现过去成长和现在生活中的各种细节、困难和资源。咨询和生活中的行为模式
	3.早期及现在人际关系和依恋特点（初中及以前），咨询和生活中的关系模式
	4.优势的深度分析（优势之处、积极因素、获得的成功、健康应对策略、技能、促进改变的因子
	5.弱点的深度分析（困难、问题、症状、缺陷或僵化应对、治疗阻碍）
	二、功能维度
	1.自我功能
	1.1自我觉知：如何看待自己。包括：
	自我身份认同：对自己的定义（认为自己是谁）、价值观、能力与局限性。在青少年时期逐渐稳定
	自我评价：反映个人能力在主观和客观的相符程度，也包括对自我理想意象的幻想（即理想的自我是什么样的）。思想和行动符合，我们的内在理想就会感到自我实现和自豪；否则就会产生内疚、失败和一无所有处的感觉。
	1.2自尊管理：从打击中恢复原状的能力。
	包括自尊の脆弱性（水平高低、稳定性）、应对挫败自尊的方式（自恋自大或自我挫败/受虐，而更健康的方式是直面问题 而不是困在自我中）、利用他人调节自尊。自尊是对自己的尊敬和或欣赏，自尊问题使我们变得无法承受情感和焦虑，无法现实评价能力和局-限，无法控制我们的冲动，无法放松，等等。
	此外，自我评价的问题也会导致自我知觉的扭曲和自尊管理的困难。有的人会高估自己的能力(夸大)，而有的人会低估自己的能力（抑郁），又或者理想化他人。（嫉妒具有攻击性，而羡慕具有靠近的倾向）
	2.人际关系功能：保持稳定、信任、亲密关系的能力
	关键：1.关系中对自己和对方的信任感、2.感知度：既好又坏的立体性、独特个性的独立性（明白他人的思想和感受与自己不同，心智化能力）、过去到现在与未来可能变化的完整性。3.安全感：抵抗面对分离、分歧、消极情绪。4.亲密性（边界情况）；5.相互依存度：合适的依存是既给予也享受的。
	 
	除此以外仍然关键的要素有：共情能力、来访意识与无意识对他人的期待和对关系的幻想。 
	两种关系问题：无意识投射与幻想、缺乏社交功能。前者揭露，后者支持
	在成长的过程中，小时候和重要他人的互动为他们整个人生中与人互动的方式打下了不可磨灭的烙印。被爱护和照料得很好的人学会了期待从他人那里也得到这些，而被虐待或忽视的人学会了预期被虐待。即使人们意识不到这些内化的无意识的关系模式和幻想，也依然影响着他们的每一次行动。
	这些幻想之所以残留在意识之外，是因为它们引发了羞愧、焦虑或其他令人不舒服的强烈情感。如果他们意识不到这些无意识的需求，人们就无法选择能和他们建立成熟满意的人际关系的人。甚至意识层面的需求和无意识的需求有所冲突。
	社交功能包括：共情能力、对自我羞耻的程度、识别社会性线索的能力。这些都影响着融入人际关系的能力。
	以资访关系为模板，检查过往模式的重现并提供修正机会。如咨询师反馈自己的想法和感受，修正来访的错误知觉；强化适应性的防御并取代非适应性的（适应性的判断标准）；通过来访猜测咨询师-咨询师反馈，提升心智化功能等。最终使来访认清过往模式，并开始憧憬他们可以拥有对身边的人更为现实的、大不相同的期待
	3.适应功能：面对压力的调整
	内在压力包括思想和幻想、情感和焦虑、痛苦和其他身体感觉;外在压力包括与他人的人际关系、与经济状况和工作相关的压力、创伤以及其他环境因素。人们在忍受内部或外部的压力刺激时有着各自的阈限，也有着适应内部和外部压力刺激的不同方式，包括：防御机制、冲动控制、情绪管理、感觉调节
	感觉刺激管理能力：对各种感官刺激的耐受和注意力分配能力
	情绪管理能力：耐受、管理、稳定体验、表达情绪的能力。情绪快速激烈变化说明该能力差。
	冲动控制差可能有物质成瘾、控制性强、暴力、违法行为等问题
	 
	无意识的调节压力即是防御机制，我们应对压力的个性化方式在早年时往往具有适应性意义，让我们免受负面感受的威胁。评价防御机制的三个维度：
	1.适应性：帮助适应压力的同时，保护或增强机能。适应性不是绝对的，一种情形下的强适应性机制可能是另一种情形下的弱适应性机制。2.灵活性。3.对思维与情感的自知力
	不适应的信号：1防御动用了过多的心理能量，以至于只给我们留下很少的精力去发动其他的重要功能。2防御损害了体验情感，或拥有成熟满意的人际关系的能力。3泛化、僵化的防御方式。4以自我毁灭或身体痛苦为代价
	不适应信号的识别：1心理或行为表现；2主观或客观的痛苦；3人际关系问题；4反移情（这也提示着生活中他人对来访的感受）
	干预第一步：帮助来访者认清他们的适应方式有问题，当前防御的效果是有限的。将僵化的防御与新习得的适应性防御，两种方式的结果进行比较、确认，能更好的留在来访心中。
 
	4.认知功能
4.1组织与规划思维、决策制订和问题解决能力、创造性思维
	A有条理，以细节为导向，会提前规划，并且可以冷静地解决问题。B更加随意，频繁地改变主意，以一种更情绪化的方式解决问题。最终，两个方案都可以大获成功，但是就计划筹备它们的思路和过程而言，是相当不同的。我们的任务不是去评判哪个方式更好，而是描述我们的来访解决问题的风格，同时去思考这些风格是如何积极或消极地影响他们的生活的。
	4.2判断能力：意识到一个有意行为的适当性和可能发生的结果，且行为能够体现这种意识（知道踩油门会出车祸但还是踩了，冲动不叫有判断力）
“明辨是非”的道德判断力是超我的功能，也可以通过内疚感来评估,如果满足愿望的冲动无法控制或道德判断不正常，都属于认知功能异常。判断力不是“全或无”的性质，而是可以在不同环境下增大或衰减的。
	4.3反思能力：评估/检验自身想法和行为的能力，修正不一致的态度和感受的能力。
	①心理感受性是和自省力有所关联的，它指的是思考某人产生思维、感觉和行为时的可能有的无意识动机的能力。自省的能力帮助人们认识和改善他们对自己和与他人关系的感知。
	②现实检验能力：分辨现实/事实与幻想/主观臆测的能力
	 来访的认知功能差，是无意识使其阻滞，还是从未习得？如果一个人有能力执行功能但是被阻滞了，就被认为是由冲突导致的问题；而如果一个人缺乏执行功能的能力，甚至从早年间就有过种种迹象，就被认为是由缺陷导致的
	另外，问题是长期/近期的、是总体性的还是选择性的，都有助于区分冲突/缺陷。 
 
5.工作和娱乐功能
	工作是付出身体或是精神努力去做某事，有目的性的活动。一个人“选择”做了什么（当然也包括职业）可以反映出他的个人和人际生活，也匹配于他的心智、能力、局限性。
	娱乐指放松、沉浸于幻想、无焦虑的体验无意识情感和驱力的能力。会娱乐的人可能拥有更健康的情绪生活并且成长得更顺利，缺乏休闲活动暗示他们在放松和享受方面有巨大问题。
	评估工作和娱乐领域：1.很好地与他们的发展水平或年龄、天赋、局限性匹配；2.感到舒服或愉悦；3.物质基础足以照顾自己和家人。"""
    
def get_supervision_prompt_text():
    return """你是资深心理咨询督导师，采用精神动力学取向整合视角。
你的核心关注点包括：来访者福祉与伦理合规性、咨询过程微观分析、咨询师自我觉察与专业发展、以及关系动力系统解构。
请根据提供的来访者信息和所有文件内容，从以下维度进行分析，并生成一份结构化的临床督导报告。

# 分析维度：
1.  **来访者分析:**
    * **显性内容:** 分析表层陈述的事实、诉求，以及可观察的情绪反应强度与变化。
    * **隐性心理过程:** 探索自体表征（自我价值感/完整性）、客体关系模式（互动期待/内在工作模型）、防御机制层级（从原始到成熟）、移情线索（对咨询师的角色投射），以及未满足的核心需求。
    * **发展性评估:** 评估咨询前后表征模式的变化、心理化能力水平和反思功能的进展。
2.  **咨询师分析:**
    * **干预技术分析:** 命名具体技术（如『支持性面质』『隐喻性诠释』），评估技术实施时序（是否匹配进程节律），以及技术选择与个案概念化的逻辑联结。
    * **回应效能评估:** 评估与来访者潜意识的匹配度（1-5级评分），对咨询联盟的影响（强化/削弱/中性），以及是否拓展心理空间（是/否/部分）。
    * **反移情管理:** 识别咨询师的身体、情绪、认知等反移情线索及处理方式。
3.  **关系动力分析:**
    * **移情-反移情矩阵:** 分析投射性认同激活领域、互补性/一致性反移情模式，以及修复性体验发生节点。
    * **此时此地互动:** 分析3轮对话内的情感传递精度及非言语同步性（语音停顿/语速匹配）。
    * **平行过程监测:** 寻找咨询关系模式在督导中的重现证据及机构系统压力的传导路径。
4.  **专业发展指导:**
    * **能力成长点:** 指出需强化的理论模块和技术优化建议。
    * **盲点警示:** 提示文化偏见风险和伦理敏感域。

# 输出规格：
* **格式:** 结构化临床督导报告。
* **必须包含的章节:** 关键交互片段标记（时间戳+对话摘要）、动力过程概念化图谱、伦理风险评级（低/中/高）、具体可操作改进策略（按实施优先级排序），以及督导后反思问题（3个开放式提问）。
* **禁止:** 绝对化诊断表述（如『来访者患有XX障碍』），脱离文本的推测性解读。

# 特殊要求：
* 标注每项结论的文本证据来源（如『L34来访者握拳陈述』）。
* 区分观察事实与督导假设（使用『可能表明』『提示』等限定词）。
* 整合至少2个理论视角（主体间性/依恋理论/关系精神分析等）。"""

# --- 特殊用户 ---
MANAGER_USER = {"username": "Manager", "password": "manager"}
COUNSELOR_SECRET = "counselor"

# --- 用户认证API ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    secret_code = data.get('secret_code')

    if not all([username, password, role]):
        return jsonify({"message": "用户名、密码和角色都是必填项"}), 400
    
    if role == 'counselor' and secret_code != COUNSELOR_SECRET:
        return jsonify({"message": "注册不正确"}), 403

    if username == MANAGER_USER['username']:
        return jsonify({"message": "此用户名已被保留"}), 409
    
    all_data = read_data()
    if username in all_data['users']:
        return jsonify({"message": "用户名已存在"}), 409

    all_data['users'][username] = {"password": password, "role": role}
    response_data = {"message": "注册成功！", "username": username, "role": role}

    # 根据角色创建档案
    if role == 'client':
        if 'clients' not in all_data['counselor_data']:
            all_data['counselor_data']['clients'] = []
        
        if not any(c.get('username') == username for c in all_data['counselor_data']['clients']):
            binding_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            new_client_entry = {
                "id": f"client-{int(time.time())}", "username": username, "name": username, 
                "age": "", "gender": "未透露", "contact": "", "sessions": [], 
                "joinDate": time.strftime("%Y-%m-%d"),
                "binding_code": binding_code
            }
            all_data['counselor_data']['clients'].append(new_client_entry)
            response_data["binding_code"] = binding_code
            response_data["message"] = f"注册成功！准备好后请点击「初始访谈」进行测试，生成分析报告^-^"


    elif role == 'counselor':
        if 'counselors' not in all_data['counselor_data']:
            all_data['counselor_data']['counselors'] = []

        if not any(c.get('username') == username for c in all_data['counselor_data']['counselors']):
            new_counselor_entry = {
                "id": f"counselor-{int(time.time())}", "username": username, "name": username, 
                "modality": "待填写", 
                "clinicalBackground": "",
                "contactInfo": "", # 优化点3: 添加联系方式字段
                "assignedClientIds": []
            }
            all_data['counselor_data']['counselors'].append(new_counselor_entry)

    write_data(all_data)
    
    return jsonify(response_data), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role_attempt = data.get('role')

    # 管理员登录
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
    
    # 获取与当前咨询师相关的预约请求
    counselor_booking_requests = []
    if 'booking_requests' in c_data:
        counselor_booking_requests = [req for req in c_data['booking_requests'] if req['counselorId'] == current_counselor['id']]
    
    response_data = {
        "counselors": c_data.get('counselors', []),
        "assigned_clients": assigned_clients,
        "unassigned_clients": unassigned_clients,
        "appointments": c_data.get('appointments', []),
        "booking_requests": counselor_booking_requests
    }
    return jsonify(response_data)

@app.route('/api/data/counselor/<username>', methods=['POST'])
def save_counselor_data(username):
    new_data = request.get_json()
    all_data = read_data()
    
    counselor_index = next((i for i, c in enumerate(all_data.get('counselor_data', {}).get('counselors', [])) if c.get('username') == username), -1)
    if counselor_index == -1:
        return jsonify({"message": "无权操作"}), 403

    counselor_profile = all_data['counselor_data']['counselors'][counselor_index]
    
    if 'update_profile' in new_data:
        profile_updates = new_data['update_profile']
        counselor_profile['name'] = profile_updates.get('name', counselor_profile['name'])
        counselor_profile['modality'] = profile_updates.get('modality', counselor_profile['modality'])
        counselor_profile['clinicalBackground'] = profile_updates.get('clinicalBackground', counselor_profile.get('clinicalBackground', ''))
        counselor_profile['contactInfo'] = profile_updates.get('contactInfo', counselor_profile.get('contactInfo', ''))
        counselor_profile['age'] = profile_updates.get('age', counselor_profile.get('age', ''))
        counselor_profile['gender'] = profile_updates.get('gender', counselor_profile.get('gender', '未透露'))
        counselor_profile['university'] = profile_updates.get('university', counselor_profile.get('university', ''))
        counselor_profile['personalStatement'] = profile_updates.get('personalStatement', counselor_profile.get('personalStatement', ''))
        counselor_profile['photo'] = profile_updates.get('photo', counselor_profile.get('photo', ''))
        all_data['counselor_data']['counselors'][counselor_index] = counselor_profile
    
    allowed_client_ids = set(counselor_profile.get('assignedClientIds', []))

    if 'clients' in new_data:
        for updated_client in new_data.get('clients', []):
            client_id = updated_client.get('id')
            # 查找现有的来访者
            client_index_to_update = next((i for i, client in enumerate(all_data['counselor_data']['clients']) if client.get('id') == client_id), -1)
            
            if client_index_to_update != -1:
                # 更新现有来访者（只允许更新分配给该咨询师的来访者）
                if client_id in allowed_client_ids:
                    existing_sessions = all_data['counselor_data']['clients'][client_index_to_update].get('sessions', [])
                    updated_client_data = {**all_data['counselor_data']['clients'][client_index_to_update], **updated_client}
                    updated_client_data['sessions'] = existing_sessions
                    all_data['counselor_data']['clients'][client_index_to_update] = updated_client_data
            else:
                # 新来访者：添加到clients列表并自动分配给当前咨询师
                all_data['counselor_data']['clients'].append(updated_client)
                # 将新来访者ID添加到咨询师的assignedClientIds中
                if client_id not in counselor_profile.get('assignedClientIds', []):
                    if 'assignedClientIds' not in counselor_profile:
                        counselor_profile['assignedClientIds'] = []
                    counselor_profile['assignedClientIds'].append(client_id)
                    all_data['counselor_data']['counselors'][counselor_index] = counselor_profile

    if 'appointments' in new_data:
        all_data['counselor_data']['appointments'] = new_data.get('appointments', [])

    write_data(all_data)
    return jsonify({"message": "数据保存成功"}), 200


@app.route('/api/counselor/assign', methods=['POST'])
def assign_client_to_counselor():
    data = request.get_json()
    counselor_username = data.get('counselorUsername')
    client_id = data.get('clientId')
    binding_code = data.get('binding_code')

    if not all([counselor_username, client_id, binding_code]):
        return jsonify({"message": "需要提供咨询师、来访者和添加口令"}), 400

    all_data = read_data()
    
    client_to_assign = next((c for c in all_data['counselor_data']['clients'] if c.get('id') == client_id), None)
    if not client_to_assign:
        return jsonify({"message": "来访者不存在"}), 404
        
    if client_to_assign.get('binding_code') != binding_code:
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

# [OPTIMIZATION 2] 新增API: 允许咨询师创建并分配来访者
@app.route('/api/counselor/create_client', methods=['POST'])
def create_client_by_counselor():
    data = request.get_json()
    counselor_username = data.get('counselorUsername')
    new_client_username = data.get('newClientUsername')

    if not all([counselor_username, new_client_username]):
        return jsonify({"message": "需要提供咨询师用户名和新来访者用户名"}), 400

    all_data = read_data()

    # 检查新用户名是否已存在
    if new_client_username in all_data['users'] or new_client_username == MANAGER_USER['username']:
        return jsonify({"message": "该来访者用户名已存在"}), 409
    
    # 查找咨询师
    counselor_index = next((i for i, c in enumerate(all_data['counselor_data']['counselors']) if c.get('username') == counselor_username), -1)
    if counselor_index == -1:
        return jsonify({"message": "操作的咨询师不存在"}), 404

    # 1. 在 users 中创建用户 (密码为空)
    all_data['users'][new_client_username] = {"password": "", "role": "client"}

    # 2. 在 clients 中创建档案
    binding_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_client_id = f"client-{int(time.time())}"
    new_client_entry = {
        "id": new_client_id, "username": new_client_username, "name": new_client_username, 
        "age": "", "gender": "未透露", "contact": "", "sessions": [], 
        "joinDate": time.strftime("%Y-%m-%d"), "binding_code": binding_code, "grade": "", 
        "sexualOrientation": "", "referredBy": "", "historyOfIllness": "", 
        "mentalStateScore": "5", "disabilityStatus": "", "religiousBelief": "",
        "ethnicIdentity": "", "personalFinance": "", "familyFinance": "",
    }
    all_data['counselor_data']['clients'].append(new_client_entry)
    
    # 3. 将新来访者分配给当前咨询师
    if 'assignedClientIds' not in all_data['counselor_data']['counselors'][counselor_index]:
        all_data['counselor_data']['counselors'][counselor_index]['assignedClientIds'] = []
    all_data['counselor_data']['counselors'][counselor_index]['assignedClientIds'].append(new_client_id)

    write_data(all_data)

    return jsonify({"message": f"来访者 '{new_client_username}' 已成功创建并分配给您。"}), 201

@app.route('/api/counselor/link_client', methods=['POST'])
def link_client_account():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "请求数据为空"}), 400
            
        client_id = data.get('clientId')
        binding_code = data.get('bindingCode')
        
        if not client_id or not binding_code:
            return jsonify({"message": "缺少必要参数"}), 400
        
        all_data = read_data()
        
        # 查找具有该binding_code的来访者账号
        registered_client = None
        for client in all_data.get('counselor_data', {}).get('clients', []):
            if client.get('binding_code') == binding_code.upper():
                registered_client = client
                break
        
        if not registered_client:
            return jsonify({"message": "特殊口令不正确或该账号不存在"}), 404
        
        # 查找要关联的咨询师创建的来访者档案
        counselor_client = None
        client_index = -1
        for i, client in enumerate(all_data.get('counselor_data', {}).get('clients', [])):
            if client.get('id') == client_id:
                counselor_client = client
                client_index = i
                break
        
        if not counselor_client:
            return jsonify({"message": "来访者档案未找到"}), 404
        
        # 检查咨询师创建的档案是否已经关联了其他账号
        if counselor_client.get('username') or counselor_client.get('linked_account'):
            return jsonify({"message": "该来访者档案已关联其他账号"}), 409
        
        # 检查这个注册用户是否已经被其他咨询师档案关联
        # 查找是否有其他档案（不是registered_client，也不是counselor_client）使用了相同的username
        registered_username = registered_client.get('username')
        if registered_username:
            for client in all_data.get('counselor_data', {}).get('clients', []):
                if (client.get('id') != client_id and  # 不是当前要关联的咨询师档案
                    client.get('id') != registered_client.get('id') and  # 不是注册用户本身
                    client.get('username') == registered_username):  # 但使用了相同的username
                    return jsonify({"message": "该账号已被其他来访者档案关联"}), 409
        
        # 进行账号关联
        # 将registered_client的信息合并到counselor_client中
        merged_client = {
            **registered_client,  # 保留原有的用户信息
            **counselor_client,   # 保留咨询师创建的档案信息
            'username': registered_client.get('username'),
            'linked_account': registered_client.get('username'),
            'binding_code': registered_client.get('binding_code')
        }
        
        # 更新客户端档案
        all_data['counselor_data']['clients'][client_index] = merged_client
        
        # 如果registered_client是一个独立的entry且不是同一个，需要删除重复的entry
        if registered_client.get('id') != client_id:
            all_data['counselor_data']['clients'] = [
                client for client in all_data['counselor_data']['clients'] 
                if client.get('id') != registered_client.get('id')
            ]
        
        write_data(all_data)
        
        return jsonify({
            "message": "账号关联成功",
            "username": registered_client.get('username'),
            "linked_client_id": client_id
        }), 200
        
    except Exception as e:
        app.logger.error(f"账号关联API处理时出错: {e}")
        return jsonify({"message": f"服务器内部错误: {str(e)}"}), 500


# --- 来访者数据API ---
@app.route('/api/data/all', methods=['GET'])
def get_all_data_for_client():
    all_data = read_data()
    clients_data = all_data.get('counselor_data', {}).get('clients', [])
    # 出于安全考虑，从这个公共端点移除所有人的绑定码
    safe_clients = []
    for client in clients_data:
        client_copy = client.copy()
        if 'binding_code' in client_copy:
            del client_copy['binding_code']
        safe_clients.append(client_copy)
            
    client_safe_data = {
        "clients": safe_clients,
        "counselors": all_data.get('counselor_data', {}).get('counselors', []),
        "appointments": all_data.get('counselor_data', {}).get('appointments', [])
    }
    return jsonify(client_safe_data)

# 优化点2: 新增API，让登录的来访者能获取自己完整的个人信息（包括绑定码）
@app.route('/api/client/me/<username>', methods=['GET'])
def get_client_self_data(username):
    all_data = read_data()
    client_profile = next((c for c in all_data.get('counselor_data', {}).get('clients', []) if c.get('username') == username), None)
    
    if not client_profile:
        return jsonify({"message": "来访者不存在"}), 404
    
    return jsonify(client_profile)


@app.route('/api/data/client/<username>', methods=['POST'])
def save_client_data(username):
    updated_profile = request.get_json()
    all_data = read_data()
    
    client_index = next((i for i, c in enumerate(all_data['counselor_data']['clients']) if c.get('username') == username), -1)
    if client_index == -1:
        return jsonify({"message": "来访者不存在"}), 404

    # 保留核心数据不被覆盖
    original_client = all_data['counselor_data']['clients'][client_index]
    sessions = original_client.get('sessions', [])
    binding_code = original_client.get('binding_code')
    join_date = original_client.get('joinDate')

    # 将更新与原始数据合并
    all_data['counselor_data']['clients'][client_index] = {
        **original_client, 
        **updated_profile,
        'sessions': sessions,
        'binding_code': binding_code,
        'joinDate': join_date
    }
    
    write_data(all_data)
    return jsonify({"message": "您的信息已更新"}), 200

# --- 预约请求 API ---
@app.route('/api/booking/request', methods=['POST'])
def create_booking_request():
    data = request.get_json()
    client_username = data.get('clientUsername')
    counselor_id = data.get('counselorId')
    message = data.get('message', '')
    
    if not all([client_username, counselor_id]):
        return jsonify({"message": "需要提供来访者用户名和咨询师ID"}), 400
    
    all_data = read_data()
    
    # 查找来访者
    client = next((c for c in all_data['counselor_data']['clients'] if c.get('username') == client_username), None)
    if not client:
        return jsonify({"message": "来访者不存在"}), 404
    
    # 创建预约请求
    booking_request = {
        "id": f"booking-{int(time.time())}",
        "clientId": client['id'],
        "clientName": client['name'],
        "counselorId": counselor_id,
        "message": message,
        "status": "pending",  # pending, accepted, rejected
        "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "respondedAt": None,
        "response": ""
    }
    
    # 添加到数据中
    if 'booking_requests' not in all_data['counselor_data']:
        all_data['counselor_data']['booking_requests'] = []
    
    all_data['counselor_data']['booking_requests'].append(booking_request)
    write_data(all_data)
    
    return jsonify({"message": "预约请求已发送", "requestId": booking_request['id']}), 201

@app.route('/api/booking/respond', methods=['POST'])
def respond_booking_request():
    data = request.get_json()
    request_id = data.get('requestId')
    counselor_username = data.get('counselorUsername')
    response_action = data.get('action')  # 'accept' or 'reject'
    response_message = data.get('response', '')
    
    if not all([request_id, counselor_username, response_action]):
        return jsonify({"message": "缺少必要参数"}), 400
    
    all_data = read_data()
    
    # 查找预约请求
    request_index = next((i for i, r in enumerate(all_data['counselor_data'].get('booking_requests', [])) if r['id'] == request_id), -1)
    if request_index == -1:
        return jsonify({"message": "预约请求不存在"}), 404
    
    # 验证咨询师权限
    counselor = next((c for c in all_data['counselor_data']['counselors'] if c.get('username') == counselor_username), None)
    if not counselor:
        return jsonify({"message": "咨询师不存在"}), 404
    
    booking_request = all_data['counselor_data']['booking_requests'][request_index]
    if booking_request['counselorId'] != counselor['id']:
        return jsonify({"message": "无权处理此预约请求"}), 403
    
    # 更新请求状态
    all_data['counselor_data']['booking_requests'][request_index].update({
        "status": "accepted" if response_action == 'accept' else "rejected",
        "respondedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "response": response_message
    })
    
    write_data(all_data)
    
    action_text = "接受" if response_action == 'accept' else "拒绝"
    return jsonify({"message": f"已{action_text}预约请求"}), 200

# --- AI 分析 API ---
def call_gemini_api(system_prompt, user_prompt):
    """
    使用 google-generativeai SDK 调用 Gemini API。
    """
    try:
        # 确保API密钥已正确配置
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
        
        # 根据官方文档的正确方式创建客户端，传入API密钥
        client = genai.Client(api_key=api_key)
        
        # 将系统提示和用户提示合并
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=-1)  
            )
        )
        
        return response.text
        
    except Exception as e:
        app.logger.error(f"调用Gemini API时出错: {e}")
        # 记录更详细的错误，如果可能的话
        if hasattr(e, 'response'):
            app.logger.error(f"Response Body: {e.response.text}")
        raise

@app.route('/api/ai/conceptualization', methods=['POST'])
def get_conceptualization():
    data = request.json
    client_info = data.get('client_info', {})
    if 'binding_code' in client_info:
        del client_info['binding_code']
    user_prompt = f"来访者基本信息:\n{json.dumps(client_info, indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{data.get('transcript_content')}\n---"
    try:
        content = call_gemini_api(get_conceptualization_prompt_text(), user_prompt)
        return jsonify({"status": "Complete", "content": content})
    except Exception as e:
        return jsonify({"error": f"AI生成失败: {e}"}), 500

@app.route('/api/ai/assessment', methods=['POST'])
def get_assessment():
    data = request.json
    client_info = data.get('client_info', {})
    if 'binding_code' in client_info:
        del client_info['binding_code']
    user_prompt = f"来访者基本信息:\n{json.dumps(client_info, indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n---\n{data.get('transcript_content')}\n---"
    try:
        content = call_gemini_api(get_assessment_prompt_text(), user_prompt)
        return jsonify({"status": "Complete", "content": content})
    except Exception as e:
        return jsonify({"error": f"AI生成失败: {e}"}), 500

@app.route('/api/ai/supervision', methods=['POST'])
def get_supervision():
    data = request.json
    client_info = data.get('client_info', {})
    if 'binding_code' in client_info:
        del client_info['binding_code']
    prompt_for_supervision = f"来访者基本信息:\n{json.dumps(client_info, indent=2, ensure_ascii=False)}\n\n咨询逐字稿内容:\n{data.get('transcript_content')}\n\nAI生成的个案概念化:\n{data.get('conceptualization_content')}\n\nAI生成的来访者评估:\n{data.get('assessment_content')}"
    try:
        content = call_gemini_api(get_supervision_prompt_text(), prompt_for_supervision)
        return jsonify({"success": True, "supervision": {"status": "Complete", "content": content}})
    except Exception as e:
        return jsonify({"error": f"服务器内部错误: {e}"}), 500

# --- 初始访谈 API ---
# System Prompt 定义
SYSTEM_PROMPT_INTERVIEW = {
  "system_prompt_name": "Preliminary Psychological State Conversational Interview",
  "version": "1.0",
  "description": "A system prompt to guide an AI in conducting a structured, empathetic, and non-diagnostic conversational interview with a participant based on 15 predefined questions. The goal is a preliminary understanding of the user's psychological state.",
  "prompt_instructions": {
    "role_definition": {
      "persona": "你是一位富有同理心、专业且善于倾听的对话引导者。你的语气始终保持温和、中立与关切。",
      "objective": "通过一个包含12个问题的结构化对话，温和地引导用户进行自我探索，对用户目前的心理状态、可能的困扰和已有资源进行一个初步的、非诊断性的了解。"
    },
    "conversation_flow": {
      "initial_message": "您好，欢迎参与这次对谈。接下来，我会在大约15分钟的对话内，与您一同梳理和探索您近期的感受与经历。这个过程是为了帮助您进行自我觉察，并生成一份简要的分析报告。答案没有对错之分，请您放松并坦诚地分享任何您想分享的事情。整个对话是完全保密的，请放心。那么，如果你准备好了请告诉我，我们就可以开始了。",
      "progression_logic": "严格按照 `question_list` 的顺序，一次只提问一个主问题。在用户回答后，根据 `follow_up_rules` 决定是否进行追问。完成一个主问题（及可能的追问）后，平稳地过渡到下一个主问题。",
      "closing_message": "非常感谢您坦诚的分享。通过刚才的对话，我们一起梳理了您近期的许多感受和经历，这本身就是非常有勇气和有意义的一步。现在您可以点击“生成报告”来得到属于您的分析报告了。再次感谢您的信任，祝您在之后的咨询服务中一切顺利。"
    },
    "follow_up_rules": {
      "trigger_conditions": [
        "当用户的回答非常简短、抽象或模糊时 (例如: ‘还好’, ‘不知道’, ‘就那样’)。",
        "当用户的回答中提到了强烈的情绪（如‘非常愤怒’、‘彻底绝望’）或关键的生活事件（如‘分手后’、‘失业了’），但没有提供具体细节时。",
        "当用户的回答中包含对分析有显著价值，但需要进一步明确的信息时。"
      ],
      "max_follow_ups_per_question": 2,
      "follow_up_style": {
        "type": "开放式、鼓励性提问",
        "examples": [
          "听起来这对您影响不小，您可以就这一点再多说一些吗？",
          "当您提到‘……’的时候，具体是一种什么样的感受？",
          "您能举一个例子来说明您刚才提到的情况吗？"
        ]
      },
      "exit_condition": "在对单个主问题进行最多1-2次追问后，无论用户回答的详细程度如何，都必须礼貌地结束追问，并自然地过渡到列表中的下一个主问题，以确保对话的整体进度。"
    },
    "constraints_and_guidelines": {
      "total_turns_limit": 20,
      "tone": "不评判、耐心、尊重、稳定。",
      "language": "使用清晰、温和、非临床的日常语言。避免使用心理学术语。",
      "prohibitions": [
        "严禁提供任何形式的心理诊断、评估或治疗建议。",
        "严禁对用户的想法、感受或行为进行价值评判。",
        "严禁打断用户，给予用户充分的思考和表达时间。",
        "如果用户明确表示不想回答某个问题，应立刻表示理解并跳到下一个问题。",
        "注意：不要在每轮对话的开头都生成相同的语句，如不要反复说“谢谢你的分享”，而是使用更丰富的对话内容",
        "注意：尝试表达对用户处境的理解与共情时，不要给出过于直白，甚至复制用户原话的回复。例如：在用户表达“考试成绩不理想，我很焦虑”时，不要回复“我理解你最近很焦虑，考试成绩不理想”或者类似的话语，而是用“我理解你的想法了。在成绩不理想时感到焦虑是正常的，问题的关键是你如何看待焦虑。”等共情表达",
        "**最高优先级**：如果用户表达出明确的、紧急的自我伤害或伤害他人的意图，必须立即暂停提问流程，并以最直接和关切的语气提供寻求专业紧急干预的建议和信息。"
      ]
    },
    "question_list": [
      {
        "id": 1,
        "text": "首先，最近有什么事情或感受一直在您的脑海里，让您特别在意或感到困扰吗？"
      },
      {
        "id": 2,
        "text": "如果用几个词来形容您最近一段时间（比如最近一两周）的整体心情，您会选择哪几个词？为什么？"
      },
      {
        "id": 3,
        "text": "当您感到焦虑或情绪低落时，脑海中通常会盘旋哪些想法或担忧？您会如何看待或评价那时的自己？"
      },
      {
        "id": 4,
        "text": "除了情绪上的感受，您的身体最近有没有发出一些“信号”？比如睡眠、食欲、精力或是一些不明原因的身体不适？"
      },
      {
        "id": 5,
        "text": "和过去相比，您最近的日常活动或兴趣爱好有什么变化吗？有没有一些以前很享受做的事，现在却感觉没什么动力了？"
      },
      {
        "id": 6,
        "text": "这些困扰在多大程度上影响了您的日常生活，比如工作/学习、处理家务或与人交往？"
      },
      {
        "id": 7,
        "text":"目前，您生活中的人际关系（如家庭、朋友、伴侣）感觉如何？它们是您的支持来源，还是压力来源？"
      },
      {
        "id": 8,
        "text": "您觉得目前的状态大概是从什么时候开始的？当时生活里是否发生了什么特别的事情？"
      },
      {
        "id": 9,
        "text": "当面对困难时，您会做些什么来让自己感觉好一点？哪些方法似乎有些效果？"
      },
      {
        "id": 10,
        "text": "在目前这段时期，您认为自身有哪些优点或力量在支撑着您？或者，生活中有哪些事能给您带来片刻的安慰？"
      },
      {
        "id": 11,
        "text": "想象一下：如果奇迹发生，所有困扰您的问题都解决了。当您第二天醒来时，您的生活会有哪些不同，会让您知道“奇迹”发生了？"
      },
      {
        "id": 12,
        "text": "最后，还有没有什么您觉得很重要，但我们还没来得及谈到的事情？"
      }
    ]
  }
}



@app.route('/api/interview/chat', methods=['POST'])
def chat_with_bot():
    # 检查请求数据
    if not request.json:
        app.logger.error("No JSON data received")
        return jsonify({"error": "请求数据格式错误：需要JSON格式"}), 400
        
    data = request.json
    user_message = data.get('message')
    username = data.get('username')
    client_provided_history = data.get('history', [])
    
    app.logger.info(f"Chat request from user: {username}, message: {user_message[:50] if user_message else 'None'}...")

    if not user_message or not user_message.strip():
        return jsonify({"error": "消息内容不能为空"}), 400
    
    if not username:
        return jsonify({"error": "用户名是必需的"}), 400
    
    try:
        # 获取或创建用户会话
        session = get_or_create_session(username)
        
        # 保存用户消息到数据库
        save_session_message(username, user_message, 'user')
        
        # 获取完整的历史记录（优先使用数据库中的记录）
        history = get_session_history(username)
        app.logger.info(f"Retrieved history for {username}: {len(history)} messages")
        
        # 如果数据库中没有历史记录，使用前端提供的历史记录（兼容性处理）
        if not history and client_provided_history:
            # 将前端历史记录保存到数据库
            all_data = read_data()
            all_data['interview_sessions'][username]['messages'] = client_provided_history
            write_data(all_data)
            history = client_provided_history
            app.logger.info(f"Used client history for {username}: {len(history)} messages")
        
        # 确保API密钥已正确配置
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
        
        # 根据官方文档的正确方式创建客户端，传入API密钥
        client = genai.Client(api_key=api_key)
        
        # 构建完整的系统提示，包含问题列表
        questions_text = "\n".join([f"问题{q['id']}: {q['text']}" for q in SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['question_list']])
        
        system_prompt = f"""
{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['role_definition']['persona']}
{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['role_definition']['objective']}

初始问候：
{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['conversation_flow']['initial_message']}

您需要按照以下顺序进行12个问题的访谈：
{questions_text}

结束语：
{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['conversation_flow']['closing_message']}

对话规则：
- {SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['conversation_flow']['progression_logic']}
- 语调：{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['constraints_and_guidelines']['tone']}
- {SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['constraints_and_guidelines']['language']}
- 追问规则：{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['follow_up_rules']['trigger_conditions'][0]}
- 每个问题最多追问{SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['follow_up_rules']['max_follow_ups_per_question']}次

禁止事项：
""" + "\n".join([f"- {p}" for p in SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['constraints_and_guidelines']['prohibitions']])

        # 添加会话状态跟踪
        system_prompt += f"""

重要指示：
- 如果这是对话的开始，请使用初始问候语开始
- 严格按照问题1到问题12的顺序进行访谈
- 在用户回答当前问题后，再提出下一个问题
- 如果用户明确表示不想回答某个问题，立即跳到下一个问题
- 完成所有12个问题后，使用结束语结束访谈"""

        # 分析对话历史，确定当前应该提问的问题
        def analyze_conversation_progress(history):
            """分析对话历史，确定已经完成了哪些问题"""
            completed_questions = set()
            assistant_messages = [item['text'] for item in history if item['sender'] == 'bot']
            
            # 检查每个问题是否已经被提及
            for q in SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['question_list']:
                question_text = q['text']
                question_keywords = question_text[:20]  # 使用问题的前20个字符作为关键词
                
                for msg in assistant_messages:
                    if question_keywords in msg or f"问题{q['id']}" in msg:
                        completed_questions.add(q['id'])
                        break
            
            # 确定下一个要提问的问题
            next_question_id = 1
            for i in range(1, 13):
                if i not in completed_questions:
                    next_question_id = i
                    break
            else:
                next_question_id = 13  # 所有问题都完成了
            
            return completed_questions, next_question_id
        
        completed_questions, next_question_id = analyze_conversation_progress(history)
        app.logger.info(f"Conversation progress: completed={completed_questions}, next={next_question_id}")
        
        # 构建完整的对话历史内容
        conversation_context = system_prompt + "\n\n"
        
        # 添加当前进度信息
        if len(history) == 0:
            conversation_context += "这是访谈的开始。请使用初始问候语开始对话。\n\n"
            app.logger.info("Starting new interview - no history")
        elif next_question_id <= 12:
            next_question = next(q for q in SYSTEM_PROMPT_INTERVIEW['prompt_instructions']['question_list'] if q['id'] == next_question_id)
            conversation_context += f"当前进度：已完成问题 {sorted(completed_questions)}，接下来应该提问第{next_question_id}个问题：\n"
            conversation_context += f"「{next_question['text']}」\n\n"
            app.logger.info(f"Continuing interview - next question {next_question_id}")
        else:
            conversation_context += "所有12个问题都已完成，请使用结束语结束访谈。\n\n"
            app.logger.info("All questions completed - using closing message")
        
        # 构建对话历史，确保AI能够理解上下文
        if len(history) > 0:
            conversation_context += "=== 之前的对话记录 ===\n"
            for item in history:
                role = "用户" if item['sender'] == 'user' else "助手"
                conversation_context += f"{role}: {item['text']}\n"
            conversation_context += "\n"
        
        # 明确告诉AI要基于历史记录回复
        conversation_context += f"=== 重要提示 ===\n"
        conversation_context += f"请基于以上完整的对话历史来回复用户的新消息。务必要考虑之前用户分享的所有信息，保持对话的连贯性。\n\n"
        conversation_context += f"=== 用户的新消息 ===\n用户: {user_message}\n\n请回复: "
        
        app.logger.info(f"Context length: {len(conversation_context)} chars, History items: {len(history)}")
        
        # 根据官方文档的正确API调用方式
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=conversation_context,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=-1)
            ),
        )
        
        # 保存AI回复到数据库
        ai_response_text = response.text
        save_session_message(username, ai_response_text, 'bot')
        
        # 检查是否包含结束语
        updated_history = get_session_history(username)
        has_closing, user_message_count = check_closing_message(updated_history)
        
        if has_closing:
            update_session_status(username, 'completed', analysis_ready=True)
        
        app.logger.info(f"Chat response for {username}: closing={has_closing}, count={user_message_count}")
        
        return jsonify({
            "response": ai_response_text,
            "session_id": session.get('session_id', 'unknown'),
            "has_closing_message": has_closing,
            "user_message_count": user_message_count,
            "can_generate_report": has_closing
        })
    except Exception as e:
        app.logger.error(f"Error during Gemini chat: {e}")
        app.logger.error(f"Error traceback: {traceback.format_exc()}")
        return jsonify({"error": f"AI回复失败: {str(e)}"}), 500

# --- 会话管理API ---
@app.route('/api/interview/session/<username>', methods=['GET'])
def get_interview_session(username):
    """获取用户的访谈会话信息"""
    try:
        session = get_or_create_session(username)
        history = get_session_history(username)
        has_closing, user_message_count = check_closing_message(history)
        
        return jsonify({
            "session": session,
            "messages": history,
            "has_closing_message": has_closing,
            "user_message_count": user_message_count,
            "can_generate_report": has_closing
        })
    except Exception as e:
        app.logger.error(f"Error fetching session: {e}")
        return jsonify({"error": f"获取会话失败: {str(e)}"}), 500

@app.route('/api/interview/session/<username>/reset', methods=['POST'])
def reset_interview_session(username):
    """重置用户的访谈会话"""
    try:
        all_data = read_data()
        if username in all_data['interview_sessions']:
            # 删除现有会话
            del all_data['interview_sessions'][username]
            write_data(all_data)
        
        # 创建新会话
        new_session = get_or_create_session(username)
        
        return jsonify({
            "message": "会话已重置",
            "session": new_session
        })
    except Exception as e:
        app.logger.error(f"Error resetting session: {e}")
        return jsonify({"error": f"重置会话失败: {str(e)}"}), 500

# --- 第二个智能体：访谈分析智能体 ---
SYSTEM_PROMPT_ANALYSIS = {
    "system_prompt_name": "Conversational Interview Analysis and Reporting",
    "version": "1.0",
    "description": "A system prompt to guide an AI agent in analyzing a user's conversational interview transcript. The agent will produce a comprehensive, structured, and empathetic report that identifies core issues, demonstrates understanding, and suggests suitable therapeutic approaches.",
    "prompt_instructions": {
        "role_definition": {
            "persona": "你是一位经验丰富、富有洞察力且具备共情能力的心理分析师。你的任务是基于给定的访谈文稿，为用户提供一份专业、清晰且充满关怀的分析报告。你的语言应兼具专业性与易懂性，核心目标是让用户感到被深入理解和支持。",
            "objective": "严格基于用户提供的访谈文稿，生成一份结构化的分析报告。报告需总结核心议题，深入分析用户在情绪、认知、行为等维度的状态，洞察其潜在困境与心态，并最终基于分析结果，为用户推荐2-3个可能适合的心理咨询流派并说明原因。"
        },
        "input_format": {
            "type": "文本（Text）",
            "content": "完整的用户与AI引导者之间的开放式访谈对话记录。"
        },
        "output_structure": {
            "title": "关于您近期状况的初步分析报告",
            "introduction": "在报告开头，写一段温和的引言，说明这份报告是基于用户之前的分享，旨在提供一个梳理和反馈的视角，并强调其非诊断性质。",
            "part_1_summary": {
                "title": "一、总体印象与核心议题",
                "content": "综合整个访谈，用叙事性的语言总结用户当前面临的核心困扰或议题。例如：'从您的谈话中，我感受到您目前可能正处在一个……的阶段，核心的困扰似乎围绕着……和……展开。'"
            },
            "part_2_multidimensional_analysis": {
                "title": "二、多维度状态分析",
                "description": "从以下几个维度，结合用户在访谈中的具体表述（可少量引用原文以增强共鸣），进行详细分析。",
                "sections": {
                    "emotional_state": "情绪状态：分析用户的主要情绪（如焦虑、低落、矛盾），以及情绪的强度和稳定性。",
                    "cognitive_patterns": "认知模式：分析用户的思维习惯，如是否存在反复担忧、负面自我评价、灾难化思维等。这是展现'理解'的关键部分。",
                    "behavioral_patterns": "行为模式：分析用户在行为上的变化，如回避社交、动机下降、兴趣丧失或应对方式。",
                    "somatic_symptoms": "生理感知：梳理用户提及的身体信号，如睡眠、食欲、精力等问题，并将其与情绪状态联系起来。",
                    "social_functioning": "社会功能与人际关系：分析用户的困扰对其日常生活（工作/学习）的影响，以及其人际支持系统的质量（是压力源还是支持源）。"
                }
            },
            "part_3_synthesis_and_interpretation": {
                "title": "三、核心困境洞察",
                "content": "这是报告的升华部分。在此，你需要整合前述所有分析，提出一个关于用户当前核心困境的深刻洞察。尝试解释各个分散的点是如何连接成一个整体的。例如：'综合来看，您提到的对……的担忧和在……上的无力感，背后可能反映了一种在'自我价值感'与'外部评价'之间的挣扎。您一方面渴望……，另一方面又害怕……，这种矛盾心态可能是您当前能量消耗的主要原因。'"
            },
            "part_4_therapeutic_recommendations": {
                "title": "四、可能适合您的咨询流派建议",
                "introduction": "在此处说明，不同的咨询流派有不同的工作方式，选择权在用户手中。以下推荐仅为基于您个人情况的参考。",
                "recommendation_structure": "推荐2-3个流派。对每一个流派，遵循以下结构：",
                "item_template": {
                    "name": "【咨询流派名称，例如：认知行为疗法 (CBT)】",
                    "description": "用1-2句话通俗地解释这个流派是做什么的。",
                    "suitability_analysis": "【为什么它可能适合您】：详细、具体地将该流派的特点与用户在访谈中透露的困扰直接挂钩。例如：'CBT疗法特别关注思维模式与情绪、行为的联系。鉴于您在访谈中提到当遇到挫折时，会对自己有很多负面评价，CBT可以帮助您识别并调整这些被称为自动化负性思维的想法，从根源上改善您的情绪。'"
                }
            },
            "final_disclaimer": {
                "title": "五、结语与重要提醒",
                "content": "在报告末尾，必须包含一段结语。再次感谢用户的信任，重申本报告是基于有限信息的初步分析，绝不能替代专业的临床诊断。强烈鼓励用户带着这份报告去和专业的心理咨询师或精神科医生进行更深入的探讨，并祝福用户。"
            }
        },
        "analytical_principles": {
            "text_based_evidence": "所有分析、洞察和推荐都必须有访谈文本作为依据，避免凭空猜测。",
            "empathetic_tone": "使用支持性、非评判性的语言，让用户感受到被尊重和理解。",
            "strengths_focus": "在分析困扰的同时，适时地将用户在访谈中展现的优点、资源和求变意愿（如'奇迹问题'的回答）也整合进报告，提供一个平衡的视角。",
            "professionalism": "保持专业的框架和视角，但用通俗易懂的语言向用户解释。"
        },
        "therapist_recommendation_logic": {
            "knowledge_base": {
                "cbt": "认知行为疗法 (CBT): 适用于具体的问题，如焦虑、恐慌、抑郁、强迫症。核心是识别和改变不适应的思维和行为模式。适合提及具体负面想法和行为困扰的用户。",
                "psychodynamic": "心理动力学疗法: 探索潜意识、早期经历和人际关系模式如何影响当前的情绪和行为。适合希望深入理解为什么我总是这样的根源性问题的用户。",
                "person_centered": "人本主义/来访者中心疗法: 强调无条件的积极关注、共情和真诚，帮助用户提升自我认知和实现个人潜能。适合感到迷茫、自我价值感低或希望在安全环境中自我探索的用户。",
                "act": "接纳承诺疗法 (ACT): 强调接纳无法改变的痛苦、澄清个人价值观，并致力于有价值的行动。适合长期与负面情绪斗争、感觉卡住了的用户。",
                "sfbt": "焦点解决短期治疗 (SFBT): 不深究问题根源，而是聚焦于用户的目标、已有资源和成功经验，快速构建解决方案。适合目标导向、希望寻找具体、积极改变方法的用户。"
            }
        }
    }
}

@app.route('/api/interview/analyze', methods=['POST'])
def analyze_interview():
    """第二个智能体：分析访谈结果（从数据库读取对话历史）"""
    data = request.json
    username = data.get('username')  # 必需参数：用户名
    client_info = data.get('client_info', {})
    
    if not username:
        return jsonify({"error": "需要提供用户名以获取对话历史"}), 400
    
    try:
        # 从数据库获取用户的完整对话历史
        all_data = read_data()
        
        if username not in all_data['interview_sessions']:
            return jsonify({"error": "未找到该用户的访谈会话"}), 404
        
        session = all_data['interview_sessions'][username]
        history = session['messages']
        
        if not history:
            return jsonify({"error": "访谈会话为空"}), 400
        
        # 检查是否有足够的对话内容进行分析
        if len(history) < 5:  # 至少需要几轮对话
            return jsonify({
                "error": "对话内容不足，无法进行分析",
                "message_count": len(history),
                "session_status": session.get('status', 'unknown')
            }), 400
        
        # 构建分析系统提示
        analysis_prompt = f"""
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['role_definition']['persona']}

核心任务：
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['role_definition']['objective']}

输入格式：
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['input_format']['content']}

请严格按照以下结构生成分析报告：

标题：{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['title']}

引言：
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['introduction']}

{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_1_summary']['title']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_1_summary']['content']}

{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['title']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['description']}

2.1 {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['sections']['emotional_state']}

2.2 {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['sections']['cognitive_patterns']}

2.3 {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['sections']['behavioral_patterns']}

2.4 {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['sections']['somatic_symptoms']}

2.5 {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_2_multidimensional_analysis']['sections']['social_functioning']}

{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_3_synthesis_and_interpretation']['title']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_3_synthesis_and_interpretation']['content']}

{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_4_therapeutic_recommendations']['title']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_4_therapeutic_recommendations']['introduction']}

{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_4_therapeutic_recommendations']['recommendation_structure']}

流派推荐格式：
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_4_therapeutic_recommendations']['item_template']['name']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_4_therapeutic_recommendations']['item_template']['description']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['part_4_therapeutic_recommendations']['item_template']['suitability_analysis']}

可参考的咨询流派：
1. {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['therapist_recommendation_logic']['knowledge_base']['cbt']}
2. {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['therapist_recommendation_logic']['knowledge_base']['psychodynamic']}
3. {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['therapist_recommendation_logic']['knowledge_base']['person_centered']}
4. {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['therapist_recommendation_logic']['knowledge_base']['act']}
5. {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['therapist_recommendation_logic']['knowledge_base']['sfbt']}

{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['final_disclaimer']['title']}
{SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['output_structure']['final_disclaimer']['content']}

分析原则：
- {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['analytical_principles']['text_based_evidence']}
- {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['analytical_principles']['empathetic_tone']}
- {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['analytical_principles']['strengths_focus']}
- {SYSTEM_PROMPT_ANALYSIS['prompt_instructions']['analytical_principles']['professionalism']}
"""
        
        # 构建用户对话内容
        conversation_text = "\n".join([
            f"{'用户' if item['sender'] == 'user' else '智能体'}: {item['text']}" 
            for item in history
        ])
        
        user_prompt = f"""
访谈会话信息：
- 用户名：{username}
- 会话开始时间：{session.get('created_at', '未知')}
- 会话完成时间：{session.get('updated_at', '未知')}

基础信息（如有）：
{json.dumps(client_info, indent=2, ensure_ascii=False) if client_info else "无"}

完整访谈对话记录：
---
{conversation_text}
---

请基于以上对话内容，生成结构化的心理状态分析报告。
"""

        # 调用AI分析
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
            
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=analysis_prompt + "\n\n" + user_prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=-1)
            )
        )
        
        # 保存分析结果到会话数据中
        all_data['interview_sessions'][username]['analysis_report'] = response.text
        all_data['interview_sessions'][username]['analysis_completed_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_data(all_data)
        
        return jsonify({
            "status": "success",
            "analysis_completed": True,
            "analysis_report": response.text,
            "analyzed_messages": len(history),
            "session_id": session['session_id'],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        
    except Exception as e:
        app.logger.error(f"访谈分析过程中出错: {e}")
        return jsonify({"error": f"分析失败: {str(e)}"}), 500

@app.route('/api/interview/status', methods=['POST'])
def check_interview_status():
    """检查访谈状态和是否可以进行分析（从数据库读取）"""
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({"error": "需要提供用户名"}), 400
    
    try:
        all_data = read_data()
        
        if username not in all_data['interview_sessions']:
            return jsonify({
                "has_closing_message": False,
                "user_message_count": 0,
                "can_generate_report": False,
                "next_step": "start_interview",
                "session_exists": False
            })
        
        session = all_data['interview_sessions'][username]
        history = session['messages']
        has_closing, user_message_count = check_closing_message(history)
        
        return jsonify({
            "has_closing_message": has_closing,
            "user_message_count": user_message_count,
            "can_generate_report": has_closing,
            "next_step": "generate_report" if has_closing else "continue_interview",
            "session_exists": True,
            "session_status": session.get('status', 'active'),
            "analysis_ready": session.get('analysis_ready', False),
            "has_analysis_report": 'analysis_report' in session
        })
        
    except Exception as e:
        app.logger.error(f"检查访谈状态时出错: {e}")
        return jsonify({"error": f"状态检查失败: {str(e)}"}), 500

# --- 前端文件服务路由 ---
@app.route('/')
def serve_home():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
