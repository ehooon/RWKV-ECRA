# RWKV-ECRA/workflows/report_flow.py
import os
import json
import re
from typing import List, Dict
from clients.llm_client import LLMClient
from config import DATA_PIPELINE
from utils.checkpoint import clear_checkpoints_for_files

def get_fs_category_tree() -> dict:
    tree = {}
    base_dir = os.path.join(DATA_PIPELINE["output_directory"], "分类报告体系")
    if not os.path.exists(base_dir): return tree
    
    for main_cat in os.listdir(base_dir):
        main_path = os.path.join(base_dir, main_cat)
        if not os.path.isdir(main_path): continue
            
        tree[main_cat] = {}
        for sub_cat in os.listdir(main_path):
            sub_path = os.path.join(main_path, sub_cat)
            if not os.path.isdir(sub_path): continue
                
            tree[main_cat][sub_cat] = []
            for file_name in os.listdir(sub_path):
                if file_name.endswith(".md") and not file_name.startswith("【类别聚合专刊】"):
                    tree[main_cat][sub_cat].append({
                        "name": os.path.splitext(file_name)[0],
                        "path": os.path.join(sub_path, file_name)
                    })
    return tree

def parse_md_blocks(md_text: str) -> Dict[str, str]:
    blocks = {}
    current_heading = "全局摘要"
    current_content = []
    for line in md_text.split('\n'):
        if re.match(r'^#{1,6}\s+', line.strip()):
            if current_content: blocks[current_heading] = '\n'.join(current_content).strip()
            current_heading = line.strip().lstrip('#').strip()
            current_content = []
        else:
            current_content.append(line)
    if current_content: blocks[current_heading] = '\n'.join(current_content).strip()
    return blocks

def batch_process_individual_reports(file_paths: List[str] = None, actual_file_ids: List[str] = None, working_memory: dict = None, tracker=None, **kwargs) -> str:
    if not actual_file_ids or working_memory is None: return "参数错误。"
    llm = LLMClient()
    cat_tree = get_fs_category_tree()
    output_base = DATA_PIPELINE["output_directory"]
    results = []

    for idx, fid in enumerate(actual_file_ids):
        fname = working_memory.get(f"Path_{fid}", f"doc_{fid}.md")
        fname_no_ext = os.path.splitext(fname)[0]
        summary_key = f"Summary_{fid}"
        summary = working_memory.get(summary_key, "")

        already_exists = False
        for m_cat, subs in cat_tree.items():
            for s_cat, docs in subs.items():
                if any(d["name"] == fname_no_ext for d in docs):
                    results.append(f"跳过：{fname_no_ext} 已存在于 [{m_cat}/{s_cat}]。")
                    already_exists = True
                    break
            if already_exists: break
        if already_exists or not summary: continue

        print(f"分类撰写引擎启动: {fname_no_ext}")
        existing_main_cats = list(cat_tree.keys())
        intro_text = summary[:400] + "\n...[省略]...\n" + summary[-400:] if len(summary) > 800 else summary

        main_msg = [{"role": "system", "content": "选择或创建大类名称，仅输出名称本身。"}, {"role": "user", "content": f"现有: {existing_main_cats}\n前言: {intro_text}"}]
        main_cat = re.sub(r'[^\w\u4e00-\u9fa5-]', '', llm.chat_completion(main_msg).content.strip()) or "综合领域"

        existing_sub_cats = list(cat_tree.get(main_cat, {}).keys())
        sub_msg = [{"role": "system", "content": f"为大类【{main_cat}】选择或创建小类名称，仅输出名称。"}, {"role": "user", "content": f"现有: {existing_sub_cats}\n前言: {intro_text}"}]
        sub_cat = re.sub(r'[^\w\u4e00-\u9fa5-]', '', llm.chat_completion(sub_msg).content.strip()) or "综合应用"

        report_msg = [{"role": "system", "content": f"撰写【{main_cat}-{sub_cat}】客观单篇报告。仅输出Markdown。"}, {"role": "user", "content": summary}]
        report_content = llm.chat_completion(report_msg).content

        save_dir = os.path.join(output_base, "分类报告体系", main_cat, sub_cat)
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{fname_no_ext}.md")
        with open(save_path, "w", encoding="utf-8") as f: f.write(report_content)

        if main_cat not in cat_tree: cat_tree[main_cat] = {}
        if sub_cat not in cat_tree[main_cat]: cat_tree[main_cat][sub_cat] = []
        cat_tree[main_cat][sub_cat].append({"name": fname_no_ext, "path": save_path})
        results.append(f"{fname_no_ext} 已归类并生成单篇报告。")

    working_memory["__category_tree__"] = cat_tree
    return "\n".join(results)

