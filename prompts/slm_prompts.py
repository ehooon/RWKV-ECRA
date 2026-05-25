def build_slm_preview_prompt(chunk_str: str) -> str:
    return (
        f"User: 【任务目标】\n"
        f"你正在进行长文档的“侦察预读”。请阅读以下片段，用极其简练的语言（100字以内）回答：\n"
        f"1. 核心主题是什么？\n"
        f"2. 推测该文件的体裁和在全局中的作用？\n\n"
        f"原文片段：\n{chunk_str}\n\n" 
        f"Assistant: <think>\n</think>\n" 
    )

def build_slm_map_prompt(chunk_str: str, map_focus: str, detail_level: str) -> str:
    return (
        f"User: 【任务目标】你正在阅读局部片段。请全面且连贯地总结概括。\n"
        f"【总结侧重点】{map_focus}\n"
        f"【字数与细节要求】{detail_level}\n"
        f"【约束】客观提炼，绝对基于输入文本，严禁发散想象。有代码请概括功能。\n"
        f"片段：\n{chunk_str}\n\n"
        f"Assistant: <think>\n</think>\n" 
    )

def build_slm_extract_prompt(chunk_str: str, map_focus: str) -> str:
    return (
        f"User: 【任务目标】高精度事实提取。\n"
        f"【提取方向】{map_focus}\n"
        f"【绝对红线（极其重要）】：\n"
        f"1. 只能从下方的原文片段中提取信息！严禁动用你的内部知识库！\n"
        f"2. 严禁捏造虚假的人名（如张三李四）、年份、数据或不存在的对比。\n"
        f"3. 必须以精简的 Markdown 无序列表形式输出。如果没有发现关键事实，必须且只能回复“无”。绝对禁止编造。\n"
        f"片段：\n{chunk_str}\n\n"
        f"Assistant: <think>\n</think>\n"
    )

def build_slm_reduce_prompt(batch_text: str, reduce_rule: str, detail_level: str, current_step: int, total_steps: int) -> str:
    return (
        f"User: 【任务目标】处理多段落合并（当前执行第 {current_step}/{total_steps} 步）。\n"
        f"【合并准则】{reduce_rule}\n"
        f"【字数与细节要求】{detail_level}\n"
        f"【绝对红线】：优先保证信息的真实性和准确性。你是一个严谨的总结者，请严格基于提供的片段进行提炼压缩，绝不允许发散创作、续写或引入原文中不存在的观点。\n"
        f"片段：\n{batch_text}\n\n"
        f"Assistant: <think>\n</think>\n"
    )