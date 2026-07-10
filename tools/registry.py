# RWKV-ECRA/tools/registry.py
from typing import Callable, Dict, Any
from utils.token_tracker import current_task_id
from utils.task_manager import update_task_progress

class ToolRegistry:
    _tools: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(cls, name: str, phase: str, signature: str):
        def decorator(func: Callable):
            cls._tools[name] = {
                "func": func,
                "signature": signature,
                "phase": phase
            }
            return func
        return decorator

    @classmethod
    def get_interfaces_by_phase(cls, phase: str) -> str:
        """渐进式披露：向大模型展示当前阶段可用的高度抽象的接口卡片"""
        lines = [f"### 当前可用工具接口 (Phase: {phase})"]
        for name, meta in cls._tools.items():
            if meta["phase"] == phase or meta["phase"] == "ALL":
                lines.append(meta["signature"] + "\n")
        return "\n".join(lines)

    @classmethod
    def execute(cls, action: str, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        if action not in cls._tools:
            return f"错误: 工具库中未注册 '{action}'。"
        
        # ✨ 工具状态拦截探针：自动将任何工具的调用动作推送至前端状态栏
        tid = context.get("task_id") or current_task_id.get()
        if tid and tid != "UNKNOWN_TASK":
            update_task_progress(tid, f"[工具调度] 正在使用工具: {action} ...")
        
        merged_kwargs = {**context, **args}
        return cls._tools[action]["func"](**merged_kwargs)

@ToolRegistry.register(
    name="finish_task",
    phase="SYNTHESIS",
    signature="""[Tool] finish_task
- 功能: 认为用户所有的目标已经完全达成，退出系统。
- 参数: 无"""
)
def _finish_task(agent_state=None, **kwargs):
    if agent_state:
        agent_state.is_finished = True
        agent_state.final_result = "任务已达成，流程正常结束。"
    return "执行结束"