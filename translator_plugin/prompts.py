# RWKV-ECRA/translator_plugin/prompts.py

def build_translation_prompt(chunk_str: str) -> str:
    """
    翻译专用的纯续写格式 Prompt。
    利用模型的前缀补全能力，直接将英文翻译为中文。
    """
    return f"English: {chunk_str}\n\nChinese:"