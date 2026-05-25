import os
from agent.orchestrator import Orchestrator
from config import DATA_PIPELINE, API_KEYS

def setup_env():
    os.environ['BAIDU_API_KEY'] = API_KEYS.get("baidu", "")
    os.makedirs(DATA_PIPELINE["input_directory"], exist_ok=True)
    os.makedirs(DATA_PIPELINE["output_directory"], exist_ok=True)

if __name__ == "__main__":
    setup_env()
    
    ckpt_dir = DATA_PIPELINE.get("checkpoint_directory")
    if os.path.exists(ckpt_dir) and len(os.listdir(ckpt_dir)) > 0:
        print(f"🔄 [断点检测] 发现上次未完成的中间进度 ({len(os.listdir(ckpt_dir))} 个文件)，将启用断点续传机制...")
    else:
        print("🚀 [断点检测] 启动全新任务。")

    agent = Orchestrator()
    print("Agent 初始化完成。开始执行指令...")
    
    query = "帮我深度分析输入目录下的所有文章，请根据文章长短自己把握总结详细程度，并在最终报告中给出这些文件的跨文件关联分析。"
    print(f"用户：{query}\n")
    
    response = agent.run(query)
    print("\n" + "="*20 + " 最终输出结果 " + "="*20)
    print(response)