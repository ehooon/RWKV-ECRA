import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

API_KEYS = {
    "baidu": "key",
    "volcengine": "key"
}

DATA_PIPELINE = {
    "input_directory": os.path.join(BASE_DIR, "data", "input"),
    "output_directory": os.path.join(BASE_DIR, "data", "output"),
    "checkpoint_directory": os.path.join(BASE_DIR, "data", "checkpoints"),
    "allowed_extensions": [".txt", ".md"],
    "max_chunk_tokens": 1600,
    "overlap_ratio": 0.1,
    
    # 🔴 MapReduce 压缩配置
    "reduce_group_size": 4,          # SLM 强制每 4 块一组进行合并
    "reduce_target_chunks": 1,
    "reduce_max_tokens": 32000,
    "slm_reduce_steps": 2,           # SLM 最大尝试轮数
    "llm_safe_window_tokens": 60000, # 🔴 LLM 绝对输入阈值 (适配64k，预留4k给系统框架)
    
    "map_focus": "保持原意压缩，提取核心逻辑，严格保留所有事实性内容",
    "reduce_rule": "保持原意压缩，去重并合并同类逻辑，绝对保留事实性数据和原始结论",
    "detail_level": "详尽",
    "reduce_max_tokens_internal": 3500,
    "slm_repeat_threshold": 5 
}

AGENT_CONFIG = {
    "max_files_per_batch": 10,     
    "max_error_retries": 3,        
    "memory_truncate_length": 60000 # 🔴 放大工作记忆，只要没超 64k 阈值就不截断，让大模型一眼看全全局！
}

SLM_CONFIG = {
    "endpoint": "http://192.168.0.125:8001/v1/chat/completions",
    "password": "rwkv7_7.2b",
    "concurrency": 16
}

TRACKING = {
    "enable": True,
    "log_dir": os.path.join(BASE_DIR, "logs")
}