import os
import json
import threading
import queue
from datetime import datetime

def fallback_serializer(obj):
    if hasattr(obj, 'model_dump'): return obj.model_dump()
    return str(obj)

class EventTracker:
    def __init__(self, log_dir="./logs", enable=True):
        self.enable = enable
        self.log_dir = log_dir
        
        if self.enable:
            os.makedirs(self.log_dir, exist_ok=True)
            self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(self.log_dir, f"trace_{self.session_id}.jsonl")
            self.slm_log_file = os.path.join(self.log_dir, f"slm_trace_{self.session_id}.jsonl")
            
            self.write_queue = queue.Queue()
            self.writer_thread = threading.Thread(target=self._async_writer, daemon=True)
            self.writer_thread.start()

    def track(self, step_name: str, input_data: any, output_data: any, meta: dict = None):
        if not self.enable: return
        self.write_queue.put({
            "target_file": self.log_file,
            "payload": {
                "timestamp": datetime.now().isoformat(),
                "step": step_name,
                "input": input_data,
                "output": output_data,
                "meta": meta or {}
            }
        })

    def track_slm(self, input_prompt: str, output_text: str):
        if not self.enable: return
        self.write_queue.put({
            "target_file": self.slm_log_file,
            "payload": {
                "timestamp": datetime.now().isoformat(),
                "prompt": input_prompt,
                "response": output_text
            }
        })

    def _async_writer(self):
        while True:
            try:
                event = self.write_queue.get()
                if event is None: break
                
                target_file = event["target_file"]
                with open(target_file, 'a', encoding='utf-8') as f:
                    json_str = json.dumps(event["payload"], ensure_ascii=False, default=fallback_serializer)
                    f.write(json_str + "\n")
                    
                self.write_queue.task_done()
            except Exception as e:
                print(f"[Tracker Error] 异步日志写入失败: {e}")