import os
import json
import re
from clients.slm_client import SLMClient
from utils.file_reader import read_local_file
from utils.chunker import semantic_chunk_text, get_token_count
from clients.llm_client import LLMClient
from config import DATA_PIPELINE, SLM_CONFIG
from utils.checkpoint import get_checkpoint, save_checkpoint, clear_all_checkpoints
from utils.retry import retry_with_fallback
from prompts.slm_prompts import (
    build_slm_preview_prompt, 
    build_slm_map_prompt, 
    build_slm_extract_prompt, 
    build_slm_reduce_prompt
)

slm_client = SLMClient()

def clean_slm_output(text: str) -> str:
    """🚨 极度鲁棒的跳过 <think> 标签机制，并加入死循环复读硬拦截"""
    clean_str = text.strip()
    clean_str = re.sub(r"<think>.*?</think>", "", clean_str, flags=re.DOTALL)
    clean_str = clean_str.replace("</think>", "").strip()
    if "<think>" in clean_str:
        clean_str = clean_str.split("<think>")[0].strip()
        
    # === 新增：防死循环 / 幻觉复读拦截器 ===
    lines = clean_str.split('\n')
    unique_lines = []
    repeat_count = 0
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # 检测是否与最近的行发生严重重复
        if line_stripped in unique_lines[-5:]: 
            repeat_count += 1
            if repeat_count > 3:  # 容忍最多连续重复 3 次
                unique_lines.append("\n...[系统安全拦截：检测到局部重复生成，已截断]...")
                break
        else:
            repeat_count = 0 
            
        unique_lines.append(line_stripped)
        
    return "\n".join(unique_lines).strip()

def preview_document_content(file_path: str, tracker=None, **kwargs) -> str:
    if "[" in file_path and "]" in file_path:
        try:
            paths = json.loads(file_path)
            file_path = paths[0] if isinstance(paths, list) and paths else file_path
        except: pass
            
    try: text = read_local_file(file_path)
    except Exception as e: return f"读取失败: {str(e)}"
    if not text.strip(): return f"警告：文件 {file_path} 内容为空。"

    max_tokens = DATA_PIPELINE.get("max_chunk_tokens", 800)
    text_chunks = semantic_chunk_text(text, max_tokens=max_tokens, overlap_ratio=0.0)
    
    if len(text_chunks) <= 3:
        sample_chunks = text_chunks
        labels = [f"切片 {i+1}" for i in range(len(text_chunks))]
    else:
        mid_idx = len(text_chunks) // 2
        sample_chunks = [text_chunks[0], text_chunks[mid_idx], text_chunks[-1]]
        labels = ["【开头部分】", "【中间部分】", "【结尾部分】"]

    prompts = [build_slm_preview_prompt(chunk) for chunk in sample_chunks]
    preview_responses = slm_client.batch_generate(prompts, tracker=tracker)
    
    preview_results = []
    for i, resp in enumerate(preview_responses):
        clean_str = clean_slm_output(resp)
        if len(clean_str) > 5:
            preview_results.append(f" - {labels[i]}: {clean_str}")

    if not preview_results: return "试读失败，未返回有效摘要。"

    return (
        f"【文件画像构建报告：{os.path.basename(file_path)}】\n"
        f"📊 物理规模: 共 {len(text_chunks)} 个切片\n"
        f"👁️ 语义抽样探测:\n" + "\n".join(preview_results)
    )

