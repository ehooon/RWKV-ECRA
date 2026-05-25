import json
from clients.llm_client import LLMClient
from schemas.tools_definition import TOOL_SCHEMAS_POOL
from tools.registry import TOOL_REGISTRY
from utils.tracker import EventTracker
from config import TRACKING 
from prompts.llm_prompts import build_orchestrator_system_prompt, build_orchestrator_user_prompt

class Orchestrator:
    def __init__(self):
        self.llm = LLMClient()
        self.tracker = EventTracker(
            log_dir=TRACKING.get("log_dir", "./logs"), 
            enable=TRACKING.get("enable", True)
        )

    def _get_active_schemas(self):
        return TOOL_SCHEMAS_POOL

    def run(self, user_query: str) -> str:
        self.tracker.track("User_Input", input_data=user_query, output_data=None)
        
        step_count = 0
        MAX_STEPS = 20
        execution_history = []

        while step_count < MAX_STEPS:
            step_count += 1
            
            sys_prompt = build_orchestrator_system_prompt()
            user_prompt = build_orchestrator_user_prompt(user_query, execution_history)
            
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            message = self.llm.chat_completion(messages, tools=self._get_active_schemas())
            
            if not getattr(message, "tool_calls", None):
                content = message.content
                self.tracker.track("LLM_Final_Response", input_data=messages, output_data=content)
                return content

            tool_calls_dump = [{"name": tc.function.name, "args": tc.function.arguments} for tc in message.tool_calls]
            self.tracker.track("LLM_Tool_Decision", input_data=messages, output_data=tool_calls_dump)

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    execution_history.append(f"❌ 规划失败: {func_name} JSON 解析异常: {str(e)}")
                    continue
                
                if func_name in TOOL_REGISTRY:
                    try:
                        result = TOOL_REGISTRY[func_name](tracker=self.tracker, **args)
                        
                        # 🚨 优化核心 2：上下文重置！截断过长的返回值，防止爆显存
                        result_str = str(result)
                        if len(result_str) > 800:
                            result_str = result_str[:800] + "\n...(详情已转交底层黑板缓存引擎托管)..."

                        execution_history.append(f"✅ {func_name} 状态:\n{result_str}")
                    except Exception as e:
                        execution_history.append(f"❌ {func_name} 运行时崩溃: {str(e)}")
                else:
                    execution_history.append(f"❌ 未找到工具: {func_name}")
                
        return "运行超过最大步数限制，任务自动终止。"