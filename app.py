# 安装必要的库: pip install Flask requests gunicorn
from flask import Flask, request, jsonify, send_from_directory, Response, make_response
import requests
import os
import json
import traceback
import logging

# 初始化和配置
app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
logging.basicConfig(level=logging.INFO)

# --- API密钥配置 ---
DEEPSEEK_API_KEY = "sk-44e1314da2d94b35b978f0fcd01ed26f"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- PROMPTS (内容保持不变) ---
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
	自我评价：反映个人能力在主观和客观的相符程度，也包括对自我理想意象的幻想（即理想的自我是什么样的）。思想和行动符合，我们的内在理想就会感到自我实现和自豪；否则就会产生内疚、失败和一无是处的感觉。
	1.2自尊管理：从打击中恢复原状的能力。
	包括自尊的脆弱性（水平高低、稳定性）、应对挫败自尊的方式（自恋自大或自我挫败/受虐，而更健康的方式是直面问题 而不是困在自我中）、利用他人调节自尊。自尊是对自己的尊敬和或欣赏，自尊问题使我们变得无法承受情感和焦虑，无法现实评价能力和局限，无法控制我们的冲动，无法放松，等等。
	此外，自我评价的问题也会导致自我知觉的扭曲和自尊管理的困难。有的人会高估自己的能力(夸大)，而有的人会低估自己的能力（抑郁），又或者理想化他人。（嫉妒具有攻击性，而羡慕具有靠近的倾向）
	2.人际关系功能：保持稳定、信任、亲密关系的能力
	关键：1.关系中对自己和对方的信任感、2.感知度：既好又坏的立体性、独特个性的独立性（明白他人的思想和感受与自己不同，心智化能力）、过去到现在与未来可能变化的完整性。3.安全感：抵抗面对分离、分歧、消极情绪。4.亲密性（边界情况）；5.相互依存度：合适的依存是既给予也享受的。
	 
	除此以外仍然关键的要素有：共情能力、来访意识与无意识对他人的期待和对关系的幻想。 
	两种关系问题：无意识投射与幻想、缺乏社交功能。前者揭露，后者支持
	在成长的过程中，小时候和重要他人的互动为他们整个人生中与人互动的方式打下了不可磨灭的烙印。被爱护和照料得很好的人学会了期待从他人那里也得到这些，而被虐待或忽视的人学会了预期被虐待。即使人们意识不到这些内化的无意识的关系模式和幻想，也依然影响着他们的每一次行动。
	这些幻想之所以残留在意识之外，是因为它们引发了羞愧、焦虑或其他令人不舒服的强烈情感。如果他们意识不到这些无意识的需求，人们就无法选择能和他们建立成熟满意的人际关系的他人。甚至意识层面的需求和无意识的需求有所冲突。
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

# --- 核心API调用函数 ---
def call_api_sync(system_prompt, user_prompt, model='deepseek-chat'):
    """同步调用API，用于一次性获取完整结果。"""
    app.logger.info(f"[SYNC_CALL_START] model={model}")
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], 'stream': False}
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content')
        if content is None: raise ValueError(f"AI response did not contain expected content: {data}")
        app.logger.info("[SYNC_CALL_SUCCESS]")
        return content
    except Exception as e:
        app.logger.error(f"[SYNC_CALL_ERROR] {e}")
        traceback.print_exc()
        raise

#def call_api_stream(system_prompt, user_prompt, model='deepseek-chat'):
   # """流式调用API，用于实现打字机效果。"""
    #app.logger.info(f"[STREAM_CALL_START] model={model}")
    #headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'}
    #payload = {'model': model, 'messages': [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], 'stream': True}
    #try:
        #proxy_response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, stream=True, timeout=300)
        #proxy_response.raise_for_status()
        #def generate():
            #for chunk in proxy_response.iter_content(chunk_size=8192):
                #yield chunk
        #return Response(generate(), content_type=proxy_response.headers.get('Content-Type'))
    #except requests.exceptions.RequestException as e:
        #app.logger.error(f"[STREAM_CALL_ERROR] {e}")
        #return jsonify({"error": f"调用外部API失败: {e}"}), 502

# --- 路由定义 ---
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze_files():
    app.logger.info("[ROUTE_HIT] /api/analyze")
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

@app.route('/api/cbt-stream', methods=['POST'])
def cbt_stream_proxy():
    app.logger.info("[ROUTE_HIT] /api/cbt-stream")
    data = request.json
    system_prompt = data.get('systemPrompt')
    user_prompt = data.get('userPrompt')
    model = data.get('model', 'deepseek-chat')
    if not user_prompt or not system_prompt: return jsonify({"error": "缺少必要的参数"}), 400
    return call_api_stream(system_prompt, user_prompt, model=model)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
