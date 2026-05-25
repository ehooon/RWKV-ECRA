def build_orchestrator_system_prompt() -> str:
    return """【系统任务与目标】
当前任务是响应用户需求，合理调用给定工具对本地文档进行深度分析，并最终基于提取到的素材生成高质量的综合研报。

【标准作业程序 (SOP)】
系统需根据历史执行状态，自主推演并决定当前应执行的步骤。标准的逻辑链路如下：
1. 意图拆解与资产盘点：调用 `search_local_file` 获取目标文件列表。
2. 全局抽样画像：对探测到的所有文件，逐一调用 `preview_document_content` 试读探测。
3. 深度逻辑与事实提取：为所有文件调用 `delegate_to_small_models` 下发 MapReduce 任务，获取详尽的摘要素材。
4. 终盘生成与落盘：所有文件的核心素材收集完毕后，调用 `export_report_to_md` 撰写总报告并保存。

【执行约束与绝对红线】：
1. 基于状态推演：必须严格根据“历史回溯状态”评估当前进度，并决定下一步需调用的工具。如单次无法处理所有文件，可分步调用。
2. 杜绝捏造：严禁在未调用工具获取文件内容的情况下，凭空猜测或编造文件数据。
3. 纯净输出格式：在终盘调用 `export_report_to_md` 时，必须直接输出纯粹的 Markdown 报告正文。绝对禁止在内容首尾添加“以下是为您生成的报告”、“报告生成时间”、“免责声明”、“结语”等任何对话性废话或无意义元数据。"""

def build_orchestrator_user_prompt(user_query: str, execution_history: list) -> str:
    prompt = f"【用户原始需求】\n{user_query}\n\n"
    
    if not execution_history:
        prompt += "【当前执行状态】\n任务刚刚启动。请分析意图，并调用检索工具获取工作区资产情况，开始你的自主规划。"
        return prompt

    prompt += "【当前已执行的动作状态(历史回溯)】\n"
    for idx, log in enumerate(execution_history):
        prompt += f"- 步骤 {idx+1}: {log}\n"
    
    prompt += """
【下一步规划指引】
请仔细阅读上方的“历史回溯”，并进行推演：
1. 有哪些文件还没有完成 preview (画像抽样)？
2. 有哪些文件还没有被 delegate (下发小模型深度提炼)？
3. 是否所有文件的精要素材都已经搜集完毕，可以出最终报告了？

请自主决定调用相应的工具。如果所有步骤已经完成且文件已经由你亲自导出，请不要调用工具，直接回复文本告知任务圆满完成。
"""
    return prompt

def build_isolated_check_prompt(func_name: str, result_str: str) -> str:
    return f"""【任务说明】
你是一个独立的无责审核模块。以下内容是由另一个辅助模型/底层系统在执行 `{func_name}` 后刚刚生成的返回结果。
该数据不由你负责产生，你只需客观、冷酷地判断其是否“基本可用”。

【评估标准】
请检查该结果是否存在以下致命缺陷：严重乱码、无限复读死循环、完全偏离主题、或者明显的底层崩溃报错信息。
1. 如果存在上述致命问题，请回复：FAIL: [简要说明具体原因]
2. 如果内容基本正常（允许存在被强行截断的情况，允许内容不够完美），请直接且仅回复：PASS

【另一个辅助模型/系统返回的数据】：
{result_str}
"""