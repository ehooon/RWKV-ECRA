# RWKV-ECRA/agent/orchestrator.py
import os
import json
import traceback
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Set
from agent.analyzer import Analyzer
from agent.planner import Planner
from utils.tracker import EventTracker
from clients.slm_client import SLMClient
from config import TRACKING, DATA_PIPELINE, get_slm_async_batch_wait_ms, get_slm_async_enabled, get_slm_async_parallelism, get_slm_concurrency
from tools.registry import ToolRegistry
from utils.chunker import get_token_count
from utils.task_manager import is_task_stopped, update_task_progress

import tools.static_ops 
import tools.web_search
import workflows.map_reduce_flow
import workflows.memory_query_flow
import workflows.report_flow


class _SLMInputQueueItem:
    def __init__(self, request_id: str, task_id: str, index: int, content: str, tracker, endpoint: str, password: str):
        self.request_id = request_id
        self.task_id = task_id
        self.index = index
        self.content = content
        self.tracker = tracker
        self.endpoint = endpoint
        self.password = password
        self.result = ""
        self.error = None
        self.done = threading.Event()

    @property
    def backend_key(self):
        return (self.endpoint, self.password)


class SLMInputScheduler:
    """上层 SLM 输入队列：只调度原始 prompt 列表，调用方继续按 index 解析结果。"""

    def __init__(self):
        self._queue = deque()
        self._condition = threading.Condition()
        self._worker_started = False
        self._active_batches = 0

    def submit(self, contents: list[str], tracker=None, task_id: str = "") -> list[str]:
        if not contents:
            return []

        if not get_slm_async_enabled():
            return SLMClient().batch_generate(contents, tracker=tracker, task_id=task_id)

        request_id = uuid.uuid4().hex
        client = SLMClient()
        items = [
            _SLMInputQueueItem(request_id, task_id or "UNKNOWN_TASK", idx, content, tracker, client.endpoint, client.password)
            for idx, content in enumerate(contents)
        ]

        with self._condition:
            self._ensure_worker_locked()
            self._queue.extend(items)
            self._condition.notify()

        for item in items:
            item.done.wait()
            if item.error:
                raise item.error

        return [item.result for item in items]

    def _ensure_worker_locked(self):
        if self._worker_started:
            return
        worker = threading.Thread(target=self._run, name="SLMInputScheduler", daemon=True)
        worker.start()
        self._worker_started = True

    def _run(self):
        while True:
            batch = self._take_batch()
            worker = threading.Thread(target=self._process_batch, args=(batch,), name="SLMInputBatch", daemon=True)
            worker.start()

    def _take_batch(self):
        with self._condition:
            while not self._queue or self._active_batches >= get_slm_async_parallelism():
                self._condition.wait()

            max_batch = get_slm_concurrency()
            first = self._queue.popleft()
            backend_key = first.backend_key
            batch = [first]

            wait_until = time.monotonic() + (get_slm_async_batch_wait_ms() / 1000.0)
            while len(batch) < max_batch:
                scan_idx = 0
                matched = False
                while len(batch) < max_batch and scan_idx < len(self._queue):
                    candidate = self._queue[scan_idx]
                    if candidate.backend_key == backend_key:
                        batch.append(candidate)
                        del self._queue[scan_idx]
                        matched = True
                    else:
                        scan_idx += 1

                if len(batch) >= max_batch:
                    break

                remaining = wait_until - time.monotonic()
                if remaining <= 0:
                    break

                if not matched:
                    self._condition.wait(timeout=remaining)
                    if self._active_batches >= get_slm_async_parallelism():
                        break

            self._active_batches += 1
            return batch

    def _process_batch(self, batch):
        try:
            print(f"[SLM 输入队列] 发射 {len(batch)} 个片段 | 首任务: {batch[0].task_id}")
            results = SLMClient(endpoint_override=batch[0].endpoint, password_override=batch[0].password).batch_generate([item.content for item in batch])
            for item, result in zip(batch, results):
                item.result = result
                if item.tracker:
                    item.tracker.track_slm(input_prompt=item.content, output_text=result, task_id=item.task_id)
        except Exception as exc:
            for item in batch:
                item.error = exc
        finally:
            for item in batch:
                item.done.set()
            with self._condition:
                self._active_batches = max(0, self._active_batches - 1)
                self._condition.notify_all()


