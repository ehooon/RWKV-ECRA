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

【🌟 核心架构：双轨执行机制】
你需要首先判定用户的指令属于哪种模式，并严格按对应的模式执行：

▶ 模式 A：【全局泛读 / 无特定实体】(BROAD_ANALYSIS)
- 触发场景：指令类似“读一下本地文章”、“总结所有文件”、“提取目录核心数据”、“生成总览”等，没有要求调查特定对象或特定逻辑。
- 执行策略：
  1. 绝对禁止“没事找事”！不要去提取任何实体，跳过实体审计（实体字典严格置空）。
  2. 不执行防诱导与领域隔离，包容沙盒中所有的文件内容，不论它们跨度多大。
  3. 缺口提取 (missing_information)：从环境状态中找出 [未读] 状态的本地文件，明确写出“需要提炼未读文件: DOC_1, DOC_2...”；若无未读文件，填“无，进入汇总生成报告”。

▶ 模式 B：【定向深研 / 有特定实体】(DEEP_RESEARCH)
- 触发场景：指令包含具体的专有名词、人物、机构，或要求验证特定逻辑。
- 执行策略：
  1. 启动严格的防诱导与跨界隔离防御。
  2. 提取并查证所有实体状态：[待检索]（无信息需搜索）、[确认相关]（有明确业务关联）、[确认无关]（存在巨大跨界，立刻判定无关并剔除）。
  3. 缺口提取 (missing_information)：指明具体需要优先调查的 1 个对象。每次只聚焦一个。

输出JSON格式：
{{
  "intent_mode": "BROAD_ANALYSIS 或是 DEEP_RESEARCH",
  "sandbox_evaluation": "针对本地文件的评估，若无则为空",
  "entity_audit": {{
    // ⚠️ 若为 BROAD_ANALYSIS，必须为空字典 {{}}！
    // ⚠️ 若为 DEEP_RESEARCH，输出 "实体名": "待检索 / 确认相关 / 确认无关"
  }},
  "refined_query": "当前有效脱水目标（若是泛读模式，保持原意即可；深研模式剔除无关项）",
  "missing_information": "指明下一步缺口（泛读填'需要提炼未读文件: DOC_X'，深研填'搜索XX身份'等）",
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