def generate_final_aggregate_reports(working_memory: dict = None, tracker=None, **kwargs) -> str:
    cat_tree = get_fs_category_tree()
    if not cat_tree: return "未找到已分类文件记录。"
    
    llm = LLMClient()
    output_base = os.path.join(DATA_PIPELINE["output_directory"], "分类报告体系")
    global_conclusions = []
    print("启动跨域聚合分析...")
    
    for main_cat, subs in cat_tree.items():
        for sub_cat, docs in subs.items():
            if len(docs) >= 2:
                doc_blocks_map = {}
                doc_tocs = {}
                for d in docs:
                    if os.path.exists(d.get("path", "")):
                        with open(d["path"], "r", encoding="utf-8") as f:
                            blocks = parse_md_blocks(f.read())
                            doc_blocks_map[d["name"]] = blocks
                            doc_tocs[d["name"]] = list(blocks.keys()) 

                if len(doc_tocs) < 2: continue
                
                planner_msg = [{"role": "system", "content": f"为【{main_cat}-{sub_cat}】多文档对比制定大纲。输出JSON数组:[{{\"section_title\":\"标题\", \"needed_sources\":{{\"文档A\":[\"目录\"]}}}}]"}, {"role": "user", "content": json.dumps(doc_tocs, ensure_ascii=False)}]
                
                plan_blocks = None
                for _ in range(3):
                    try:
                        resp = llm.chat_completion(planner_msg).content
                        match = re.search(r'\[.*\]', resp, re.DOTALL)
                        plan_blocks = json.loads(match.group(0)) if match else json.loads(re.sub(r'```json\n|\n```|```', '', resp).strip())
                        break
                    except: pass
                        
                if not plan_blocks: continue

                final_report_sections = []
                for block_plan in plan_blocks:
                    section_title = block_plan.get("section_title", "未命名")
                    needed_sources = block_plan.get("needed_sources", {})
                    context_fragments = [f"【{doc_name}-{h}】\n{doc_blocks_map[doc_name][h]}" for doc_name, req_h in needed_sources.items() if doc_name in doc_blocks_map for h in req_h if h in doc_blocks_map[doc_name]]
                    combined_context = "\n\n".join(context_fragments)
                    
                    if not combined_context.strip(): continue
                    writer_msg = [{"role": "system", "content": f"根据素材撰写【{section_title}】段落。纯客观，无废话。直接输出正文。"}, {"role": "user", "content": combined_context}]
                    final_report_sections.append(f"## {section_title}\n\n{llm.chat_completion(writer_msg).content}\n")

                if final_report_sections:
                    full_report_text = "\n".join(final_report_sections)
                    save_path = os.path.join(output_base, main_cat, sub_cat, f"【类别聚合专刊】_{main_cat}_{sub_cat}.md")
                    with open(save_path, "w", encoding="utf-8") as f: f.write(f"# {main_cat} - {sub_cat} 聚合分析\n\n" + full_report_text)
                    global_conclusions.append(f"【{main_cat}-{sub_cat} 综述】: {full_report_text[:1000]}")

            else:
                for d in docs:
                    if os.path.exists(d.get("path", "")):
                        with open(d["path"], "r", encoding="utf-8") as f: global_conclusions.append(f"【观点: {d['name']}】: {f.read()[:600]}")

    if global_conclusions:
        print("生成最终大视野总述...")
        global_msg = [{"role": "system", "content": "撰写全局跨域分析报告，客观呈现技术联系与平行赛道。"}, {"role": "user", "content": "\n\n".join(global_conclusions)}]
        try:
            with open(os.path.join(DATA_PIPELINE["output_directory"], "全局跨域关联分析.md"), "w", encoding="utf-8") as f:
                f.write("# 全局跨域关联分析\n\n" + llm.chat_completion(global_msg).content)
        except Exception: pass

    # 精准清理缓存
    processed_abs_paths = [v for k, v in (working_memory or {}).items() if k.startswith("AbsPath_")]
    if processed_abs_paths: clear_checkpoints_for_files(processed_abs_paths)
        
    return "跨域分析全流程完成并已归档本地硬盘。"