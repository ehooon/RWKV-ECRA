# RWKV-ECRA/agent/planner.py
import json
import re
from clients.llm_client import LLMClient
from tools.registry import ToolRegistry

class Planner:
    def __init__(self):
        self.llm = LLMClient()
        
    def plan_next_action(self, user_query: str, analysis_result: dict, env_context: str, phase: str) -> dict:
        tool_interfaces = ToolRegistry.get_interfaces_by_phase(phase)
        active_query = analysis_result.get('refined_query', user_query)
        missing_info = analysis_result.get('missing_information', '无')
        
        sys_prompt = f"""任务：基于缺口生成工具调用的 JSON 参数。

[环境目标]
- 目标：{active_query}
- 缺口：{missing_info}

{tool_interfaces}

[执行约束]
1. 执行 execute_web_search 时，提取缺口中的核心实体，剥离无关上下文。
2. 执行 delegate_to_small_models 时，必须从环境状态中提取出准确的 file_ids（如 ["DOC_1"]）。

[示例]
缺口: "需要提炼未读文件: DOC_1, DOC_2"
-> {{"action": "delegate_to_small_models", "args": {{"file_ids": ["DOC_1", "DOC_2"]}}}}

缺口: "调查 Hongkong Doll 是否对 ETH 产生影响"
-> {{"action": "execute_web_search", "args": {{"query": "Hongkong Doll 真实身份 履历"}}}}

必须只输出 JSON："""
        
        messages = [
            {"role": "system", "content": sys_prompt},
            # 🔴 核心修复：把 env_context 传给 Planner，让它知道当前有哪些 DOC 可以被提取！
            {"role": "user", "content": f"当前环境状态：\n{env_context}\n\n请针对核心缺口，直接输出 JSON 格式的工具规划。"}
        ]
        
        try:
            llm_response = self.llm.chat_completion(messages).content
            
            print(f"[大模型规划原始输出]:\n{llm_response.strip()}")

            match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            clean_json = match.group(0) if match else llm_response
            
            plan_data = json.loads(clean_json)
            
            return {
                "action": plan_data.get("action", "none"),
                "args": plan_data.get("args", {})
            }
        except Exception as e:
            print(f"[JSON 解析失败] 大模型返回不合法: {llm_response}")
            return {
                "action": "none",
                "args": {}
            }