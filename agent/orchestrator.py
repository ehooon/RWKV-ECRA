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
    refined_query: str = ""  
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
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        active_query = self.refined_query if self.refined_query else self.user_query
        
        env_lines = [
            "【挂载模块: 任务环境】",
            f"- 系统时间: {current_time_str}", 
            f"- 当前执行目标: {active_query}"
        ]
        return "\n".join(env_lines)

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
        lines.append("【工作指引】: 请继续检查并收集其他缺漏情报；如果所有核心事实均已齐备，请立即调用 generate_final_aggregate_reports 进入最终聚合。")
            
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

        # UI 中文映射字典
        PHASE_MAP = {
            "DISCOVERY": "🔍 探测与发现",
            "EXTRACTION": "📑 深度提取",
            "SYNTHESIS": "🧠 聚合适成"
        }
        ACTION_MAP = {
            "search_local_file": "检索沙盒文件",
            "preview_document_content": "试读文档摘要",
            "delegate_to_small_models": "调度小模型提炼全文",
            "query_checkpoint_via_slm": "执行记忆区细节捞针",
            "batch_process_individual_reports": "归档单篇独立报告",
            "compress_working_memory": "执行工作记忆压缩",
            "generate_final_aggregate_reports": "排版聚合最终研报",
            "execute_web_search": "执行互联网检索",
            "finish_task": "任务逻辑闭环退出",
            "none": "思考下一步方向"
        }

        progress_log = []
        def push_progress(msg: str):
            progress_log.append(msg)
            update_task_progress(self.state.task_id, "\n".join(progress_log))

        push_progress("🚀 正在初始化环境，构建工作区内存与检索本地文件...")

        try:
            initial_files_json = ToolRegistry.execute("search_local_file", {"keyword": ""}, {})
            initial_files = json.loads(initial_files_json)
            for i, p in enumerate(initial_files):
                fid = f"DOC_{i+1}"
                self.state.id_to_path[fid] = p
                self.state.path_to_id[p] = fid
            self.state.last_feedback = f"系统就绪，目录中发现 {len(initial_files)} 份可用文件。"
            push_progress(f"✅ 环境就绪：感知到 {len(initial_files)} 份文件。\n")
        except Exception:
            self.state.last_feedback = "目录为空。"
            push_progress(f"✅ 环境就绪：本地沙盒目录为空。\n")
            
        step_count = 0
        MAX_STEPS = 40 
        
        while step_count < MAX_STEPS:
            if is_task_stopped(self.state.task_id):
                self.state.last_feedback = "任务已被用户手动终止。"
                self.state.is_finished = True
                self.state.final_result = "执行中止: 任务已被手动停止。"
                push_progress("\n⚠️ 任务被手动中止。")
                return self.state.final_result
                
            step_count += 1
            context_text = self.state.to_markdown_context()

            try:
                push_progress(f"🤔 [思考步数 {step_count}] 正在分析环境状态与任务缺口...")

                analysis = self.analyzer.analyze_intent_and_phase(user_query, context_text)
                phase = analysis.get("next_phase", "DISCOVERY")
                missing_info = analysis.get("missing_information", "无")
                
                if "refined_query" in analysis and analysis["refined_query"]:
                    self.state.refined_query = analysis["refined_query"]
                if "entity_audit" in analysis:
                    self.state.entity_audit.update(analysis["entity_audit"])
                    
                abandoned = analysis.get("abandoned_file_ids", [])
                if isinstance(abandoned, list) and abandoned:
                    self.state.abandoned_file_ids.update(abandoned)
                
                print(f"\n" + "="*50)
                print(f"🕵️ [Deep Research 步数 {step_count}]")
                if self.state.abandoned_file_ids:
                    print(f"🗑️ 物理屏蔽资源: {list(self.state.abandoned_file_ids)}")
                print(f"🔍 实体审计 (Entity Audit):")
                for ent, desc in analysis.get('entity_audit', {}).items():
                    print(f"  - {ent}: {desc}")
                print(f"💧 脱水目标: {self.state.refined_query}")
                print(f"🎯 缺口提取: {missing_info}")
                print(f"📍 当前阶段: {phase}")
                print("="*50)
                
                plan = self.planner.plan_next_action(user_query, analysis, context_text, phase)
                action, args = plan["action"], plan["args"]
                print(f"[工具调用]: -> {action}()")

                friendly_phase = PHASE_MAP.get(phase, phase)
                friendly_action = ACTION_MAP.get(action, action)
                
                push_progress(f"  ├─ 阶段: {friendly_phase}\n  ├─ 缺口: {missing_info}\n  └─ 动作: 调度工具 [{friendly_action}]")
                
                self.tracker.track("Routing", input_data=phase, output_data=plan)

                step_log = f"## 🏃 步骤 {step_count} (阶段: {phase})\n\n"
                step_log += "### 1. 状态分析 (Analyzer)\n"
                step_log += f"- **脱水目标**: {self.state.refined_query}\n"
                step_log += f"- **实体审计**: \n```json\n{json.dumps(analysis.get('entity_audit', {}), ensure_ascii=False, indent=2)}\n```\n"
                step_log += f"- **缺口提取**: {missing_info}\n\n"
                step_log += "### 2. 工具路由 (Planner)\n"
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

                push_progress(f"✅ [执行完成] 工具返回结果，整理进入下一轮...\n")

                with open(trace_file, "a", encoding="utf-8") as f:
                    f.write(f"### 3. 工具执行结果\n\n```text\n{result}\n```\n\n---\n\n")

                if self.state.is_finished:
                    if "排版研报" not in str(self.state.final_result) and not is_task_stopped(self.state.task_id):
                        print("\n[系统兜底] 检测到任务结束，强制调起聚合引擎...")
                        push_progress("🔧 检测到任务闭环，正在生成最终聚合研报...")
                        from workflows.report_flow import generate_final_aggregate_reports
                        generate_final_aggregate_reports(working_memory=self.state.working_memory, tracker=self.tracker, agent_state=self.state)