def search_local_file(keyword: str = "", tracker=None, **kwargs) -> str:
    base_dir = DATA_PIPELINE["input_directory"]
    allowed_exts = DATA_PIPELINE["allowed_extensions"]
    max_tokens = DATA_PIPELINE.get("max_chunk_tokens", 800)
    
    keyword = keyword.strip()
    found_files = []
    total_files = 0
    file_details = []

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in allowed_exts and (not keyword or keyword.lower() in file.lower()):
                file_path = os.path.abspath(os.path.join(root, file))
                found_files.append(file_path)
                size_bytes = os.path.getsize(file_path)
                est_chars = max(1, size_bytes // 2)
                est_chunks = max(1, est_chars // int(max_tokens * 1.5))
                total_files += 1
                file_details.append(f"  - {file} | 预估切片(Chunk): {est_chunks}块")
                
    if not found_files: return f"未找到匹配的文件。"
        
    overview = f"✅ 总计找到文件: {total_files} 个\n【详情清单】:\n" + "\n".join(file_details)
    overview += f"\n\n<!-- FILE_PATHS: {json.dumps(found_files, ensure_ascii=False)} -->"
    return overview

@retry_with_fallback(max_retries=3, delay=5)
def delegate_to_small_models(file_path: str, doc_topology: str, map_focus: str, reduce_rule: str, detail_level: str, slm_reduce_steps: int = 2, target_token_limit: int = 32000, tracker=None, **kwargs) -> str:
    if "[" in file_path and "]" in file_path:
        try:
            paths = json.loads(file_path)
            file_path = paths[0] if isinstance(paths, list) and paths else file_path
        except: pass

    params_for_cache = {"doc_topology": doc_topology, "map_focus": map_focus, "reduce_rule": reduce_rule}
    cached_result = get_checkpoint(file_path, params_for_cache)
    if cached_result:
        return f"⚡ [断点命中] {os.path.basename(file_path)} 的详尽提取已存在于外置缓存。\n速览内容:\n{cached_result[:1500]}..."

    try: text = read_local_file(file_path)
    except Exception as e: return f"读取失败: {str(e)}"

    max_tokens = DATA_PIPELINE.get("max_chunk_tokens", 800)
    text_chunks = semantic_chunk_text(text, max_tokens=max_tokens, overlap_ratio=DATA_PIPELINE.get("overlap_ratio", 0.1))
    
    # ==========================
    # 双轨提取并行下发 (Summary + Facts)
    # ==========================
    summary_prompts = []
    extract_prompts = []
    
    for chunk_str in text_chunks:
        summary_prompts.append(build_slm_map_prompt(chunk_str, map_focus, detail_level))
        extract_prompts.append(build_slm_extract_prompt(chunk_str, map_focus))
        
    all_prompts = summary_prompts + extract_prompts
    concurrency_limit = SLM_CONFIG.get("concurrency", 16)
    all_responses = []
    
    print(f"🚀 [双轨 Map] 对 {os.path.basename(file_path)} 启动逻辑提炼与事实提取并行处理...")
    for i in range(0, len(all_prompts), concurrency_limit):
        batch = all_prompts[i : i + concurrency_limit]
        all_responses.extend(slm_client.batch_generate(batch, tracker=tracker))

    chunk_count = len(text_chunks)
    raw_summaries = all_responses[:chunk_count]
    raw_facts = all_responses[chunk_count:]

    current_reports = [clean_slm_output(r) for r in raw_summaries if len(clean_slm_output(r).strip()) > 5]
    
    valid_facts = []
    for f in raw_facts:
        f_clean = clean_slm_output(f)
        if len(f_clean) > 2 and f_clean != "无" and "没有" not in f_clean:
            valid_facts.append(f_clean)

    # ==========================
    # Phase 2: Summary 轨道的 Reduce 合并
    # ==========================
    reduce_max_tokens = 3500 # 🚨 限制合并 Token 以适配 4K 窗口
    current_step = 1
    while current_step <= slm_reduce_steps:
        total_current_tokens = sum(get_token_count(r) for r in current_reports)
        if total_current_tokens <= target_token_limit or len(current_reports) <= 1: break
            
        grouped_prompts = []
        i = 0
        while i < len(current_reports):
            batch = [current_reports[i]]
            current_batch_tokens = get_token_count(current_reports[i])
            i += 1
            while i < len(current_reports) and current_batch_tokens + get_token_count(current_reports[i]) < reduce_max_tokens:
                batch.append(current_reports[i])
                current_batch_tokens += get_token_count(current_reports[i])
                i += 1
                
            batch_text = "\n\n---\n\n".join(batch)
            grouped_prompts.append(build_slm_reduce_prompt(batch_text, reduce_rule, detail_level, current_step, slm_reduce_steps))
            
        next_responses = slm_client.batch_generate(grouped_prompts, tracker=tracker)
        valid_responses = [clean_slm_output(r) for r in next_responses if len(clean_slm_output(r).strip()) > 5]
        
        if not valid_responses: break
        current_reports = valid_responses
        current_step += 1

    # ==========================
    # 组装保真数据并返回给 LLM 丰满的速览摘要
    # ==========================
    final_logic = "\n\n".join(current_reports)
    final_facts_str = "\n".join(valid_facts) if valid_facts else "*(无绝对关键事实提取)*"
    
    massive_final_output = (
        f"### 📍 核心关键事实提取清册 (保真数据)\n{final_facts_str}\n\n"
        f"### 🧠 深度逻辑推演报告\n{final_logic}"
    )
    
    save_checkpoint(file_path, params_for_cache, massive_final_output)
    
    # 🚨 将反馈给大模型的文本放宽到 1500 字符，大模型将以此为素材亲自撰写最终报告
    llm_preview = massive_final_output[:1500] + "\n...(其余内容已存入缓存)...\n" if len(massive_final_output) > 1500 else massive_final_output
    
    return (
        f"✅ 提取完成！处理文件: {os.path.basename(file_path)}\n\n"
        f"【核心素材速览】:\n{llm_preview}\n"
        f"*(提示：你已经获取了该文件的提炼素材，请将其纳入你的知识库用于最终出盘)*"
    )

def export_report_to_md(file_name: str, full_report_content: str, tracker=None, **kwargs) -> str:
    """🚨 优化核心：彻底抛弃 SLM 拼接，由统筹大模型(LLM)亲自撰写完整报告并直接落盘"""
    base_dir = DATA_PIPELINE["output_directory"] 
    
    if not file_name.endswith('.md'): file_name += '.md'
    out_path = os.path.abspath(os.path.join(base_dir, file_name))
    
    try:
        # 直接写盘大模型传入的优质内容
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(full_report_content)
            
        if tracker: 
            tracker.track("SubStep_ExportMD", input_data={"file_name": file_name}, output_data={"status": "success", "path": out_path})
            
        clear_all_checkpoints()
        return f"✅ 完美合并！最终综合研报已由你亲自撰写完成并落盘至：{out_path}。任务圆满结束。"
    except Exception as e:
        return f"❌ 写入 Markdown 文件失败: {str(e)}"