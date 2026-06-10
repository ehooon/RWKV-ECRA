# RWKV-ECRA/translator_plugin/config.py

TRANSLATOR_CONFIG = {
    # 🔴 独立的翻译切块长度 (Token)
    # 建议设在 1000-1500 左右，既不会超显存，又能保证英文大段落完整，防止句子被拦腰斩断
    "max_chunk_tokens": 300, 
    
    # 翻译任务必须为 0，绝对不能改，否则生成的中文交界处会出现复读两遍的句子
    "overlap_ratio": 0.0       
}