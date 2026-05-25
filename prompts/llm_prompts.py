def build_orchestrator_system_prompt() -> str:
    return """【系统指令】
当前任务流程：理解意图 -> 盘点资产 -> 试读画像 -> 制定策略下发 MapReduce -> 大模型融会贯通亲自撰写总报告并落盘。
【要求与红线】：
1. 试读和抽取细节的工作已经委托给小模型，你会收到它们返回的核心素材。
2. 严禁跳过试读和委托阶段直接盲猜文件内容。
3. 在最后出报告阶段，你必须将获取到的所有片段融会贯通，亲自撰写最终的 Markdown 长文报告，拒绝“拼接式”行文。最终报告绝不要包含类似“所有内容均来自模型”的免责废话。"""

def build_orchestrator_user_prompt(user_query: str, execution_history: list) -> str:
    prompt = f"【用户原始需求】\n{user_query}\n\n"
    
    if not execution_history:
        prompt += """【当前阶段：意图拆解与资源探测】
分析用户意图，并调用 `search_local_file` 获取文件列表。"""
        return prompt

    prompt += "【当前已执行的动作状态(历史回溯)】\n"
    history_str = ""
    for idx, log in enumerate(execution_history):
        history_str += f"- 步骤 {idx+1}: {log}\n"
    prompt += history_str + "\n"

    if "search_local_file" in history_str and "preview_document_content" not in history_str:
        prompt += "【当前阶段：抽样与画像构建】\n必须对上方找到的**每一个**文件调用 `preview_document_content` 工具。"

    elif "preview_document_content" in history_str and "delegate_to_small_models" not in history_str:
        prompt += """【当前阶段：全局策略分析与委托下发】
必须为**每个**文件调用 `delegate_to_small_models` 下发 MapReduce 任务。
工具会为你返回该文件的 1500 字精要素材，请你吸收并记忆这些素材，作为你最后写总报告的基础。"""

    elif "delegate_to_small_models" in history_str and "export_report_to_md" not in history_str:
        # 🚨 重点修改这里：增加极其严格的格式和内容过滤约束
        prompt += """【当前阶段：全局关联分析与最终大盘输出】
所有文件的提炼素材已经全部收集完毕。
请调用 `export_report_to_md` 工具。由于底层不再自动拼接，你需要在 `full_report_content` 参数中，亲自撰写一份完整、排版优美的 Markdown 格式最终研报。

请包含：
1. 宏观跨文件分析：深度比对各文件的共性或差异点。
2. 核心观点梳理：基于历史步骤中你获取到的各文件精要素材，用你严谨连贯的语言重新组织并深度总结。

🚨【绝对红线（严禁违反）】：
1. 报告必须纯粹是学术/技术干货！直接从正文的大标题（如 `# 核心报告`）开始写。
2. 绝对禁止在报告开头或结尾添加任何“报告生成时间”、“作者信息”、“前言”、“免责声明”、“结语”等无意义的边角料或元数据！
3. 杜绝所有类似“根据您的要求，我为您生成了以下报告”的废话，只输出报告本身。"""
    else:
        prompt += "【当前阶段：评估与完结】\n若已写盘完成，请直接回复：“报告已生成，任务圆满完成。”"

    return prompt