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
        
        sys_prompt = f"""基于当前缺口生成工具调用的 JSON 参数。

目标：{active_query}
缺口：{missing_info}

{tool_interfaces}

约束：
1. execute_web_search：query 必须是极简短关键词，禁止长句。
2. verify_keyword_in_file：必须将长实体拆分为简短的核心词组放入 keywords 数组。
3. 必须且只能输出单个 JSON 对象，格式严格如下：
{{"action": "工具名称", "args": {{"参数1": "值1"}}}}"""
        
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"当前环境状态：\n{env_context}\n\n请直接输出 JSON 工具规划。"}
        ]
        
        llm_response = self.llm.chat_completion(messages).content
        
        print(f"[大模型规划原始输出]:\n{llm_response.strip()}")

        match_dict = re.search(r'\{.*\}', llm_response, re.DOTALL)
        match_list = re.search(r'\[.*\]', llm_response, re.DOTALL)
        
        if match_dict:
            clean_json = match_dict.group(0)
        elif match_list:
            clean_json = match_list.group(0)
        else:
            clean_json = llm_response
            
        # 这里去除了 try...except，解析错误直接向外抛出供主流程捕获
        plan_data = json.loads(clean_json)
        
        if isinstance(plan_data, list) and len(plan_data) > 0:
            plan_data = plan_data[0]
        if not isinstance(plan_data, dict):
            plan_data = {}
        
        action = plan_data.get("action") or plan_data.get("tool_name") or plan_data.get("name") or plan_data.get("tool") or "none"
        args = plan_data.get("args") or plan_data.get("parameters") or plan_data.get("arguments") or {}
        
        return {
            "action": action,
            "args": args
        }