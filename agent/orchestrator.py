# RWKV-ECRA/agent/orchestrator.py
import os
import json
from dataclasses import dataclass, field
from typing import Dict
from agent.analyzer import Analyzer
from agent.planner import Planner
from tools.static_ops import search_local_file, preview_document_content
from utils.tracker import EventTracker
from config import TRACKING

# 引入动态长耗时工作流
from workflows.map_reduce_flow import delegate_to_small_models
from workflows.memory_query_flow import query_checkpoint_via_slm
from workflows.report_flow import batch_process_individual_reports, generate_final_aggregate_reports

@dataclass
class AgentState:
    user_query: str = ""
    id_to_path: Dict[str, str] = field(default_factory=dict)
    path_to_id: Dict[str, str] = field(default_factory=dict)
    working_memory: Dict[str, str] = field(default_factory=dict) 
    last_feedback: str = "" 

    def to_markdown_context(self) -> str:
        sandbox_status = [f"沙盒总文件数: {len(self.id_to_path)} 个。"]
        for i, (fid, path) in enumerate(self.id_to_path.items()):
            if i >= 15:
                sandbox_status.append("... (隐藏剩余文件，请使用 search_local_file 工具精确检索)")
                break
            status = "✅ 已提炼" if f"Summary_{fid}" in self.working_memory else "⏳ 待提炼"
            sandbox_status.append(f"- {fid}: {os.path.basename(path)} [{status}]")

        memory_index = ["*(空)*"] if not self.working_memory else [
            f"- 🔑 Key: `{k}` | 状态: 就绪" for k in self.working_memory.keys() if not k.startswith("__") and not k.startswith("AbsPath_") and not k.startswith("Path_")
        ]

        return "\n".join([
            "【1. 沙盒快照】", "\n".join(sandbox_status), "",
            "【2. 工作记忆区(已提炼内容)】", "\n".join(memory_index), "",
            "【3. 底层反馈】", self.last_feedback if self.last_feedback else "无"
        ])

class Orchestrator:
    def __init__(self):
        self.tracker = EventTracker(log_dir=TRACKING.get("log_dir", "./logs"), enable=TRACKING.get("enable", True))
        self.state = AgentState()
        self.state.working_memory["__category_tree__"] = {} 
        self.analyzer = Analyzer()
        self.planner = Planner()

    def run(self, user_query: str) -> str:
        self.tracker.track("User_Input", input_data=user_query, output_data=None)
        self.state.user_query = user_query
        
        # 静态扫描：一次性映射ID
        try:
            initial_files = json.loads(search_local_file(keyword=""))
            for i, p in enumerate(initial_files):
                fid = f"DOC_{i+1}"
                self.state.id_to_path[fid] = p
                self.state.path_to_id[p] = fid
            self.state.last_feedback = f"✅ 系统就绪，沙盒中发现 {len(initial_files)} 份可用文件。"
        except Exception:
            self.state.last_feedback = "✅ 沙盒为空。"
            
        step_count = 0
        MAX_STEPS = 40 
        
        while step_count < MAX_STEPS:
            step_count += 1
            context = self.state.to_markdown_context()

            try:
                # 1. 意图分析阶段 (What)
                analysis = self.analyzer.analyze_intent_and_phase(user_query, context)
                phase = analysis.get("next_phase", "DISCOVERY")
                print(f"\n🧠 [第 {step_count} 步|分析师]: 阶段={phase} | 推演={analysis.get('missing_information')}")
                
                # 2. 工具规划阶段 (How)
                plan = self.planner.plan_next_action(user_query, analysis, context, phase)
                action, args = plan["action"], plan["args"]
                print(f"🎯 [规划师]: 决定调用工具 {action}")
                
                self.tracker.track("Routing", input_data=phase, output_data=plan)

                if action == "finish_task":
                    return "✅ 任务由 Agent 判定已满足用户指令，主动声明完成。"

                # 3. 跨文件参数补齐
                args["working_memory"] = self.state.working_memory
                args["tracker"] = self.tracker
                
                if "file_ids" in args:
                    args["actual_file_ids"] = args["file_ids"]
                    args["file_paths"] = [self.state.id_to_path.get(fid) for fid in args["file_ids"] if fid in self.state.id_to_path]

                # 4. 动静分离路由分发
                if action == "search_local_file":
                    args["path_to_id"] = self.state.path_to_id
                    result = search_local_file(**args)
                    
                elif action == "preview_document_content":
                    result = preview_document_content(**args)
                    
                elif action == "delegate_to_small_models":
                    result = delegate_to_small_models(**args)
                    
                elif action == "query_checkpoint_via_slm":
                    result = query_checkpoint_via_slm(**args)
                    
                elif action == "batch_process_individual_reports":
                    result = batch_process_individual_reports(**args)
                    
                elif action == "generate_final_aggregate_reports":
                    result = generate_final_aggregate_reports(**args)
                    return f"🎉 聚合全局报告生成完毕！\n底层反馈: {result}"
                else:
                    result = "⚠️ 未知工具。"

                self.state.last_feedback = f"✅ 执行成功:\n{result}"

            except Exception as e:
                self.state.last_feedback = f"❌ 底层执行异常拦截: {str(e)}"
                print(f"❌ Error: {e}")
                
        return "⚠️ 达到引擎最大调度步数，被强制阻断。"