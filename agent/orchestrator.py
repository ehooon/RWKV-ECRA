# RWKV-ECRA/agent/orchestrator.py
import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Set
from agent.analyzer import Analyzer
from agent.planner import Planner
from utils.tracker import EventTracker
from config import TRACKING, DATA_PIPELINE
from tools.registry import ToolRegistry
from utils.chunker import get_token_count
from utils.task_manager import is_task_stopped, update_task_progress

import tools.static_ops 
import tools.web_search
import workflows.map_reduce_flow
import workflows.memory_query_flow
import workflows.report_flow

@dataclass
class AgentState:
    task_id: str = ""
    task_output_dir: str = ""  
    user_query: str = ""
    id_to_path: Dict[str, str] = field(default_factory=dict)
    path_to_id: Dict[str, str] = field(default_factory=dict)
    working_memory: Dict[str, str] = field(default_factory=dict) 
    memory_catalog: Dict[str, str] = field(default_factory=dict) 
    last_feedback: str = "" 
    
    entity_audit: Dict[str, str] = field(default_factory=dict)
    abandoned_file_ids: Set[str] = field(default_factory=set)
    
    is_finished: bool = False
    final_result: str = ""

    def _mount_global_env(self) -> str:
        current_time_str = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        return "\n".join([
            "【挂载模块: 任务环境】",
            f"- 系统时间: {current_time_str}", 
            f"- 初始指令: {self.user_query}"
        ])

    def _mount_memory_catalog(self) -> str:
        filtered_mem = {}
        for k, v in self.working_memory.items():
            if any(fid in k for fid in self.abandoned_file_ids):
                continue
            if not k.startswith("__") and not k.startswith("AbsPath_") and not k.startswith("Path_"):
                filtered_mem[k] = v

        if not filtered_mem:
            return "【挂载模块: 情报目录大纲】\n*(记忆区当前为空)*"
            
        memory_total_tokens = sum(get_token_count(str(v)) for v in filtered_mem.values())
        memory_details = []
        
        for k in filtered_mem.keys():
            desc = self.memory_catalog.get(k, "已存储有效结构化数据")
            memory_details.append(f"- `{k}`: [{desc}]")
                
        lines = ["【挂载模块: 情报目录大纲】"]
        
        lines.append(f"[系统状态] 当前可用知识库缓存已挂载（体积估算: {memory_total_tokens} Tokens）。")
        lines.append("【工作指引】: 请继续检查并收集其他缺漏情报；如果所有核心事实均已齐备，请立即调用 generate_final_aggregate_reports 进入最终大一统聚合（系统底座已搭载自动超限折叠与二次重压引擎，请放心调用无需顾虑 Token）。")
            
        lines.append("\n以下是已获取的可用情报，请据此决定下一步：")
        lines.extend(memory_details)
        return "\n".join(lines)

    def _mount_local_sandbox(self) -> str:
        pending_items = []
        for fid, path in self.id_to_path.items():
            if fid in self.abandoned_file_ids:
                continue 
            if f"Preview_{fid}" in self.memory_catalog or f"Summary_{fid}" in self.memory_catalog:
                continue 
            pending_items.append(f"- {fid}: {os.path.basename(path)} [未读]")
            
        if not pending_items:
            return ""
            
        lines = [
            "【挂载模块: 本地文件沙盒】", 
            f"发现 {len(pending_items)} 个尚未探索的本地文件资源："
        ]
        lines.extend(pending_items[:15])
        if len(pending_items) > 15:
            lines.append("... (隐藏剩余未处理文件，使用 search_local_file 检索)")
            
        return "\n".join(lines)

    def _mount_feedback(self) -> str:
        if not self.last_feedback:
            return ""
        return f"【挂载模块: 最新执行反馈】\n{self.last_feedback}"

    def to_markdown_context(self) -> str:
        modules = [
            self._mount_global_env(),
            self._mount_memory_catalog(),
            self._mount_local_sandbox(),
            self._mount_feedback()
        ]
        return "\n\n".join(m for m in modules if m)


