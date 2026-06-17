# RWKV-ECRA/prompts/llm_prompts.py
import json

# RWKV-ECRA/prompts/llm_prompts.py

def build_orchestrator_system_prompt() -> str:
    return """根据用户指令，调用工具完成长文本分析任务。
你只能通过 `file_ids`（如 ['DOC_1']）对挂载可见的文件进行操作。绝对不可虚构ID或凭空想象文件名！

【可用工具】
- `search_local_file`: 根据关键词检索文件。
- `preview_document_content`: 读取文件片段，了解内容概况。
- `verify_keyword_in_file`: 物理级全文检索，确认文件中是否真实包含某实体名词（用于验证关联性）。
- `delegate_to_small_models`: 触发模型对长文本进行全文摘要提炼。
- `query_checkpoint_via_slm`: 在已提取的摘要缓存中进行特定细节捞针。
- `execute_web_search`: 针对缺乏本地信息支撑的实体执行联网检索。
- `batch_process_individual_reports`: 归档单篇分类报告并释放内存。
- `generate_final_aggregate_reports`: 跨域聚合分析，生成全局总述报告。

【执行约束红线】：
1. 防强行关联幻觉：如果你试图推断 A实体（如某项目）与 B实体（如某技术）有关联，必须先调用 `verify_keyword_in_file` 在A的文件中搜索B的名字！如果返回出现 0 次，必须将该实体标为无关并放弃关联！
2. 产出管线分流 (正向工作流)：
   - 针对【本地文件】：提炼完成后，应调用 batch_process_individual_reports 释放空间。
   - 针对【网络事实】：不可再次调用提炼工具，请将其保留在缓存中直到最终汇总。"""

def build_orchestrator_user_prompt(context_text: str) -> str:
    return f"阅读以下环境状态，根据用户指令进行推演并选择工具。\n\n{context_text}"

def build_diagnostic_prompt(query: str, action: str, args: dict, last_error: str) -> tuple[str, str]:
    sys_prompt = "阅读任务目标和执行报错信息，判断执行停滞原因，并提供下一步处理建议。"
    content = (
        f"【任务目标】: {query}\n"
        f"【当前动作】: {action}\n"
        f"【调用参数】: {json.dumps(args, ensure_ascii=False)}\n"
        f"【系统报错】: {last_error}\n\n"
        f"请评估失败原因，说明下一步的具体建议。"
    )
    return sys_prompt, content