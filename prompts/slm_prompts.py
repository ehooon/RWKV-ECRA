# RWKV-ECRA/prompts/slm_prompts.py
import re

def _wash_slm_input(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\n{2,}', '\n', text).strip()

def build_slm_preview_prompt(chunk_str: str) -> str:
    clean_chunk = _wash_slm_input(chunk_str)
    return (
        f"User: 请阅读下方文本，概括其核心主题和文件类型。如果文本无实质内容，回复“无实质内容”。\n"
        f"文本：\n{clean_chunk}\n\n" 
        f"Assistant: <think>\n</think>" 
    )

def build_slm_sequential_summary_prompt(chunk_str: str, current_idx: int, total_chunks: int, focus: str, is_english: bool = False) -> str:
    clean_chunk = _wash_slm_input(chunk_str)
    if is_english:
        return (
            f"User: Extract core factual points from the text based on [{focus}]. Output as a Markdown list. If no substantive content, reply 'None'.\n"
            f"Text:\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>"
        )
    else:
        return (
            f"User: 按照【{focus}】提取文本中的客观事实。以无序列表输出。若完全无实质内容，回复“无”。\n"
            f"文本：\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>" 
        )

def build_slm_reduce_prompt(batch_text: str, reduce_rule: str, current_step: int, total_steps: int, is_english: bool = False) -> str:
    clean_batch = _wash_slm_input(batch_text)
    if is_english:
        return (
            f"User: Merge and deduplicate the bullet points based on [{reduce_rule}]. Output as a list.\n"
            f"Points:\n{clean_batch}\n\n"
            f"Assistant: <think>\n</think>"
        )
    else:
        return (
            f"User: 按照【{reduce_rule}】对下方列出的事实要点进行去重并合并。以列表输出精炼结果。\n"
            f"要点：\n{clean_batch}\n\n"
            f"Assistant: <think>\n</think>"
        )
    
def build_slm_query_checkpoint_prompt(chunk_str: str, query: str, is_english: bool = False) -> str:
    clean_chunk = _wash_slm_input(chunk_str)
    if is_english:
        return (
            f"User: Extract information strictly related to [{query}] from the text. If not found, reply 'Not found'.\n"
            f"Text:\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>"
        )
    else:
        return (
            f"User: 请提取与【{query}】客观相关的信息。如果不存在，回复“未找到”。\n"
            f"文本：\n{clean_chunk}\n\n"
            f"Assistant: <think>\n</think>"
        )


def build_slm_web_search_compress_prompt(query: str, raw_text: str, goal: str) -> str:
    clean_text = _wash_slm_input(raw_text)
    return (
        f"User: 我们的调查目标是“{goal}”。请阅读下方的网页内容，提取关于【{query}】的客观事实。\n"
        f"如果发现这个实体跟我们的调查目标毫无关系，请直接说明它的真实身份（比如它只是个网红、游戏或无关品牌），千万不要强行把它和调查目标扯上关系。\n"
        f"文本：\n{clean_text}\n\n"
        f"Assistant: <think>\n</think>"
    )

# 🌟 新增：极简自然语言物理防关联判断提示词 🌟
def build_slm_relevance_judgment_prompt(mapped_text: str, query: str) -> str:
    clean_text = _wash_slm_input(mapped_text)
    return (
        f"User: 判断这段文字是否和目标实体{query}相关。\n"
        f"文字：\n{clean_text}\n\n"
        f"Assistant: <think>\n</think>"
    )

def build_slm_tool_routing_prompt(llm_thought: str, tool_interfaces: str) -> str:
    clean_thought = _wash_slm_input(llm_thought)
    clean_tools = _wash_slm_input(tool_interfaces)
    return (
        f"User: 请将下方的行动规划转换为 JSON 格式，仅输出 JSON：{{\"action\": \"工具名\", \"args\": {{\"参数名\": \"值\"}}}}。遇到退出或无工具时填 finish_task。\n"
        f"可用工具：\n{clean_tools}\n"
        f"行动规划：\n{clean_thought}\n\n"
        f"Assistant: <think>\n</think>"
    )