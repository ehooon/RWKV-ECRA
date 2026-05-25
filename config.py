import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

API_KEYS = {
    "baidu": "key"
}

DATA_PIPELINE = {
    "input_directory": os.path.join(BASE_DIR, "data", "input"),
    "output_directory": os.path.join(BASE_DIR, "data", "output"),
    "checkpoint_directory": os.path.join(BASE_DIR, "data", "checkpoints"),
    "allowed_extensions": [".txt", ".md"],
    "max_chunk_tokens": 1600,
    "overlap_ratio": 0.1,
    "reduce_group_size": 5, 
    "reduce_target_chunks": 1,
    "reduce_max_tokens": 3200
}

SLM_CONFIG = {
    "endpoint": "http://localhost:8001/v1/chat/completions",
    "password": "rwkv7_7.2b",
    "concurrency": 16
}

TRACKING = {
    "enable": True,
    "log_dir": os.path.join(BASE_DIR, "logs")
}