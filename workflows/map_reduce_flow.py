# RWKV-ECRA/workflows/map_reduce_flow.py
import os
import re
from typing import List
from clients.slm_client import SLMClient
from clients.llm_client import LLMClient
from utils.file_reader import read_local_file
from utils.chunker import semantic_chunk_text, get_token_count
from config import DATA_PIPELINE, SLM_CONFIG
from utils.checkpoint import get_checkpoint, save_checkpoint
from utils.retry import retry_with_fallback
from prompts.slm_prompts import build_slm_sequential_summary_prompt, build_slm_reduce_prompt

slm_client = SLMClient()

def clean_slm_output(text: str) -> str:
    clean_str = text.strip()
    clean_str = re.sub(r"<think>.*?</think>", "", clean_str, flags=re.DOTALL)
    clean_str = clean_str.replace("</think>", "").strip()
    if "<think>" in clean_str:
        clean_str = clean_str.split("<think>")[0].strip()
        
    lines = clean_str.split('\n')
    unique_lines = []
    repeat_count = 0
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped: continue
        if line_stripped in unique_lines[-DATA_PIPELINE.get("slm_repeat_threshold", 5):]: 
            repeat_count += 1
            if repeat_count > 3:  
                unique_lines.append("\n...[重复内容截断]...")
                break
        else:
            repeat_count = 0 
        unique_lines.append(line_stripped)
    return "\n".join(unique_lines).strip()

def _sequential_assemble(reports: List[str], chunk_count: int) -> str:
    assembled_parts = []
    for i, report in enumerate(reports):
        if report and report != "无":
            assembled_parts.append(f"### 原文第 {i+1}/{chunk_count} 部分提炼\n{report}")
    return "\n\n".join(assembled_parts)

