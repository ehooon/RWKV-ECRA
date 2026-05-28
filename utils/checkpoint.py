import os
import json
import hashlib
from typing import List
from config import DATA_PIPELINE

def _get_cache_key(file_path: str) -> str:
    return hashlib.md5(file_path.encode('utf-8')).hexdigest()

def get_checkpoint(file_path: str) -> str:
    ckpt_dir = DATA_PIPELINE["checkpoint_directory"]
    cache_key = _get_cache_key(file_path)
    ckpt_path = os.path.join(ckpt_dir, f"{cache_key}.json")
    
    if os.path.exists(ckpt_path):
        try:
            with open(ckpt_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("result", "")
        except Exception:
            return ""
    return ""

def save_checkpoint(file_path: str, result: str):
    ckpt_dir = DATA_PIPELINE["checkpoint_directory"]
    os.makedirs(ckpt_dir, exist_ok=True)
    
    cache_key = _get_cache_key(file_path)
    ckpt_path = os.path.join(ckpt_dir, f"{cache_key}.json")
    
    with open(ckpt_path, 'w', encoding='utf-8') as f:
        json.dump({
            "file_path": file_path,
            "result": result
        }, f, ensure_ascii=False, indent=2)

def clear_checkpoints_for_files(file_paths: List[str]):
    ckpt_dir = DATA_PIPELINE["checkpoint_directory"]
    if not os.path.exists(ckpt_dir):
        return
        
    deleted_count = 0
    for fp in file_paths:
        cache_key = _get_cache_key(fp)
        ckpt_path = os.path.join(ckpt_dir, f"{cache_key}.json")
        if os.path.exists(ckpt_path):
            try:
                os.remove(ckpt_path)
                deleted_count += 1
            except Exception:
                pass
                
    if deleted_count > 0:
        print(f"🧹 [断点清理] 精准打击：已自动清理本次任务用完的 {deleted_count} 个中间缓存。")