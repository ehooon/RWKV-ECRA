# RWKV-ECRA/utils/task_manager.py
import os
import json
import threading
from datetime import datetime
from config import DATA_PIPELINE

TASK_LOG_FILE = os.path.join(DATA_PIPELINE.get("output_directory", "./data/output"), "tasks.jsonl")

class TaskStore:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._lock = threading.Lock()
        self._task_index = {}
        self._ordered_keys = []
        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    record = json.loads(line)
                    tid = record.get("task_id")
                    if tid:
                        if tid not in self._task_index:
                            self._ordered_keys.append(tid)
                            self._task_index[tid] = record
                        else:
                            self._task_index[tid].update(record)
                        
                        # 墓碑清除：如果在重载时发现处于删除状态，彻底脱离内存
                        if self._task_index[tid].get('status') == 'deleted':
                            if tid in self._ordered_keys:
                                self._ordered_keys.remove(tid)
                            del self._task_index[tid]
                except json.JSONDecodeError:
                    continue

    def record_task(self, task_id: str, query: str, status: str, result_dir: str = "", error: str = ""):
        with self._lock:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            record = {
                "task_id": task_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": query,
                "status": status,
                "result_dir": result_dir,
                "error": error
            }
            
            if task_id not in self._task_index:
                self._ordered_keys.append(task_id)
                self._task_index[task_id] = record
            else:
                self._task_index[task_id].update(record)
            
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._task_index[task_id], ensure_ascii=False) + "\n")

    def update_task_progress(self, task_id: str, progress: str):
        with self._lock:
            if task_id in self._task_index:
                self._task_index[task_id]['progress'] = progress
                with open(self.filepath, "a", encoding="utf-8") as f:
                    f.write(json.dumps(self._task_index[task_id], ensure_ascii=False) + "\n")

    def request_stop(self, task_id: str):
        with self._lock:
            if task_id in self._task_index and self._task_index[task_id]['status'] == 'running':
                self._task_index[task_id]['status'] = 'stopped'
                with open(self.filepath, "a", encoding="utf-8") as f:
                    f.write(json.dumps(self._task_index[task_id], ensure_ascii=False) + "\n")

    def delete_task(self, task_id: str):
        with self._lock:
            if task_id in self._task_index:
                self._task_index[task_id]['status'] = 'deleted'
                with open(self.filepath, "a", encoding="utf-8") as f:
                    f.write(json.dumps(self._task_index[task_id], ensure_ascii=False) + "\n")
                
                # 物理删除专属报告文件夹，释放硬盘空间
                task_dir = self._task_index[task_id].get("result_dir")
                if task_dir and os.path.exists(task_dir):
                    import shutil
                    try:
                        shutil.rmtree(task_dir)
                    except Exception:
                        pass
                
                # 抹除内存
                if task_id in self._ordered_keys:
                    self._ordered_keys.remove(task_id)
                del self._task_index[task_id]

    def is_task_stopped(self, task_id: str) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if not task:
                return True # 不存在也直接熔断退出
            return task.get('status') in ('stopped', 'deleted')

    def get_all_tasks(self) -> list:
        with self._lock:
            return [self._task_index[k] for k in reversed(self._ordered_keys)]

_store = None
def _get_store() -> TaskStore:
    global _store
    if _store is None:
        _store = TaskStore(TASK_LOG_FILE)
    return _store

def init_task_file():
    _get_store()

def record_task(task_id: str, query: str, status: str, result_dir: str = "", error: str = ""):
    _get_store().record_task(task_id, query, status, result_dir, error)

def update_task_progress(task_id: str, progress: str):
    _get_store().update_task_progress(task_id, progress)

def request_stop(task_id: str):
    _get_store().request_stop(task_id)

def delete_task(task_id: str):
    _get_store().delete_task(task_id)

def is_task_stopped(task_id: str) -> bool:
    return _get_store().is_task_stopped(task_id)

def get_all_tasks() -> list:
    return _get_store().get_all_tasks()