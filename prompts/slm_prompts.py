# RWKV-ECRA/prompts/slm_prompts.py
import re

def _wash_slm_input(text: str) -> str:
    """洗稿过滤：强制把输入原文的所有多余换行压平，绝不给原文 \n\n 干扰截断的机会"""
    if not text:
        return ""
    return re.sub(r'\n{2,}', '\n', text).strip()

def build_slm_preview_prompt(chunk_str: str) -> str:
    clean_chunk = _wash_slm_input(chunk_str)
    return (
        f"User: 概括文本核心主题与类型。\n"
        f"文本：\n{clean_chunk}\n\n" 
        f"Assistant: <think>\n</think>" 
    )

def build_slm_sequential_summary_prompt(chunk_str: str, current_idx: int, total_chunks: int, focus: str, is_english: bool = False) -> str:
    clean_chunk = _wash_slm_input(chunk_str)
    if is_english:
        return (
            # 直接透传 config 中的 focus，仅追加防截断后缀
            f"User: {focus}\n"
            f"Text:\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>"
        )
    else:
        return (
            # 直接透传 config 中的 focus，仅追加防截断后缀
            f"User: {focus}\n"
            f"文本：\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>" 
        )

def build_slm_reduce_prompt(batch_text: str, reduce_rule: str, current_step: int, total_steps: int, is_english: bool = False) -> str:
    clean_batch = _wash_slm_input(batch_text)
    if is_english:
        return (
            # 直接透传 config 中的 reduce_rule
            f"User: {reduce_rule}\n"
            f"Text:\n{clean_batch}\n\n"
            f"Assistant: <think>\n</think>"
        )
    else:
        return (
            # 直接透传 config 中的 reduce_rule
            f"User: {reduce_rule}\n"
            f"文本：\n{clean_batch}\n\n"
            f"Assistant: <think>\n</think>"
        )
    
def build_slm_query_checkpoint_prompt(chunk_str: str, query: str, is_english: bool = False) -> str:
    clean_chunk = _wash_slm_input(chunk_str)
    if is_english:
        return (
            f"User: Extract info strictly related to [{query}] (No empty lines, reply 'Not found' if missing).\n"
            f"Text:\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>"
        )
    else:
        return (
            f"User: 提取与【{query}】相关的信息(勿输出空行，无则回未找到)。\n"
            f"文本：\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>"
        )

def build_slm_web_search_compress_prompt(query: str, raw_text: str, goal: str) -> str:
    clean_text = _wash_slm_input(raw_text)
    return (
        f"User: 提取网页中与【{query}】相关的事实(勿输出空行，无内容回无)。\n"
        f"网页：\n{clean_text}\n\n"
        f"Assistant: <think>\n</think>"
    )

def build_slm_relevance_judgment_prompt(mapped_text: str, query: str) -> str:
    clean_text = _wash_slm_input(mapped_text)
    return (
        f"User: 判断下文是否和实体【{query}】相关(仅回是或否)。\n"
        f"文字：\n{clean_text}\n\n"
        f"Assistant: <think>\n</think>"
    )

def build_slm_tool_routing_prompt(llm_thought: str, tool_interfaces: str) -> str:
    clean_thought = _wash_slm_input(llm_thought)
    clean_tools = _wash_slm_input(tool_interfaces)
    return (
        f"User: 将规划转为单行 JSON：{{\"action\": \"工具名\", \"args\": {{\"参数名\": \"值\"}}}}。退出填 finish_task。\n"
        f"工具：\n{clean_tools}\n"
        f"规划：\n{clean_thought}\n\n"
        f"Assistant: <think>\n</think>"
    )

# ==========================================
# 最终报告生成专用 (SLM 滚动溯源)
# ==========================================

def build_slm_section_binding_prompt(section_title: str, goal: str, candidate_list: str) -> str:
    """让小模型为一节报告挑选相关参考资料，输出 ref_id 的 JSON 数组"""
    clean_candidates = _wash_slm_input(candidate_list)
    return (
        f"User: 你正在为报告挑选资料。当前要撰写的章节是《{section_title}》，报告总目标是【{goal}】。\n"
        f"下面是候选资料清单，每行格式为 资料ID | 标题 | 摘要。请选出与本章节内容直接相关的资料ID。\n"
        f"只输出 JSON 数组，例如 [\"DOC_1\", \"WEB_REF_SF_ab12cd\"]。没有相关资料就输出 []。不要输出任何其他文字。\n"
        f"候选资料：\n{clean_candidates}\n\n"
        f"Assistant: <think>\n</think>"
    )

def build_slm_section_write_prompt(section_title: str, node_id: str, skeleton: str, goal: str,
                                   refs_text: str, part_idx: int = 1, total_parts: int = 1,
                                   is_english: bool = False) -> str:
    """让小模型撰写报告指定小节的正文（可能是多步生成中的第 k 步）"""
    clean_refs = _wash_slm_input(refs_text)
    clean_skeleton = _wash_slm_input(skeleton)
    if is_english:
        part_note = f" (part {part_idx}/{total_parts}: only cover the facts in the materials below, other parts will be merged later)" if total_parts > 1 else ""
        return (
            f"User: You are writing section 《{section_title}》{part_note} of a report. Goal: {goal}\n"
            f"Outline:\n{clean_skeleton}\n"
            f"Rules: 1. Write ONLY this section in Markdown. 2. Keep every citation tag like ^{{DOC_x}}^ or ^[WEB_REF_x]^ exactly as given, never invent new ones. "
            f"3. Preserve concrete figures, dates and viewpoints. 4. No empty lines.\n"
            f"Materials:\n{clean_refs}\n\n"
            f"Assistant: <think>\n</think>"
        )
    part_note = f"（本节内容较长，这是第 {part_idx}/{total_parts} 步，只需覆盖下面给出的资料，后续会合并）" if total_parts > 1 else ""
    return (
        f"User: 你正在撰写报告的第《{section_title}》节{part_note}。报告总目标：【{goal}】。\n"
        f"全文骨架：\n{clean_skeleton}\n"
        f"要求：1. 只写本节正文，Markdown 格式，不要输出空行，不要复述骨架。2. 资料中的引用角标（如 ^{{DOC_x}}^ 或 ^[WEB_REF_x]^）必须原样保留，禁止编造新角标。"
        f"3. 保留具体数据、时间节点与观点出处。\n"
        f"本节可用资料：\n{clean_refs}\n\n"
        f"Assistant: <think>\n</think>"
    )

def build_slm_section_merge_prompt(section_title: str, parts_text: str, is_english: bool = False) -> str:
    """把同一节分步生成的多段正文合并去重成一节"""
    clean_parts = _wash_slm_input(parts_text)
    if is_english:
        return (
            f"User: Merge the following parts of section 《{section_title}》 into one coherent section. "
            f"Deduplicate, keep all facts, keep every citation tag (^{{...}}^ / ^[...]^) exactly. No empty lines.\n"
            f"Parts:\n{clean_parts}\n\n"
            f"Assistant: <think>\n</think>"
        )
    return (
        f"User: 以下是报告第《{section_title}》节分步生成的多个片段，请合并成一段连贯的本节正文。"
        f"去重并合并同类逻辑，绝对保留事实性数据和所有引用角标（^{{...}}^ / ^[...]^ 原样保留），不要输出空行。\n"
        f"片段：\n{clean_parts}\n\n"
        f"Assistant: <think>\n</think>"
    )