GLOBAL_SLM_INPUT_SCHEDULER = SLMInputScheduler()

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
        
        # 🟢 新增：把当前的实体状态挂载到环境变量中，防止大模型失忆重置
        if self.entity_audit:
            env_lines.append("- 🎯 当前实体校验状态 (Entity Audit):")
            for ent, status in self.entity_audit.items():
                env_lines.append(f"  * {ent}: {status}")
                
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

    def _mount_local_workspace(self) -> str:
        pending_items = []
        for fid, path in self.id_to_path.items():
            if fid in self.abandoned_file_ids:
                continue 
            if f"Summary_{fid}" in self.memory_catalog:
                continue 
            
            if f"Preview_{fid}" in self.memory_catalog:
                pending_items.append(f"- {fid}: {os.path.basename(path)} [已试读判定为相关，等待进行全文深度提炼]")
            else:
                pending_items.append(f"- {fid}: {os.path.basename(path)} [未读，可试读排查或直接提取]")
            
        if not pending_items:
            return ""
            
        lines = [
            "【挂载模块: 本地工作区文件 (Local Workspace)】", 
            "核心防幻觉红线：本地工作区中的文件可能是【完全相互独立、毫无关联】的实体（例如 A项目 与 B项目）。",
            "你必须客观独立地提取它们的信息。绝不要因为它们同在一个目录下，就在没有原文依据的情况下，强行脑补或捏造它们之间存在合作、使用或因果关系！",
            f"发现 {len(pending_items)} 个尚未完全消化的本地文件资源："
        ]
        lines.extend(pending_items[:15])
        if len(pending_items) > 15:
            lines.append("... (隐藏剩余文件，使用 search_local_file 检索)")
            
        return "\n".join(lines)

    def _mount_feedback(self) -> str:
        if not self.last_feedback:
            return ""
        return f"【挂载模块: 最新执行反馈】\n{self.last_feedback}"

    def to_markdown_context(self) -> str:
        modules = [
            self._mount_global_env(),
            self._mount_memory_catalog(),
            self._mount_local_workspace(),
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

        PHASE_MAP = {
            "DISCOVERY": "探测与发现",
            "EXTRACTION": "深度提取",
            "SYNTHESIS": "聚合适成"
        }
        ACTION_MAP = {
            "search_local_file": "检索本地工作区文件",
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
            push_progress(f"环境就绪：感知到 {len(initial_files)} 份文件。\n")
        except Exception:
            self.state.last_feedback = "目录为空。"
            push_progress(f"环境就绪：本地工作区目录为空。\n")
            
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
                push_progress(f"[思考步数 {step_count}] 正在分析环境状态与任务缺口...")

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
                    "task_id": self.state.task_id,
                    "slm_scheduler": GLOBAL_SLM_INPUT_SCHEDULER
                }
                
                if "file_ids" in args:
                    args["actual_file_ids"] = args["file_ids"]
                    args["file_paths"] = [self.state.id_to_path.get(fid) for fid in args["file_ids"] if fid in self.state.id_to_path]

                result = ToolRegistry.execute(action, args=args, context=env_context)
                self.state.last_feedback = f"上一步 [{action}] 执行结果:\n{result}"

                push_progress(f"✅ [执行完成] 工具返回结果，整理进入下一轮...\n")

                with open(trace_file, "a", encoding="utf-8") as f:
                    f.write(f"### 3. 工具执行结果\n\n```text\n{result}\n```\n\n---\n\n")

                if self.state.is_finished:
                    if "排版研报" not in str(self.state.final_result) and not is_task_stopped(self.state.task_id):
                        print("\n[系统兜底] 检测到任务结束，强制调起聚合引擎...")
                        push_progress("🔧 检测到任务闭环，正在生成最终聚合研报...")
                        from workflows.report_flow import generate_final_aggregate_reports
                        generate_final_aggregate_reports(working_memory=self.state.working_memory, tracker=self.tracker, agent_state=self.state)
                    
                    break

            except Exception as e:
                error_msg = f"❌ 执行步骤 {step_count} 时发生异常: {str(e)}"
                print(f"\n{error_msg}")
                traceback.print_exc()
                push_progress(error_msg)
                
                self.state.last_feedback = f"上一步执行出现严重异常: {str(e)}。请反思调用参数是否符合要求，或尝试调用其他工具。"

        if not self.state.is_finished and not is_task_stopped(self.state.task_id):
            print("\n[系统兜底] 达到最大探索步数，强制调起聚合引擎...")
            push_progress("⚠️ 达到最大思考步数限制，正在强制生成最终聚合研报...")
            from workflows.report_flow import generate_final_aggregate_reports
            generate_final_aggregate_reports(working_memory=self.state.working_memory, tracker=self.tracker, agent_state=self.state)
            
        return self.state.final_result
