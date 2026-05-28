import os
import sys
from agent.orchestrator import Orchestrator
from config import DATA_PIPELINE, API_KEYS

def setup_env():
    os.environ['BAIDU_API_KEY'] = API_KEYS.get("baidu", "")
    os.makedirs(DATA_PIPELINE["input_directory"], exist_ok=True)
    os.makedirs(DATA_PIPELINE["output_directory"], exist_ok=True)

if __name__ == "__main__":
    setup_env()
    print("🚀 [单次指令模式] Agent 引擎已启动。")
    
    # 支持命令行传参，也支持交互式输入
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("\n" + "="*60)
        query = input("💡 请输入您的长文本分析需求\n(例如: '帮我提取目录中所有包含财务二字的文件核心数据' 或 '全量生成总览报告')\n👉 ")
        print("="*60 + "\n")
        
    if not query.strip():
        print("指令为空，退出程序。")
        sys.exit(0)
        
    print(f"🧠 接收指令: {query}\n正在唤醒大模型进行规划与执行...\n")
    
    agent = Orchestrator()
    try:
        response = agent.run(query)
        print("\n" + "🎉 "*10 + " 任务圆满完成 " + "🎉 "*10)
        print(response)
    except Exception as e:
        print(f"\n❌ [执行异常] Agent 运行遭遇阻断: {e}")