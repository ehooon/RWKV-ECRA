# RWKV-ECRA/workflows/memory_query_flow.py
import os
from typing import List
from clients.slm_client import SLMClient
from utils.chunker import semantic_chunk_text
from config import DATA_PIPELINE, get_slm_concurrency
from utils.checkpoint import get_checkpoint
from prompts.slm_prompts import build_slm_query_checkpoint_prompt
from workflows.map_reduce_flow import clean_slm_output
from workflows.report_flow import get_fs_category_tree
from tools.registry import ToolRegistry

slm_client = SLMClient()

@ToolRegistry.register(
    name="query_checkpoint_via_slm",
    phase="EXTRACTION",
    signature="""[Tool] query_checkpoint_via_slm
- 功能: [局部问答] 仅限已提炼进记忆区的文件。针对特定细节进行捞针提问，严禁用于首次全文阅读。
- 参数: file_ids (目标文件虚拟ID数组), query_instruction (捞针问题)"""
)
def query_checkpoint_via_slm(file_paths: List[str] = None, query_instruction: str = "捞针", tracker=None, **kwargs) -> str:
    if not file_paths: return "未提供目标路径。"
    final_feedback = []
    concurrency_limit = get_slm_concurrency()
    task_id = kwargs.get("task_id")
    slm_scheduler = kwargs.get("slm_scheduler")
    cat_tree = get_fs_category_tree()
    
    # 🌟 1. 铺平所有文件的并发任务队列
    ready_queue = []
    doc_states = {}
    
    for doc_idx, file_path in enumerate(file_paths):
        fname = os.path.basename(file_path)
        fname_no_ext = os.path.splitext(fname)[0]
        memory_text = ""
        
        # 尝试从分类归档目录反向拉取
        for m_cat, subs in cat_tree.items():
            for s_cat, docs in subs.items():
                for d in docs:
                    if d["name"] == fname_no_ext and os.path.exists(d["path"]):
                        try:
                            with open(d["path"], "r", encoding="utf-8") as f:
                                memory_text = f.read()
                        except: pass
                        break
        
        # 若不在归档中，从缓存检查
        if not memory_text: memory_text = get_checkpoint(file_path)

        if not memory_text:
            final_feedback.append(f"记忆区中未找到 {fname} 的记录，请先执行全文提炼。")
            continue

        print(f"[记忆检索挂载]: {fname} | 意图: {query_instruction}")
        chunks = semantic_chunk_text(memory_text, max_tokens=DATA_PIPELINE.get("max_chunk_tokens", 800), overlap_ratio=0.1)
        prompts = [build_slm_query_checkpoint_prompt(chunk, query_instruction) for chunk in chunks]
        
        doc_states[doc_idx] = {
            "fname": fname,
            "results": [None] * len(prompts)
        }
        
        for seq_idx, prompt in enumerate(prompts):
            ready_queue.append((doc_idx, seq_idx, prompt))

    if not ready_queue:
        return "\n\n".join(final_feedback) if final_feedback else "操作忽略，无可用数据块。"

    # 🌟 2. 发射全局并发
    for i in range(0, len(ready_queue), concurrency_limit):
        batch = ready_queue[i : i + concurrency_limit]
        prompts_to_send = [item[2] for item in batch]
        
        if slm_scheduler:
            results = slm_scheduler.submit(prompts_to_send, tracker=tracker, task_id=task_id)
        else:
            results = slm_client.batch_generate(prompts_to_send, tracker=tracker, task_id=task_id)
        
        for (doc_idx, seq_idx, _), raw_res in zip(batch, results):
            doc_states[doc_idx]["results"][seq_idx] = clean_slm_output(raw_res)

    # 🌟 3. 回收组装答案
    for doc_idx, state in doc_states.items():
        valid_answers = [r for r in state["results"] if r and "未找到" not in r and len(r) > 5]
        
        if not valid_answers:
            final_feedback.append(f"针对意图，未在 {state['fname']} 记忆中发现相关内容。")
        else:
            merged_answer = "\n\n---\n\n".join(valid_answers)
            if len(merged_answer) > 2000:
                merged_answer = merged_answer[:2000] + "\n...(内容过多已截断)..."
            final_feedback.append(f"从 {state['fname']} 提取结果:\n{merged_answer}")

    return "\n\n".join(final_feedback)
