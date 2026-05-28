def build_slm_preview_prompt(chunk_str: str) -> str:
    return (
        f"User: 【任务目标】\n"
        f"你正在进行长文档的“侦察预读”。请阅读以下片段，用极其简练的语言（100字以内）回答：\n"
        f"1. 核心主题是什么？\n"
        f"2. 推测该文件的体裁和在全局中的作用？\n"
        f"若片段为目录或无意义字符，仅回复“无实质内容，无法推断”。\n\n"
        f"原文片段：\n{chunk_str}\n\n" 
        f"Assistant: <think>\n</think>" 
    )

def build_slm_sequential_summary_prompt(chunk_str: str, current_idx: int, total_chunks: int, focus: str, detail_level: str) -> str:
    return (
        f"User: 【任务目标】作为专业审查员，客观分析当前连续文本切片（第 {current_idx}/{total_chunks} 部分）【做了什么】，并提取【核心事实】。\n"
        f"【关注方向】{focus}\n"
        f"【详略程度】{detail_level}\n"
        f"【绝对红线（极其重要）】：\n"
        f"1. 核心任务是【保持原意压缩】，必须严格保留原文中的客观事实性内容（具体指标、数据、核心结论），切勿遗漏。\n" # 👈 新增
        f"2. 严禁翻译原文！严禁发散扩写！严禁解释发挥！\n"
        f"3. 严禁写“首先”、“其次”、“综上所述”等废话文章结构。\n"
        f"4. 请严格使用精简的 Markdown 无序列表（- ）进行输出。列表中只需包含客观动作和具体事实。\n"
        f"5. 如果该片段为纯废话或无实质内容，必须且只能回复“无”。\n\n"
        f"原文片段：\n{chunk_str}\n\n"
        f"Assistant: <think>\n</think>" 
    )

def build_slm_reduce_prompt(batch_text: str, reduce_rule: str, detail_level: str, current_step: int, total_steps: int) -> str:
    return (
        f"User: 【任务目标】处理多段落要点合并（当前执行 Reduce 第 {current_step}/{total_steps} 步）。\n"
        f"【合并准则】{reduce_rule}\n"
        f"【字数与细节要求】{detail_level}\n"
        f"【绝对红线】：\n"
        f"1. 核心任务是【保持原意压缩】，你接收到的是按原文顺序排列的各段落事实要点，请梳理并合并同类项。\n" # 👈 修改
        f"2. 优先保证信息的真实性，严格保留原文核心逻辑和实验数据，严禁自我创作。\n" # 👈 修改
        f"3. 保持高度精简的无序列表格式，绝对拒绝生成“综上所述”、“总之”等总结性废话。\n\n"
        f"顺序要点片段：\n{batch_text}\n\n"
        f"Assistant: <think>\n</think>"
    )

def build_slm_query_checkpoint_prompt(chunk_str: str, query: str) -> str:
    return (
        f"User: 【任务目标】客观严谨的资料检索提取。\n"
        f"【查询需求】{query}\n"
        f"【约束条件】：\n"
        f"1. 仔细比对查询需求与切片内容。\n"
        f"2. 若包含所需信息，请详细提取整理。\n"
        f"3. 若完全不包含所需信息，仅回复“未找到”。严禁编造答案。\n\n"
        f"原文片段：\n{chunk_str}\n\n"
        f"Assistant: <think>\n</think>"
    )