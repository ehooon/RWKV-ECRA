# RWKV-ECRA/agent/analyzer.py
import json
import re
from clients.llm_client import LLMClient

class Analyzer:
    def __init__(self):
        self.llm = LLMClient()
        
    def analyze_intent_and_phase(self, user_query: str, env_context: str) -> dict:
        sys_prompt = """你是一个任务状态分析师。只负责分析，不负责执行。
基于用户原始目标和当前沙盒环境，判断下一步该进入什么阶段。

可选阶段严格限定为以下3个：
- DISCOVERY: 还需要找文件，或者对文件内容一无所知需要试读。
- EXTRACTION: 已经锁定目标文件，需要对其进行全文提炼或捞针（记忆区目前没有该文件的 Summary）。
- SYNTHESIS: 记忆区已存在相关提炼结果，可以开始归类、写报告，或目标已全部完成。

请返回JSON，格式如下：
{"missing_information": "推演当前缺什么信息", "next_phase": "上面3个阶段选其一"}"""
        
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"【用户目标】: {user_query}\n\n【环境快照】:\n{env_context}"}
        ]
        
        try:
            resp = self.llm.client.chat.completions.create(
                model=self.llm.model, messages=messages, temperature=0.1
            ).choices[0].message.content
            
            match = re.search(r'\{.*\}', resp, re.DOTALL)
            clean_json = match.group(0) if match else resp
            return json.loads(clean_json)
        except Exception as e:
            return {"missing_information": f"解析异常: {e}", "next_phase": "DISCOVERY"}