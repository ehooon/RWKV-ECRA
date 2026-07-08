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