# RWKV-ECRA/workflows/memory_query_flow.py
import os
from typing import List
from clients.slm_client import SLMClient
from utils.chunker import semantic_chunk_text
from config import DATA_PIPELINE, get_slm_concurrency
from prompts.slm_prompts import build_slm_query_checkpoint_prompt
from workflows.map_reduce_flow import clean_slm_output
from tools.registry import ToolRegistry
from utils.file_reader import read_local_file

slm_client = SLMClient()

@ToolRegistry.register(
    name="query_checkpoint_via_slm",
    phase="EXTRACTION",
    signature="""[Tool] query_checkpoint_via_slm
- 功能: [全量原文档捞针] 直接对指定的原文件进行高并发切片扫读，提取极其微小或被忽略的细节事实。
- 参数: file_ids (目标文件虚拟ID数组), query_instruction (捞针问题)"""
)
def query_checkpoint_via_slm(file_paths: List[str] = None, query_instruction: str = "捞针", tracker=None, **kwargs) -> str:
    if not file_paths: return "未提供目标路径。"
    final_feedback = []
    concurrency_limit = get_slm_concurrency()
    task_id = kwargs.get("task_id")
    slm_scheduler = kwargs.get("slm_scheduler")
    
    ready_queue = []
    doc_states = {}
    
    for doc_idx, file_path in enumerate(file_paths):
        fname = os.path.basename(file_path)
        
        try:
            # ======== 🔴 核心重构：彻底抛弃压缩资产，直接读取绝对原始文件 ========
            raw_text = read_local_file(file_path)
        except Exception as e:
            final_feedback.append(f"读取原始文件 {fname} 失败: {str(e)}")
            continue

        if not raw_text.strip():
            final_feedback.append(f"原始文件 {fname} 内容为空。")
            continue

        print(f"[原始文本并发捞针]: {fname} | 意图: {query_instruction}")
        
        # 将原始长文本暴力切片，准备利用 SLM 的高并发进行地毯式排查
        chunks = semantic_chunk_text(raw_text, max_tokens=DATA_PIPELINE.get("max_chunk_tokens", 800), overlap_ratio=0.1)
        
        if not chunks:
            final_feedback.append(f"原始文件 {fname} 无法切分出有效内容块。")
            continue
            
        prompts = [build_slm_query_checkpoint_prompt(chunk, query_instruction) for chunk in chunks]
        
        doc_states[doc_idx] = {
            "fname": fname,
            "results": [None] * len(prompts)
        }
        
        for seq_idx, prompt in enumerate(prompts):
            ready_queue.append((doc_idx, seq_idx, prompt))

    if not ready_queue:
        return "\n\n".join(final_feedback) if final_feedback else "操作忽略，无可用数据块。"

    # ======== 发射 SLM 全量并发捞针任务 ========
    for i in range(0, len(ready_queue), concurrency_limit):
        batch = ready_queue[i : i + concurrency_limit]
        prompts_to_send = [item[2] for item in batch]
        
        if slm_scheduler:
            results = slm_scheduler.submit(prompts_to_send, tracker=tracker, task_id=task_id)
        else:
            results = slm_client.batch_generate(prompts_to_send, tracker=tracker, task_id=task_id)
        
        for (doc_idx, seq_idx, _), raw_res in zip(batch, results):
            doc_states[doc_idx]["results"][seq_idx] = clean_slm_output(raw_res)

    # ======== 回收并组装针尖数据 ========
    for doc_idx, state in doc_states.items():
        # 过滤掉所有回答“未找到”、“无”的噪音区块
        valid_answers = [r for r in state["results"] if r and "未找到" not in r and "无实质内容" not in r and len(r) > 5]
        
        if not valid_answers:
            final_feedback.append(f"针对意图，未在 {state['fname']} 原文中发现相关内容。")
        else:
            merged_answer = "\n\n---\n\n".join(valid_answers)
            if len(merged_answer) > 2000:
                merged_answer = merged_answer[:2000] + "\n...(针尖内容过多已截断)..."
            final_feedback.append(f"从 {state['fname']} 原始文本中提取到的细节:\n{merged_answer}")

    return "\n\n".join(final_feedback)