def llm_plan_execute_check_compression(text: str, original_file_tokens: int = None, tracker=None) -> str:
    max_tokens = DATA_PIPELINE.get("llm_safe_window_tokens", 60000)
    current_tokens = get_token_count(text)
    
    if current_tokens <= max_tokens:
        return text 
        
    print(f"Token 超阈值 ({current_tokens})，启动 LLM 降维压缩...")
    llm = LLMClient()
    current_text = text
    iteration = 1
    
    while get_token_count(current_text) > max_tokens and iteration <= 3:
        current_tokens = get_token_count(current_text)
        ratio_str = f"(留存: {(current_tokens/original_file_tokens)*100:.1f}%)" if original_file_tokens else ""
        print(f"降维循环 {iteration} 启动 | 压缩前: {current_tokens} Tokens {ratio_str}")
        
        sample_len = min(len(current_text) // 2, 20000) 
        sample_text = current_text[:sample_len] + "\n...[省略]...\n" + current_text[-sample_len:]
        
        plan_msg = [
            {"role": "system", "content": "制定极限提炼策略，大幅删减边缘细节并合并同类项。输出3条规则。"}, 
            {"role": "user", "content": f"{sample_text}\n请制定策略："}
        ]
        strategy = llm.chat_completion(plan_msg).content

        chunks = semantic_chunk_text(current_text, max_tokens=20000, overlap_ratio=0.0)
        compressed_pieces = []
        for chunk in chunks:
            exec_msg = [
                {"role": "system", "content": f"严格按规则提炼：\n{strategy}\n直接输出正文。"}, 
                {"role": "user", "content": chunk}
            ]
            compressed_pieces.append(llm.chat_completion(exec_msg).content)
            
        current_text = "\n\n".join(compressed_pieces)
        
        new_tokens = get_token_count(current_text)
        new_ratio_str = f"(留存: {(new_tokens/original_file_tokens)*100:.1f}%)" if original_file_tokens else ""
        print(f"降维循环 {iteration} 完成 | 压缩后: {new_tokens} Tokens {new_ratio_str}")
        
        iteration += 1
        
    return current_text

@retry_with_fallback(max_retries=3, delay=5)
def delegate_to_small_models(file_paths: List[str] = None, actual_file_ids: List[str] = None, working_memory: dict = None, tracker=None, **kwargs) -> str:
    if not file_paths: return "未传入目标文件路径"
    cfg = DATA_PIPELINE
    
    actual_focus = cfg.get("map_focus", "保持原意压缩，提取核心逻辑，严格保留所有事实性内容")
    actual_detail = cfg.get("detail_level", "详尽")
    concurrency_limit = SLM_CONFIG.get("concurrency", 16)
    reduce_group_size = cfg.get("reduce_group_size", 4) 
    llm_safe_window = cfg.get("llm_safe_window_tokens", 60000)
    final_feedback = []
    
    for idx, file_path in enumerate(file_paths):
        file_name = os.path.basename(file_path)
        file_id = actual_file_ids[idx] if actual_file_ids else f"UNKNOWN_{idx}"
        
        cached_result = get_checkpoint(file_path)
        if cached_result:
            safe_final_output = cached_result
            final_feedback.append(f"{file_name} 命中本地提炼缓存。")
        else:
            try: 
                text = read_local_file(file_path)
                original_tokens = get_token_count(text)
                print(f"提炼启动: {file_name} | 初始规模: {original_tokens} Tokens | 焦点: {actual_focus}")
            except Exception as e: 
                final_feedback.append(f"读取失败: {str(e)}")
                continue

            # Stage A: Map
            max_tokens = cfg.get("max_chunk_tokens", 800)
            text_chunks = semantic_chunk_text(text, max_tokens=max_tokens, overlap_ratio=cfg.get("overlap_ratio", 0.1))
            total_chunks = len(text_chunks)
            
            all_prompts = [build_slm_sequential_summary_prompt(chunk, i+1, total_chunks, actual_focus, actual_detail) for i, chunk in enumerate(text_chunks)]
            all_responses = []
            
            print(f"Map 阶段: 共 {total_chunks} 个切片并发处理中...")
            for i in range(0, len(all_prompts), concurrency_limit):
                batch = all_prompts[i : i + concurrency_limit]
                all_responses.extend(slm_client.batch_generate(batch, tracker=tracker))

            current_reports = [clean_slm_output(r) for r in all_responses]
            current_massive_output = _sequential_assemble(current_reports, total_chunks)
            stage_a_tokens = get_token_count(current_massive_output)
            
            ratio_a = (stage_a_tokens / original_tokens) * 100 if original_tokens > 0 else 0
            print(f"Map 阶段完成: {stage_a_tokens} Tokens (留存率 {ratio_a:.1f}%)")
            
            # Stage B: Reduce
            if stage_a_tokens > llm_safe_window:
                current_step = 1
                slm_reduce_steps = cfg.get("slm_reduce_steps", 2)
                while current_step <= slm_reduce_steps and len(current_reports) > 1:
                    grouped_prompts = []
                    for i in range(0, len(current_reports), reduce_group_size):
                        batch = current_reports[i : i + reduce_group_size]
                        batch_text = "\n\n".join([f"片段{j+1}:\n{b}" for j, b in enumerate(batch)])
                        grouped_prompts.append(build_slm_reduce_prompt(batch_text, cfg.get("reduce_rule"), actual_detail, current_step, slm_reduce_steps))
                        
                    next_responses = slm_client.batch_generate(grouped_prompts, tracker=tracker)
                    valid_responses = [clean_slm_output(r) for r in next_responses if len(clean_slm_output(r).strip()) > 5]
                    if not valid_responses: break
                        
                    current_reports = valid_responses
                    current_massive_output = _sequential_assemble(current_reports, len(current_reports))
                    current_tokens = get_token_count(current_massive_output)
                    
                    ratio_b = (current_tokens / original_tokens) * 100 if original_tokens > 0 else 0
                    print(f"Reduce 第 {current_step} 步完成: {current_tokens} Tokens (留存率 {ratio_b:.1f}%)")
                    
                    if current_tokens <= llm_safe_window: break
                    current_step += 1

            # Stage C: LLM Final Check
            safe_final_output = llm_plan_execute_check_compression(current_massive_output, original_file_tokens=original_tokens, tracker=tracker)
            
            final_tokens = get_token_count(safe_final_output)
            final_ratio = (final_tokens / original_tokens) * 100 if original_tokens > 0 else 0
            print(f"提炼结束: 最终保留 {final_tokens} Tokens (总压缩留存率: {final_ratio:.1f}%)")

            save_checkpoint(file_path, safe_final_output)

        if working_memory is not None:
            working_memory[f"Summary_{file_id}"] = safe_final_output
            working_memory[f"Path_{file_id}"] = file_name
            working_memory[f"AbsPath_{file_id}"] = file_path 
            
        final_feedback.append(f"{file_name} 全文提取完成，已载入系统记忆区。")

    return "\n".join(final_feedback)