class Orchestrator:
    def __init__(self):
        self.tracker = EventTracker(log_dir=TRACKING.get("log_dir", "./logs"), enable=TRACKING.get("enable", True))
        self.state = AgentState()
        self.state.working_memory["__category_tree__"] = {} 
        self.analyzer = Analyzer()
        self.planner = Planner()

    def run(self, user_query: str, task_id: str = None) -> str:
        self.state.task_id = task_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.state.task_output_dir = os.path.join(DATA_PIPELINE.get("output_directory", "./data/output"), self.state.task_id)
        os.makedirs(self.state.task_output_dir, exist_ok=True)
        
        self.tracker.track("User_Input", input_data=user_query, output_data=None)
        self.state.user_query = user_query
        
        debug_dir = DATA_PIPELINE.get("debug_directory", "./data/debug_slm")
        os.makedirs(debug_dir, exist_ok=True)
        session_id = self.state.task_id
        trace_file = os.path.join(debug_dir, f"DeepResearch_Trace_{session_id}.md")
        
        with open(trace_file, "w", encoding="utf-8") as f:
            f.write(f"# Deep Research 执行追踪日志\n\n**启动时间**: {session_id}\n**用户指令**: {user_query}\n\n---\n\n")

        update_task_progress(self.state.task_id, "🔧 正在初始化环境，搜索本地目录中的文件...")

        try:
            initial_files_json = ToolRegistry.execute("search_local_file", {"keyword": ""}, {})
            initial_files = json.loads(initial_files_json)
            for i, p in enumerate(initial_files):
                fid = f"DOC_{i+1}"
                self.state.id_to_path[fid] = p
                self.state.path_to_id[p] = fid
            self.state.last_feedback = f"系统就绪，目录中发现 {len(initial_files)} 份可用文件。"
        except Exception:
            self.state.last_feedback = "目录为空。"
            
        step_count = 0
        MAX_STEPS = 40 
        
        while step_count < MAX_STEPS:
            if is_task_stopped(self.state.task_id):
                self.state.last_feedback = "任务已被用户手动终止。"
                self.state.is_finished = True
                self.state.final_result = "执行中止: 任务已被手动停止。"
                return self.state.final_result
                
            step_count += 1
            context_text = self.state.to_markdown_context()

            try:
                # 🔴 播报推演阶段
                update_task_progress(self.state.task_id, f"🧠 正在思考下一步行动... (当前执行步数: {step_count})")

                analysis = self.analyzer.analyze_intent_and_phase(user_query, context_text)
                phase = analysis.get("next_phase", "DISCOVERY")
                missing_info = analysis.get("missing_information", "无")
                
                # 🔴 播报意图方向
                progress_msg = f"🏃 步数 {step_count} | 阶段: {phase}\n🎯 方向: {missing_info}\n🛠️ 动作: 准备进行规划推演..."
                update_task_progress(self.state.task_id, progress_msg)
                
                if "entity_audit" in analysis:
                    self.state.entity_audit.update(analysis["entity_audit"])
                    
                abandoned = analysis.get("abandoned_file_ids", [])
                if isinstance(abandoned, list) and abandoned:
                    self.state.abandoned_file_ids.update(abandoned)
                
                print(f"\n" + "="*50)
                print(f"🕵️ [Deep Research 步数 {step_count}]")
                if self.state.abandoned_file_ids:
                    print(f"🗑️ 系统已物理屏蔽资源: {list(self.state.abandoned_file_ids)}")
                print(f"🔍 实体审计 (Entity Audit):")
                for ent, desc in analysis.get('entity_audit', {}).items():
                    print(f"  - {ent}: {desc}")
                print(f"📊 任务拆解: {analysis.get('task_decomposition', [])}")
                print(f"🧠 进度反思: {analysis.get('reflection', '无')}")
                print(f"🎯 下步动作: {missing_info}")
                print(f"📍 当前阶段: {phase}")
                print("="*50)
                
                plan = self.planner.plan_next_action(user_query, analysis, context_text, phase)
                action, args = plan["action"], plan["args"]
                print(f"[工具调用]: -> {action}()")

                # 🔴 播报当前正执行的工具
                progress_msg = f"🏃 步数 {step_count} | 阶段: {phase}\n🎯 方向: {missing_info}\n🛠️ 动作: 正在调用工具 {action}()"
                update_task_progress(self.state.task_id, progress_msg)
                
                self.tracker.track("Routing", input_data=phase, output_data=plan)

                step_log = f"## 🏃 步骤 {step_count} (阶段: {phase})\n\n"
                step_log += "### 1. 状态分析 (Analyzer)\n"
                step_log += f"- **实体审计**: \n```json\n{json.dumps(analysis.get('entity_audit', {}), ensure_ascii=False, indent=2)}\n```\n"
                step_log += f"- **任务拆解**: {analysis.get('task_decomposition', [])}\n"
                step_log += f"- **进度反思**: {analysis.get('reflection', '无')}\n"
                step_log += f"- **下步动作**: {missing_info}\n\n"
                step_log += "### 2. 工具调用规划 (Planner)\n"
                step_log += f"- **动作**: `{action}`\n"
                step_log += f"- **参数**: \n```json\n{json.dumps(args, ensure_ascii=False, indent=2)}\n```\n\n"
                
                with open(trace_file, "a", encoding="utf-8") as f:
                    f.write(step_log)

                env_context = {
                    "original_goal": user_query,  
                    "path_to_id": self.state.path_to_id,
                    "id_to_path": self.state.id_to_path,
                    "working_memory": self.state.working_memory,
                    "tracker": self.tracker,
                    "agent_state": self.state,
                    "task_id": self.state.task_id 
                }
                
                if "file_ids" in args:
                    args["actual_file_ids"] = args["file_ids"]
                    args["file_paths"] = [self.state.id_to_path.get(fid) for fid in args["file_ids"] if fid in self.state.id_to_path]

                result = ToolRegistry.execute(action, args=args, context=env_context)

                # 🔴 播报完成情况
                update_task_progress(self.state.task_id, f"🏃 步数 {step_count} | 阶段: {phase}\n✅ 工具 {action} 执行完毕，整理结果进入下一轮...")

                with open(trace_file, "a", encoding="utf-8") as f:
                    f.write(f"### 3. 工具执行结果\n\n```text\n{result}\n```\n\n---\n\n")

                if self.state.is_finished:
                    # 🔴 修复：将校验关键字更改为报告生成器必然返回的 "排版研报"
                    if "排版研报" not in str(self.state.final_result) and not is_task_stopped(self.state.task_id):
                        print("\n[系统生命周期兜底] 检测到任务即将结束，但由于工具路由跑偏，最终聚合报告尚未在本地落盘！")
                        print("正在强制调起高级报告汇聚引擎...")
                        update_task_progress(self.state.task_id, "🔧 正在生成最终分析研报...")
                        from workflows.report_flow import generate_final_aggregate_reports
                        generate_final_aggregate_reports(working_memory=self.state.working_memory, tracker=self.tracker, agent_state=self.state)
                    
                    update_task_progress(self.state.task_id, "🎉 任务已圆满完成！")
                    return self.state.final_result

                print(f"[工具返回]: {result}")
                print("-" * 40)