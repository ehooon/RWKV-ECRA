# RWKV-ECRA/workflows/memory_query_flow.py
import os
from typing import List
from clients.slm_client import SLMClient
from utils.chunker import semantic_chunk_text
from config import DATA_PIPELINE, SLM_CONFIG
from utils.checkpoint import get_checkpoint
from prompts.slm_prompts import build_slm_query_checkpoint_prompt
from workflows.map_reduce_flow import clean_slm_output # 复用清洗逻辑
from workflows.report_flow import get_fs_category_tree # 复用树检索

slm_client = SLMClient()

def query_checkpoint_via_slm(file_paths: List[str] = None, query_instruction: str = "捞针", tracker=None, **kwargs) -> str:
    if not file_paths: return "未提供目标路径。"
    final_feedback = []
    concurrency_limit = SLM_CONFIG.get("concurrency", 16)
    cat_tree = get_fs_category_tree()
    
    for file_path in file_paths:
        fname = os.path.basename(file_path)
        fname_no_ext = os.path.splitext(fname)[0]
        memory_text = ""
        
        # 优先读成型报告
        for m_cat, subs in cat_tree.items():
            for s_cat, docs in subs.items():
                for d in docs:
                    if d["name"] == fname_no_ext and os.path.exists(d["path"]):
                        try:
                            with open(d["path"], "r", encoding="utf-8") as f:
                                memory_text = f.read()
                        except: pass
                        break
        
        # 降级读缓存
        if not memory_text:
            memory_text = get_checkpoint(file_path)

        if not memory_text:
            final_feedback.append(f"记忆区中未找到 {fname} 的记录，请先执行全文提炼。")
            continue

        print(f"记忆检索启动: {fname} | 意图: {query_instruction}")
        max_tokens = DATA_PIPELINE.get("max_chunk_tokens", 800)
        chunks = semantic_chunk_text(memory_text, max_tokens=max_tokens, overlap_ratio=0.1)
        
        prompts = [build_slm_query_checkpoint_prompt(chunk, query_instruction) for chunk in chunks]
        all_responses = []
        for i in range(0, len(prompts), concurrency_limit):
            batch = prompts[i:i+concurrency_limit]
            all_responses.extend(slm_client.batch_generate(batch, tracker=tracker))
            
        valid_answers = [clean_slm_output(r) for r in all_responses if "未找到" not in clean_slm_output(r) and len(clean_slm_output(r)) > 5]
        if not valid_answers:
            final_feedback.append(f"针对意图，未在 {fname} 记忆中发现相关内容。")
            continue
            
        merged_answer = "\n\n---\n\n".join(valid_answers)
        if len(merged_answer) > 2000:
            merged_answer = merged_answer[:2000] + "\n...(内容过多已截断)..."
        final_feedback.append(f"从 {fname} 提取结果:\n{merged_answer}")

    return "\n\n".join(final_feedback)