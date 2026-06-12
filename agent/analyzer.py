# RWKV-ECRA/agent/analyzer.py
import json
import re
from datetime import datetime
from clients.llm_client import LLMClient

class Analyzer:
    def __init__(self):
        self.llm = LLMClient()
        
    def analyze_intent_and_phase(self, user_query: str, env_context: str) -> dict:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        sys_prompt = f"""系统时间：{current_time}
任务：分析用户的初始意图，并基于已挂载的上下文输出状态与行动方向。

【核心架构：双轨执行机制】
你需要首先判定用户的指令属于哪种模式，并严格按对应的模式执行：

▶ 模式 A：【全局泛读 / 无特定实体】(BROAD_ANALYSIS)
- 触发场景：没有要求调查特定对象或特定逻辑。
- 执行策略：不执行实体审计。针对未知的本地工作区文件，应当先进入 DISCOVERY 阶段调用 preview 进行试读。注意：本地工作区中可能包含与本次任务完全无关的干扰文件，你需要根据试读结果，决定是剔除它，还是进入 EXTRACTION 阶段提炼其全文。

▶ 模式 B：【定向深研 / 有特定实体】(DEEP_RESEARCH)
- 触发场景：指令包含具体的专有名词、人物、机构，或要求验证特定逻辑。
- 执行策略：启动严格的防诱导与跨界隔离防御。提取并查证所有实体状态。

【视觉与防脑补绝对红线】
1. 你目前能感知和操作的，只有当前明确列在“环境状态”中的本地工作区文件。绝对不要凭空虚构或引入未列出的文件！
2. 本地工作区的文件之间可能是完全平行且毫无关联的，绝对不要在没有原文依据的情况下强行脑补它们之间的关联。

输出JSON格式：
{{
  "intent_mode": "BROAD_ANALYSIS 或是 DEEP_RESEARCH",
  "sandbox_evaluation": "针对本地工作区文件的评估，若无则为空",
  "entity_audit": {{
    // 若为 BROAD_ANALYSIS，必须为空字典 {{}}！
    // 若为 DEEP_RESEARCH，输出 "实体名": "待检索 / 确认相关 / 确认无关"
  }},
  "abandoned_file_ids": [], // 如果你在阅读试读情报后，发现某文件与目标【毫无关联（属于纯垃圾干扰项）】，填入此数组彻底抛弃！如果是有效文件（哪怕它与其他文件完全无关），也应留空予以保留。
  "refined_query": "当前有效脱水目标（若是泛读模式，保持原意即可；深研模式剔除无关项）",
  "missing_information": "指明下一步缺口（需要试读哪些文件，或需要全文提炼哪些文件）",
  "next_phase": "DISCOVERY|EXTRACTION|SYNTHESIS"
}}"""
        
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"总体目标: {user_query}\n当前环境状态:\n{env_context}"}
        ]
        
        try:
            resp = self.llm.client.chat.completions.create(
                model=self.llm.model, messages=messages, temperature=0.1
            ).choices[0].message.content
            
            match = re.search(r'\{.*\}', resp, re.DOTALL)
            clean_json = match.group(0) if match else resp
            return json.loads(clean_json)
        except Exception as e:
            return {
                "intent_mode": "BROAD_ANALYSIS",
                "sandbox_evaluation": "",
                "entity_audit": {},
                "refined_query": user_query,
                "missing_information": "解析异常，请求对未知文件进行提取或检索", 
                "next_phase": "DISCOVERY"
            }