# RWKV-ECRA/utils/token_tracker.py
import os
import json
import threading
from contextvars import ContextVar
from config import DATA_PIPELINE

# 声明上下文变量，后台任务启动时注入当前 Task ID，子线程自动继承
current_task_id: ContextVar[str] = ContextVar("current_task_id", default="UNKNOWN_TASK")

class GlobalTokenTracker:
    def __init__(self):
        self.lock = threading.Lock()
        output_dir = DATA_PIPELINE.get("output_directory", "./data/output")
        os.makedirs(output_dir, exist_ok=True)
        self.file_path = os.path.join(output_dir, "global_token_usage.json")
        
        self.stats = {
            "global": {
                "rwkv_slm": {"input_tokens": 0, "output_tokens": 0},
                "cloud_llm": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
            },
            "tasks": {}
        }
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "global" in data:
                        self.stats = data
                    else:
                        # 兼容处理：如果没有 global 结构，说明是旧版数据，做合并
                        self.stats["global"]["rwkv_slm"].update(data.get("rwkv_slm", {}))
                        self.stats["global"]["cloud_llm"].update(data.get("cloud_llm", {}))
            except Exception:
                pass

    def _save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _init_task_locked(self, task_id: str):
        if task_id not in self.stats["tasks"]:
            self.stats["tasks"][task_id] = {
                "rwkv_slm": {"input_tokens": 0, "output_tokens": 0},
                "cloud_llm": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
            }

    def add_slm(self, input_tokens: int, output_tokens: int, task_id: str = None):
        tid = task_id or current_task_id.get()
        with self.lock:
            # 记录全局总览
            self.stats["global"]["rwkv_slm"]["input_tokens"] += input_tokens
            self.stats["global"]["rwkv_slm"]["output_tokens"] += output_tokens
            
            # 记录独立任务账单
            if tid and tid != "UNKNOWN_TASK":
                self._init_task_locked(tid)
                self.stats["tasks"][tid]["rwkv_slm"]["input_tokens"] += input_tokens
                self.stats["tasks"][tid]["rwkv_slm"]["output_tokens"] += output_tokens
                
            self._save()

    def add_llm(self, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0, task_id: str = None):
        tid = task_id or current_task_id.get()
        with self.lock:
            # 记录全局总览
            self.stats["global"]["cloud_llm"]["input_tokens"] += input_tokens
            self.stats["global"]["cloud_llm"]["output_tokens"] += output_tokens
            self.stats["global"]["cloud_llm"]["reasoning_tokens"] += reasoning_tokens
            
            # 记录独立任务账单
            if tid and tid != "UNKNOWN_TASK":
                self._init_task_locked(tid)
                self.stats["tasks"][tid]["cloud_llm"]["input_tokens"] += input_tokens
                self.stats["tasks"][tid]["cloud_llm"]["output_tokens"] += output_tokens
                self.stats["tasks"][tid]["cloud_llm"]["reasoning_tokens"] += reasoning_tokens
                
            self._save()

    def get_stats(self, task_id: str = None):
        with self.lock:
            if task_id:
                return self.stats["tasks"].get(task_id, {})
            return self.stats

    def reset(self):
        with self.lock:
            self.stats = {
                "global": {
                    "rwkv_slm": {"input_tokens": 0, "output_tokens": 0},
                    "cloud_llm": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
                },
                "tasks": {}
            }
            self._save()

global_token_tracker = GlobalTokenTracker()