import os
import json
import hashlib
import shutil
from config import DATA_PIPELINE

def _get_cache_key(file_path: str, kwargs: dict) -> str:
    raw_str = file_path + json.dumps(kwargs, sort_keys=True)
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

def get_checkpoint(file_path: str, kwargs: dict) -> str:
    ckpt_dir = DATA_PIPELINE["checkpoint_directory"]
    cache_key = _get_cache_key(file_path, kwargs)
    ckpt_path = os.path.join(ckpt_dir, f"{cache_key}.json")
    
    if os.path.exists(ckpt_path):
        try:
            with open(ckpt_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("result", "")
        except Exception:
            return ""
    return ""

def save_checkpoint(file_path: str, kwargs: dict, result: str):
    ckpt_dir = DATA_PIPELINE["checkpoint_directory"]
    os.makedirs(ckpt_dir, exist_ok=True)
    
    cache_key = _get_cache_key(file_path, kwargs)
    ckpt_path = os.path.join(ckpt_dir, f"{cache_key}.json")
    
    with open(ckpt_path, 'w', encoding='utf-8') as f:
        json.dump({
            "file_path": file_path,
            "params": kwargs,
            "result": result
        }, f, ensure_ascii=False, indent=2)

def clear_all_checkpoints():
    ckpt_dir = DATA_PIPELINE["checkpoint_directory"]
    if os.path.exists(ckpt_dir):
        shutil.rmtree(ckpt_dir)
        print(f"🧹 [断点清理] 任务已圆满完成，中间缓存目录 {ckpt_dir} 已自动清理。")