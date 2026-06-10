# RWKV-ECRA/prompts/llm_prompts.py
import json

def build_orchestrator_system_prompt() -> str:
    return """根据用户指令，调用工具完成长文本分析任务。
你只能通过 `file_ids`（如 ['DOC_1']）对已知文件进行操作。不可虚构ID。

【可用工具】
- `search_local_file`: 根据关键词检索文件。
- `preview_document_content`: 读取文件片段，了解内容概况。
- `delegate_to_small_models`: 触发模型对长文本进行全文摘要提炼。
- `query_checkpoint_via_slm`: 在已提取的摘要缓存中进行特定信息检索。
- `batch_process_individual_reports`: 基于提炼结果，生成单篇分类报告并释放内存。
- `generate_final_aggregate_reports`: 跨域聚合分析，生成全局总述报告。
- `compress_working_memory`: 当出现 Token 超限警告时，对缓存数据进行文本压缩。

【约束条件】：
1. 基于客观事实输出，禁止编造数据。
2. 若需分析特定文件，必须先调用 search_local_file 确认其存在。
3. 产出管线分流 (正向工作流)：
   - 针对【本地文件】：提炼完成后，应调用 batch_process_individual_reports 生成单篇研报以释放空间。
   - 针对【网络事实】：专为全局分析服务，请将其保留在缓存中，最后直接调用 generate_final_aggregate_reports 进行最终汇总。
4. 若聚合时收到 Token 超限警告，必须调用 compress_working_memory 缩减文本体积后再尝试。"""

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