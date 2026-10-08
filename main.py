# RWKV-ECRA/main.py
import os
import sys
import uuid
from datetime import datetime
from agent.orchestrator import Orchestrator
from config import DATA_PIPELINE, API_KEYS
from utils.task_manager import record_task, is_task_stopped

def setup_env():
    os.environ['BAIDU_API_KEY'] = API_KEYS.get("baidu", "")
    os.makedirs(DATA_PIPELINE["input_directory"], exist_ok=True)
    os.makedirs(DATA_PIPELINE["output_directory"], exist_ok=True)
    os.makedirs(DATA_PIPELINE.get("asset_directory", "./data/knowledge_assets"), exist_ok=True)

if __name__ == "__main__":
    setup_env()
    print("[系统] Agent 引擎已启动")
    
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("\n" + "="*60)
        query = input("请输入文本分析指令 (例如: '提取目录中所有财务文件的核心数据' 或 '生成总览报告')\n> ")
        print("="*60 + "\n")
        
    if not query.strip():
        print("指令为空，退出程序。")
        sys.exit(0)
        
    print(f"[系统] 接收指令: {query}\n开始执行分析任务...\n")
    
    agent = Orchestrator()
    task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    task_output_dir = os.path.join(DATA_PIPELINE["output_directory"], task_id)
    record_task(task_id, query, "running", task_output_dir)
    try:
        response = agent.run(query, task_id=task_id)
        if not is_task_stopped(task_id):
            record_task(task_id, query, "completed", task_output_dir)
        print("\n" + "="*20 + " 任务完成 " + "="*20)
        print(response)
    except Exception as e:
        if not is_task_stopped(task_id):
            record_task(task_id, query, "failed", task_output_dir, str(e))
        print(f"\n[执行异常] 运行中止: {e}")