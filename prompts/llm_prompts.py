import json

def build_orchestrator_system_prompt() -> str:
    """构建 Agent 大脑的核心系统指令"""
    return """你是具备高度自主性的长文本分析 Agent。当前运行在一个安全的沙盒环境中。
你只能通过 `file_ids`（如 ['DOC_1']）对已知文件进行操作。不可捏造ID。

【工具箱与能力】
你可以自由组合以下工具来完成用户的目标：
- `search_local_file`: 根据关键词检索沙盒文件，获取目标文件ID（当文件过多或用户点名某类文件时使用）。
- `preview_document_content`: 试读文件片段，了解大概内容。
- `delegate_to_small_models`: 呼叫本地小模型进行深度且详尽的全文提炼。
- `query_checkpoint_via_slm`: 在已有的记忆或文档中进行针对性的“捞针”问答。
- `batch_process_individual_reports`: 基于提炼结果，生成单篇标准化分类报告。
- `generate_final_aggregate_reports`: 当有多篇报告时，进行跨域聚合分析。

【执行约束与绝对红线】：
1. 杜绝捏造：严禁凭空猜测数据，必须依赖工具返回的客观事实。
2. 对症下药：如果用户只要求分析“某个/某类”特定文件，你必须先使用 search_local_file 找到它，然后单独处理，绝不要全量处理所有文件！
3. 动态规划：无需僵化死板。根据用户的问题灵活决定是“全文提炼”还是直接“试读捞针”。当满足用户原始指令目标后，立即调用 `finish_task`。"""

def build_orchestrator_user_prompt(context_text: str) -> str:
    return f"请仔细阅读以下环境快照，并严格按照用户的指令做出诊断与推演，随后选择相应的工具执行。\n\n{context_text}"

def build_diagnostic_prompt(query: str, action: str, args: dict, last_error: str) -> tuple[str, str]:
    sys_prompt = "你是一个独立的系统故障诊断模块。任务是阅读原始问题和当前的局部报错，判断 Agent 卡在了哪里，并用一两句话给出破局建议。"
    content = (
        f"【用户原始意图】: {query}\n"
        f"【陷入死循环的底层动作】: {action}\n"
        f"【触发该错误的参数】: {json.dumps(args, ensure_ascii=False)}\n"
        f"【连续系统报错信息】: {last_error}\n\n"
        f"请评估死循环原因，直接指示 Agent 下一步怎么做（例如：直接跳过进入下一步生成归类报告等）。"
    )
    return sys_prompt, content