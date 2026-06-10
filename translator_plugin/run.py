# RWKV-ECRA/translator_plugin/run.py
import os
import sys

# 动态将项目根目录加入环境变量，以便能引用主项目的 clients 和 utils
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PLUGIN_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import DATA_PIPELINE
from translator_plugin.core import process_translation_task

# 📥 共用项目原有的全局输入目录
TRANS_INPUT_DIR = DATA_PIPELINE["input_directory"]

# 📤 输出完全内聚：就存在这个插件大文件夹下的 output 目录里！
TRANS_OUTPUT_DIR = os.path.join(PLUGIN_DIR, "output")

def setup_plugin_env():
    os.makedirs(TRANS_INPUT_DIR, exist_ok=True)
    os.makedirs(TRANS_OUTPUT_DIR, exist_ok=True)

if __name__ == "__main__":
    setup_plugin_env()
    
    print("="*60)
    print("🌍 独立翻译插件已启动 (Powered by SLM Client)")
    print(f"📥 正在监视全局输入: {TRANS_INPUT_DIR}")
    print(f"📤 翻译结果将输出至: {TRANS_OUTPUT_DIR}")
    print("="*60)
    
    user_input = input("\n请确认待翻译文档已放入全局输入目录，按 Enter 键开始 (输入 q 退出): ")
    
    if user_input.strip().lower() == 'q':
        print("已退出。")
        sys.exit(0)
        
    process_translation_task(TRANS_INPUT_DIR, TRANS_OUTPUT_DIR)
    
    print("\n🎉 所有翻译任务执行完毕，请前往 translator_plugin/output 查看结果！")