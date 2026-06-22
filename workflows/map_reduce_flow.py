# RWKV-ECRA/workflows/map_reduce_flow.py
import os
import re
from typing import List
from clients.slm_client import SLMClient
from clients.llm_client import LLMClient
from utils.file_reader import read_local_file
from utils.chunker import semantic_chunk_text, get_token_count
from config import DATA_PIPELINE, SLM_CONFIG, get_llm_concurrency, get_slm_concurrency
from utils.checkpoint import get_checkpoint, save_checkpoint
from utils.retry import retry_with_fallback
from prompts.slm_prompts import build_slm_sequential_summary_prompt, build_slm_reduce_prompt
from tools.registry import ToolRegistry
from utils.task_manager import is_task_stopped
import concurrent.futures

slm_client = SLMClient()

def detect_is_english(text: str, threshold: float = 0.5) -> bool:
    clean_text = re.sub(r'[\W_0-9]+', '', text)
    if not clean_text:
        return False
    eng_chars = len(re.findall(r'[a-zA-Z]', clean_text))
    return (eng_chars / len(clean_text)) > threshold

def clean_slm_output(text: str) -> str:
    clean_str = text.strip()
    clean_str = re.sub(r"<think>.*?</think>", "", clean_str, flags=re.DOTALL)
    clean_str = clean_str.replace("</think>", "").strip()
    if "<think>" in clean_str:
        clean_str = clean_str.split("<think>")[0].strip()
        
    if "\n\n" in clean_str:
        clean_str = clean_str.split("\n\n")[0].strip()
        
    for marker in ["User:", "Assistant:", "Q:", "A:", "Question:"]:
        if marker in clean_str:
            clean_str = clean_str.split(marker)[0].strip()
            
    lines = clean_str.split('\n')
    valid_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped: continue
        
        valid_lines.append(line_stripped)
        
        n = len(valid_lines)
        if n >= 4:
            is_repeating = False
            for p in range(1, (n // 2) + 1):
                repeats = 3 if p == 1 else 2  
                if n >= p * repeats:
                    pattern = valid_lines[-p:]
                    match_all = True
                    for j in range(1, repeats):
                        start_idx = n - p * (j + 1)
                        end_idx = n - p * j
                        if valid_lines[start_idx:end_idx] != pattern:
                            match_all = False
                            break
                    
                    if match_all:
                        valid_lines = valid_lines[:-p*(repeats-1)]
                        valid_lines.append("...[系统物理防浪涌：检测到模型陷入周期性复读，后续冗余已被彻底截断]...")
                        is_repeating = True
                        break
                        
            if is_repeating:
                break 
                
    return "\n".join(valid_lines).strip()

def _sequential_assemble(reports: List[str], chunk_count: int) -> str:
    assembled_parts = []
    for i, report in enumerate(reports):
        if report and report not in ["无", "None", "none", "NONE"]:
            assembled_parts.append(f"### 原文第 {i+1}/{chunk_count} 部分提炼\n{report}")
    return "\n\n".join(assembled_parts)

def llm_plan_execute_check_compression(text: str, original_file_tokens: int = None, tracker=None) -> str:
    max_tokens = DATA_PIPELINE.get("llm_safe_window_tokens", 60000)
    current_tokens = get_token_count(text)
    
    if current_tokens <= max_tokens:
        return text 
        
    print(f"\n🚨 Token 超阈值 ({current_tokens})，启动大模型(LLM)极限降维压缩...")
    llm = LLMClient()
    current_text = text
    iteration = 1
    
    while get_token_count(current_text) > max_tokens and iteration <= 3:
        current_tokens = get_token_count(current_text)
        ratio_str = f"(留存: {(current_tokens/original_file_tokens)*100:.1f}%)" if original_file_tokens else ""
        print(f"♻️ 降维循环 {iteration} 启动 | 压缩前: {current_tokens} Tokens {ratio_str}")
        
        sample_len = min(len(current_text) // 2, 20000) 
        sample_text = current_text[:sample_len] + "\n...[省略]...\n" + current_text[-sample_len:]
        
        print("   -> 正在让大模型总览全局，制定极限提炼策略...")
        plan_msg = [
            {"role": "system", "content": "制定极限提炼策略，大幅删减边缘细节并合并同类项。输出3条规则。"}, 
            {"role": "user", "content": f"{sample_text}\n请制定策略："}
        ]
        
        try:
            strategy = llm.chat_completion(plan_msg).content
        except Exception as e:
            strategy = "1. 删减边缘细节。2. 提取核心数据。3. 合并同类项。"
            print(f"   ⚠️ 策略生成超时，使用默认兜底策略: {e}")

        # 切割为 15000 Token 一个的区块
        chunks = semantic_chunk_text(current_text, max_tokens=15000, overlap_ratio=0.0)
        
        llm_concurrency = get_llm_concurrency()
        print(f"   -> 🚀 文本已切割为 {len(chunks)} 个碎片，启动滚动并发提炼 (限制并发: {llm_concurrency})...")
        
        compressed_pieces = [None] * len(chunks)
        
        def _compress_single_chunk(idx, chunk_data):
            exec_msg = [
                {"role": "system", "content": f"严格按规则提炼：\n{strategy}\n必须大幅压减字数，直接输出提炼后的正文。"}, 
                {"role": "user", "content": chunk_data}
            ]
            try:
                res = llm.chat_completion(exec_msg).content
                return idx, True, res
            except Exception as e:
                return idx, False, str(e)

        max_workers = min(len(chunks), llm_concurrency)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_compress_single_chunk, i, c) for i, c in enumerate(chunks)]
            
            for f in concurrent.futures.as_completed(futures):
                idx, success, res = f.result()
                if success:
                    compressed_pieces[idx] = res
                    print(f"      ✅ 区块 {idx+1}/{len(chunks)} 压缩完成。")
                else:
                    compressed_pieces[idx] = ""
                    print(f"      ❌ 区块 {idx+1}/{len(chunks)} 压缩失败: {res}")
            
        current_text = "\n\n".join([p for p in compressed_pieces if p])
        
        new_tokens = get_token_count(current_text)
        new_ratio_str = f"(留存: {(new_tokens/original_file_tokens)*100:.1f}%)" if original_file_tokens else ""
        print(f"✅ 降维循环 {iteration} 完成 | 压缩后: {new_tokens} Tokens {new_ratio_str}\n")
        
        iteration += 1
        
    return current_text

@ToolRegistry.register(
    name="delegate_to_small_models",
    phase="EXTRACTION",
    signature="""[Tool] delegate_to_small_models
- 功能: [核心] 文档首次处理必备！调用底层小模型对长文本进行全文深度压缩提炼，并将完整摘要永久写入系统记忆区。
- 参数: file_ids (待处理的目标文件虚拟ID数组)"""
)
@retry_with_fallback(max_retries=3, delay=5)
def delegate_to_small_models(file_paths: List[str] = None, actual_file_ids: List[str] = None, working_memory: dict = None, tracker=None, task_id: str = None, **kwargs) -> str:
    if not file_paths: return "未传入目标文件路径"
    
    cfg = DATA_PIPELINE
    concurrency_limit = get_slm_concurrency()
    slm_scheduler = kwargs.get("slm_scheduler")
    reduce_group_size = cfg.get("reduce_group_size", 4) 
    llm_safe_window = cfg.get("llm_safe_window_tokens", 60000)
    slm_reduce_steps_limit = cfg.get("slm_reduce_steps", 2)
    
    debug_dir = cfg.get("debug_directory", "./data/debug_slm")
    enable_debug = cfg.get("enable_debug_slm", False)
    if enable_debug: os.makedirs(debug_dir, exist_ok=True)
    
    final_feedback = []
    
    # 🌟 1. 状态机初始化与任务入队
    doc_states = {}
    ready_queue = [] # 存放元组: (doc_idx, stage_str, seq_idx, prompt)

    for idx, file_path in enumerate(file_paths):
        if task_id and is_task_stopped(task_id): break
        file_name = os.path.basename(file_path)
        
        cached_result = get_checkpoint(file_path)
        if cached_result:
            doc_states[idx] = {"status": "CACHED", "final_text": cached_result, "file_name": file_name, "file_path": file_path}
            final_feedback.append(f"{file_name} 命中本地提炼缓存。")
            continue
            
        try:
            text = read_local_file(file_path)
            original_tokens = get_token_count(text)
            is_eng = detect_is_english(text, threshold=cfg.get("english_ratio_threshold", 0.5))
            
            actual_focus = cfg.get("map_focus_en") if is_eng else cfg.get("map_focus", "保持原意压缩...")
            actual_reduce = cfg.get("reduce_rule_en") if is_eng else cfg.get("reduce_rule", "保持原意压缩...")
            
            chunks = semantic_chunk_text(text, max_tokens=cfg.get("max_chunk_tokens", 800), overlap_ratio=cfg.get("overlap_ratio", 0.1))
            prompts = [build_slm_sequential_summary_prompt(chunk, i+1, len(chunks), actual_focus, is_eng) for i, chunk in enumerate(chunks)]
            
            print(f"[提取挂载]: {file_name} | {original_tokens} Tokens | 切片数: {len(chunks)}")
            
            doc_states[idx] = {
                "status": "MAP",
                "file_name": file_name,
                "file_path": file_path,
                "original_tokens": original_tokens,
                "is_eng": is_eng,
                "reduce_rule": actual_reduce,
                "map_results": [None] * len(prompts),
                "current_reduce_results": []
            }
            
            for seq_idx, prompt in enumerate(prompts):
                ready_queue.append((idx, "MAP", seq_idx, prompt))
                
        except Exception as e:
            final_feedback.append(f"{file_name} 读取失败: {str(e)}")
            doc_states[idx] = {"status": "ERROR"}

    # 🌟 2. 全局动态并发调度中心 (吃满并发)
    while ready_queue:
        if task_id and is_task_stopped(task_id):
            return "执行中止: 用户已手动停止任务。"
            
        batch = ready_queue[:concurrency_limit]
        ready_queue = ready_queue[concurrency_limit:]
        
        prompts_to_send = [item[3] for item in batch]
        print(f"[SLM 并发调度] 正在发射 {len(prompts_to_send)} 个切片任务 (全局队列剩余: {len(ready_queue)})")
        
        if slm_scheduler:
            results = slm_scheduler.submit(prompts_to_send, tracker=tracker, task_id=task_id)
        else:
            results = slm_client.batch_generate(prompts_to_send, tracker=tracker, task_id=task_id)
        
        # 将结果分配回对应的文档状态中
        for (doc_idx, stage, seq_idx, _), raw_res in zip(batch, results):
            clean_res = clean_slm_output(raw_res)
            state = doc_states[doc_idx]
            
            # --- MAP 阶段结果回收 ---
            if stage == "MAP":
                state["map_results"][seq_idx] = clean_res
                
                # 如果该文档的所有 MAP 任务都已完成
                if all(r is not None for r in state["map_results"]):
                    current_reports = [r for r in state["map_results"] if r and r not in ["无", "None", "none", "NONE"]]
                    massive_output = _sequential_assemble(current_reports, len(state["map_results"]))
                    current_tokens = get_token_count(massive_output)
                    print(f"✅ [{state['file_name']}] Map 阶段组装完成 -> 体积: {current_tokens} Tokens")
                    
                    if current_tokens > llm_safe_window:
                        # 触发 REDUCE 1 入队
                        state["status"] = "REDUCE_1"
                        grouped_prompts = []
                        for i in range(0, len(current_reports), reduce_group_size):
                            b_text = "\n\n".join([f"片段{j+1}:\n{b}" for j, b in enumerate(current_reports[i : i + reduce_group_size])])
                            grouped_prompts.append(build_slm_reduce_prompt(b_text, state["reduce_rule"], 1, slm_reduce_steps_limit, state["is_eng"]))
                            
                        state["current_reduce_results"] = [None] * len(grouped_prompts)
                        for sq, p in enumerate(grouped_prompts):
                            ready_queue.append((doc_idx, "REDUCE_1", sq, p))
                    else:
                        state["status"] = "DONE_SLM"
                        state["massive_output"] = massive_output
                        
            # --- REDUCE 阶段结果回收 ---
            elif stage.startswith("REDUCE_"):
                step = int(stage.split("_")[1])
                state["current_reduce_results"][seq_idx] = clean_res
                
                # 如果当前层级的 REDUCE 任务全部完成
                if all(r is not None for r in state["current_reduce_results"]):
                    valid_reports = [r for r in state["current_reduce_results"] if len(r) > 5]
                    massive_output = _sequential_assemble(valid_reports, len(valid_reports))
                    current_tokens = get_token_count(massive_output)
                    print(f"✅ [{state['file_name']}] Reduce {step} 组装完成 -> 体积: {current_tokens} Tokens")
                    
                    if enable_debug:
                        with open(os.path.join(debug_dir, f"{state['file_name']}_02_Reduce_Step{step}.md"), "w", encoding="utf-8") as f:
                            f.write(f"# {state['file_name']} - Reduce 阶段 {step} 输出\n\n{massive_output}")
                    
                    if current_tokens > llm_safe_window and step < slm_reduce_steps_limit and len(valid_reports) > 1:
                        # 触发下一级 REDUCE 入队
                        next_step = step + 1
                        state["status"] = f"REDUCE_{next_step}"
                        grouped_prompts = []
                        for i in range(0, len(valid_reports), reduce_group_size):
                            b_text = "\n\n".join([f"片段{j+1}:\n{b}" for j, b in enumerate(valid_reports[i : i + reduce_group_size])])
                            grouped_prompts.append(build_slm_reduce_prompt(b_text, state["reduce_rule"], next_step, slm_reduce_steps_limit, state["is_eng"]))
                            
                        state["current_reduce_results"] = [None] * len(grouped_prompts)
                        for sq, p in enumerate(grouped_prompts):
                            ready_queue.append((doc_idx, f"REDUCE_{next_step}", sq, p))
                    else:
                        state["status"] = "DONE_SLM"
                        state["massive_output"] = massive_output

    # 🌟 3. 后处理落盘 (LLM 保底与状态写回)
    for idx, state in doc_states.items():
        if task_id and is_task_stopped(task_id): break
        if state["status"] == "ERROR": continue
        
        file_name = state["file_name"]
        file_path = state["file_path"]
        file_id = actual_file_ids[idx] if actual_file_ids else f"UNKNOWN_{idx}"
        
        if state["status"] == "CACHED":
            safe_final_output = state["final_text"]
        else:
            safe_final_output = llm_plan_execute_check_compression(state["massive_output"], original_file_tokens=state["original_tokens"], tracker=tracker)
            if enable_debug:
                with open(os.path.join(debug_dir, f"{file_name}_03_Final.md"), "w", encoding="utf-8") as f:
                    f.write(f"# {file_name} - 最终存入系统记忆区的内容\n\n{safe_final_output}")
            save_checkpoint(file_path, safe_final_output)
            final_feedback.append(f"{file_name} 全文提取完成，已载入系统记忆区。")

        if working_memory is not None:
            working_memory[f"Summary_{file_id}"] = safe_final_output
            working_memory[f"Path_{file_id}"] = file_name
            working_memory[f"AbsPath_{file_id}"] = file_path 
            
            if "agent_state" in kwargs and kwargs["agent_state"]:
                final_tok_est = get_token_count(safe_final_output)
                kwargs["agent_state"].memory_catalog[f"Summary_{file_id}"] = f"状态: 本地文件全文深度提炼完成 (后台物理留存 ~{final_tok_est} Tokens)"
            
    return "\n".join(final_feedback)
