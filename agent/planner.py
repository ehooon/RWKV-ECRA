# RWKV-ECRA/agent/planner.py
import json
from clients.llm_client import LLMClient
from schemas.progressive_tools import TOOL_GROUPS

class Planner:
    def __init__(self):
        self.llm = LLMClient()
        
    def plan_next_action(self, user_query: str, analysis_result: dict, env_context: str, phase: str) -> dict:
        available_tools = TOOL_GROUPS.get(phase, TOOL_GROUPS["DISCOVERY"])
        
        sys_prompt = f"""你是执行规划师。上游分析师已定位当前阶段为：【{phase}】。
建议：{analysis_result.get('missing_information', '无')}
请结合用户目标，从我提供的 tools 工具中强制选择一个最合适的工具，并输出参数。
注意：操作文件必须使用虚拟ID（如 DOC_1）。"""
        
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"目标:{user_query}\n当前沙盒:\n{env_context}"}
        ]
        
        resp = self.llm.client.chat.completions.create(
            model=self.llm.model,
            messages=messages,
            tools=available_tools,
            tool_choice="required",
            temperature=0.1
        ).choices[0].message
        
        if not getattr(resp, "tool_calls", None):
            raise ValueError("大模型拒绝调用工具")
            
        tool_call = resp.tool_calls[0]
        return {
            "action": tool_call.function.name,
            "args": json.loads(tool_call.function.arguments)
        }