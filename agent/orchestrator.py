import json
import re
from clients.llm_client import LLMClient
from schemas.tools_definition import TOOL_SCHEMAS_POOL
from tools.registry import TOOL_REGISTRY
from utils.tracker import EventTracker
from config import TRACKING 
from prompts.llm_prompts import (
    build_orchestrator_system_prompt, 
    build_orchestrator_user_prompt,
    build_isolated_check_prompt
)

def robust_json_parse(json_str: str) -> dict:
    """🛠️ 高强度 JSON 容错解析器：应对模型生成参数时的各种幺蛾子"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # 剔除 Markdown 格式干扰
    clean_str = re.sub(r'^```(?:json)?|```$', '', json_str.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(clean_str)
    except json.JSONDecodeError:
        pass
        
    # 修复常见的尾部逗号错误
    clean_str = re.sub(r",\s*}", "}", clean_str)
    clean_str = re.sub(r",\s*\]", "]", clean_str)
    try:
        return json.loads(clean_str)
    except json.JSONDecodeError:
        pass

    # 暴力提取最外层的 {}
    match = re.search(r'\{.*\}', clean_str, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
            
    raise ValueError(f"无法解析的 JSON 字符串 (已尝试多重退避修复): {json_str[:100]}...")


class Orchestrator:
    def __init__(self):
        self.llm = LLMClient()
        self.tracker = EventTracker(
            log_dir=TRACKING.get("log_dir", "./logs"), 
            enable=TRACKING.get("enable", True)
        )

    def _get_active_schemas(self):
        return TOOL_SCHEMAS_POOL

    def _run_isolated_check(self, func_name: str, result_str: str) -> tuple[bool, str]:
        """
        🕵️ 独立沙盒审查机制：专门阻断小模型产生幻觉或乱码导致脏数据污染主脑上下文。
        返回：(是否通过审核, 审核意见)
        """
        # 只对容易产生大段文本幻觉的节点进行审查
        if func_name not in ["preview_document_content", "delegate_to_small_models"]:
            return True, "PASS"
            
        sys_prompt = "你是一个独立的无责审核模块。请根据指令客观评估其他模型的输出质量。"
        user_prompt = build_isolated_check_prompt(func_name, result_str)
        
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # 开启纯对话模式，不传入 tools 参数，保证上下文绝对隔离
            response = self.llm.chat_completion(messages)
            check_result = response.content.strip()
            
            self.tracker.track("Isolated_Check", input_data={"func": func_name, "content": result_str[:200]}, output_data=check_result)
            
            if check_result.upper().startswith("FAIL"):
                return False, check_result
            return True, "PASS"
        except Exception as e:
            # 如果审核网关自己请求失败，默认放行，防止系统卡死
            return True, f"Check bypassed due to internal error: {str(e)}"

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
            
            # 退出条件：主模型没有再发起工具调用
            if not getattr(message, "tool_calls", None):
                content = message.content
                self.tracker.track("LLM_Final_Response", input_data=messages, output_data=content)
                return content

            tool_calls_dump = [{"name": tc.function.name, "args": tc.function.arguments} for tc in message.tool_calls]
            self.tracker.track("LLM_Tool_Decision", input_data=messages, output_data=tool_calls_dump)

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                
                # 🚨 应用强鲁棒性的 JSON 解析
                try:
                    args = robust_json_parse(tool_call.function.arguments)
                except ValueError as e:
                    execution_history.append(f"❌ 规划失败: {func_name} 的参数格式错误。请保持标准 JSON 格式，且勿在外部包裹 Markdown 代码块标签。报错详情: {str(e)}")
                    continue
                
                if func_name in TOOL_REGISTRY:
                    try:
                        result = TOOL_REGISTRY[func_name](tracker=self.tracker, **args)
                        result_str = str(result)
                        
                        # 🚨 触发上下文完全隔离的“无责审查”拦截器
                        is_pass, check_msg = self._run_isolated_check(func_name, result_str)
                        
                        if not is_pass:
                            # 审核不通过，记录到主脑历史中，主脑会自动决定如何重试或跳过
                            execution_history.append(f"⚠️ 工具 {func_name} 已执行，但结果被安全网关判定为不可用被拦截。原因: {check_msg}")
                            continue

                        # 🚨 审核通过后，为了防御爆显存进行截断
                        if len(result_str) > 1500:
                            result_str = result_str[:1500] + "\n...(详情已存入底层缓存，请基于此缩略素材进行后续规划)..."

                        execution_history.append(f"✅ {func_name} 执行成功:\n{result_str}")
                        
                    except Exception as e:
                        execution_history.append(f"❌ {func_name} 运行时异常: {str(e)}")
                else:
                    execution_history.append(f"❌ 未找到对应工具: {func_name}")
                
        return "⚠️ 运行超过最大步数限制 (20步)，任务被迫终止。"