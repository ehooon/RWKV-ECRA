# RWKV-ECRA/workflows/report_flow.py
import os
import json
import re
import uuid
from typing import List, Dict
from clients.llm_client import LLMClient
from config import DATA_PIPELINE
from utils.checkpoint import clear_checkpoints_for_files
from tools.registry import ToolRegistry
from utils.chunker import get_token_count, semantic_chunk_text
from workflows.map_reduce_flow import llm_plan_execute_check_compression

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

@ToolRegistry.register(
    name="batch_process_individual_reports",
    phase="SYNTHESIS",
    signature="""[Tool] batch_process_individual_reports
- 功能: 本地文档归档专线。专用于将缓存区中的【本地文件(DOC_X)】提炼结果生成单篇分类报告并释放内存。
- 参数: file_ids (目标本地文件ID数组)"""
)
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

        print(f"执行分类归档: {fname_no_ext}")
        existing_main_cats = list(cat_tree.keys())
        intro_text = summary[:400] + "\n...[省略]...\n" + summary[-400:] if len(summary) > 800 else summary

        main_msg = [{"role": "system", "content": "选择或创建大类名称，仅输出名称本身。"}, {"role": "user", "content": f"现有: {existing_main_cats}\n前言: {intro_text}"}]
        main_cat = re.sub(r'[^\w\u4e00-\u9fa5-]', '', llm.chat_completion(main_msg).content.strip()) or "综合领域"

        existing_sub_cats = list(cat_tree.get(main_cat, {}).keys())
        sub_msg = [{"role": "system", "content": f"为大类【{main_cat}】选择或创建小类名称，仅输出名称。"}, {"role": "user", "content": f"现有: {existing_sub_cats}\n前言: {intro_text}"}]
        sub_cat = re.sub(r'[^\w\u4e00-\u9fa5-]', '', llm.chat_completion(sub_msg).content.strip()) or "综合应用"

        report_msg = [{"role": "system", "content": f"撰写单篇概括报告。仅输出Markdown。"}, {"role": "user", "content": summary}]
        report_content = llm.chat_completion(report_msg).content

        save_dir = os.path.join(output_base, "分类报告体系", main_cat, sub_cat)
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{fname_no_ext}.md")
        with open(save_path, "w", encoding="utf-8") as f: f.write(report_content)

        if main_cat not in cat_tree: cat_tree[main_cat] = {}
        if sub_cat not in cat_tree[main_cat]: cat_tree[main_cat][sub_cat] = []
        cat_tree[main_cat][sub_cat].append({"name": fname_no_ext, "path": save_path})
        
        if summary_key in working_memory:
            del working_memory[summary_key]
            
        results.append(f"{fname_no_ext} 已归类并生成单篇报告，内存已释放。")

    working_memory["__category_tree__"] = cat_tree
    return "\n".join(results)


@ToolRegistry.register(
    name="compress_working_memory",
    phase="SYNTHESIS",
    signature="""[Tool] compress_working_memory
- 功能: 当 Token 超出限制时，对缓存中较长的数据块执行文本压缩。
- 参数: 无"""
)
def compress_working_memory(working_memory: dict = None, tracker=None, **kwargs) -> str:
    if not working_memory: return "缓存为空。"
    compressed_count = 0
    for k, v in list(working_memory.items()):
        if k.startswith("Summary_") or k.startswith("WebFact_"):
            current_tokens = get_token_count(v)
            if current_tokens > 5000:
                print(f"[执行压缩] 正在处理数据块 {k} ...")
                new_text = llm_plan_execute_check_compression(v, original_file_tokens=current_tokens, tracker=tracker)
                working_memory[k] = new_text
                compressed_count += 1
    return f"文本压缩执行完毕，共处理了 {compressed_count} 个数据块。"


@ToolRegistry.register(
    name="generate_final_aggregate_reports",
    phase="SYNTHESIS",
    signature="""[Tool] generate_final_aggregate_reports
- 功能: 终局动作。结合所有本地与网络事实，【分步结构化】生成最终总分总分析研报。
- 参数: 无"""
)
def generate_final_aggregate_reports(working_memory: dict = None, tracker=None, agent_state=None, **kwargs) -> str:
    cat_tree = get_fs_category_tree()
    llm = LLMClient()
    
    print("启动汇聚分析流程 (强绑定隔离溯源模式)...")
    
    source_registry = {}
    global_conclusions = []
    
    # ==========================================
    # 1. 装载全局素材并分配 UUID 溯源角标
    # ==========================================
    
    # [1.1] 装载本地归档报告的观点
    if cat_tree:
        for main_cat, subs in cat_tree.items():
            for sub_cat, docs in subs.items():
                for d in docs:
                    if os.path.exists(d.get("path", "")):
                        with open(d["path"], "r", encoding="utf-8") as f: 
                            loc_ref_id = f"LOC_REF_{uuid.uuid4().hex[:8]}"
                            source_registry[loc_ref_id] = {"title": d['name'], "url": None, "type": "local"}
                            # 强制打上本地专属内联角标
                            global_conclusions.append(f"【本地文档 ^{{{loc_ref_id}}}^ 】\n{f.read().strip()}")

    # [1.2] 装载未归类的本地提炼结果
    if working_memory:
        for k, text in working_memory.items():
            if k.startswith("Summary_"):
                fid = k.split("_")[1]
                fname = working_memory.get(f"Path_{fid}", f"未知文档_{fid}")
                fname_no_ext = os.path.splitext(fname)[0]
                loc_ref_id = f"LOC_REF_{uuid.uuid4().hex[:8]}"
                source_registry[loc_ref_id] = {"title": fname_no_ext, "url": None, "type": "local"}
                global_conclusions.append(f"【本地文档 ^{{{loc_ref_id}}}^ 】\n{text.strip()}")
                
        # [1.3] 注册网络事实的元数据 (网络事实已经在 web_search 工具中被打上了 WEB_REF_XXX)
        web_structured = working_memory.get("__web_structured_facts__", [])
        for item in web_structured:
            web_ref_id = item.get("ref_id")
            if web_ref_id:
                source_registry[web_ref_id] = {"title": item["title"], "url": item["url"], "type": "web"}
                
        # [1.4] 追加已被 web_search 组装好包含 ^[WEB_REF_XXX]^ 标记的正文段落
        for k, text in working_memory.items():
            if k.startswith("WebFact_"):
                global_conclusions.append(text.strip())

    # [1.5] 提取无关项（不在提供给大模型的上下文内挂载，仅作静态附录拼装）
    audit_notes = []
    if agent_state and agent_state.entity_audit:
        for ent, status in agent_state.entity_audit.items():
            if "卸载" in status or "无关" in status or "放弃" in status:
                audit_notes.append(f"- 实体【{ent}】: 经检索证实属于无关领域，已在分析链路中物理剔除。")

    if not global_conclusions:
        return "未找到任何本地归档文档、未归类提炼或联网事实，无法生成报告。"

    combined_text = "\n\n".join(global_conclusions)
    total_tokens = get_token_count(combined_text)
    token_limit = DATA_PIPELINE.get("llm_safe_window_tokens", 60000)
    
    # ==========================================
    # 2. Token 容量溢出应急处理机制
    # ==========================================
    if total_tokens > token_limit:
        print(f"\n🚨 [容量重载预警] 聚合素材池已达 {total_tokens} Tokens！远超 {token_limit} 限制。")
        print("🔄 [底座接管] 开始执行无感折叠降维策略...")
        
        from clients.slm_client import SLMClient
        from workflows.map_reduce_flow import clean_slm_output
        from prompts.slm_prompts import build_slm_sequential_summary_prompt
        from config import SLM_CONFIG
        
        slm = SLMClient()
        max_chunk = DATA_PIPELINE.get("max_chunk_tokens", 800)
        re_chunks = semantic_chunk_text(combined_text, max_tokens=max_chunk, overlap_ratio=0.0)
        
        slm_prompts = [build_slm_sequential_summary_prompt(c, i+1, len(re_chunks), "极限提取结论与论据，并必须保留原有角标", "详尽") for i, c in enumerate(re_chunks)]
        slm_res = []
        concurrency = SLM_CONFIG.get("concurrency", 16)
        
        for i in range(0, len(slm_prompts), concurrency):
            batch = slm_prompts[i:i+concurrency]
            slm_res.extend(slm.batch_generate(batch, tracker=tracker))
            
        slm_cleaned = [clean_slm_output(r) for r in slm_res]
        combined_text = "\n\n".join([f"【提炼区块 {i+1}】\n{r}" for i, r in enumerate(slm_cleaned) if r and "无实质内容" not in r and r not in ["无", "None"]])
        total_tokens = get_token_count(combined_text)
        print(f"✅ SLM 二压完毕，体积缩减至: {total_tokens} Tokens。")

        if total_tokens > token_limit:
            llm_chunks = semantic_chunk_text(combined_text, max_tokens=token_limit // 2, overlap_ratio=0.0)
            llm_sub_reports = []
            
            for sub_idx, sub_text in enumerate(llm_chunks):
                sub_msg = [
                    {"role": "system", "content": "提取骨干事实与数据。必须严格保留原文中的 ^{LOC_REF...}^ 和 ^[WEB_REF...]^ 标签。"},
                    {"role": "user", "content": f"{sub_text}"}
                ]
                try:
                    sub_rep = llm.chat_completion(sub_msg).content
                except Exception as e:
                    sub_rep = f"[局部提炼失败]: {e}"
                llm_sub_reports.append(f"### [高密事实区块 {sub_idx+1}]\n{sub_rep}")
                
            combined_text = "\n\n" + "="*40 + "\n\n".join(llm_sub_reports)
            total_tokens = get_token_count(combined_text)
            print(f"✅ LLM 提取完毕，安全存量: {total_tokens} Tokens。")
            
    # ==========================================
    # 3. 核心节点生成 (AST 大纲 & 分步排版)
    # ==========================================
    print(f"[架构] 开始分步结构化生成最终报告 (脱水目标模式)...")
    
    STATIC_CONTEXT_PREFIX = f"【可用事实素材池】\n{combined_text}\n\n---\n\n"
    active_goal = agent_state.refined_query if (agent_state and hasattr(agent_state, 'refined_query') and agent_state.refined_query) else kwargs.get("original_goal", "未指定目标")

    try:
        print(">> 1/3 正在生成报告骨架树(AST)...")
        
        outline_sys_prompt = """任务：基于输入的目标和素材池，生成报告结构的 JSON AST 骨架。

约束要求：
1. 采用【总-分-总】结构。
2. 章节设置必须基于实际素材池中的数据，无数据支撑的维度不设章节。
3. 输出 JSON 数组格式，包含 node_id 和 title 字段。示例：
[
  {"node_id": "01_intro", "title": "一、 全局执行摘要与核心结论"},
  {"node_id": "02_detail", "title": "二、 核心趋势分析"}
]"""
        outline_resp = llm.chat_completion([
            {"role": "system", "content": outline_sys_prompt}, 
            {"role": "user", "content": STATIC_CONTEXT_PREFIX + f"任务目标：{active_goal}\n请输出 JSON 大纲："}
        ]).content
        
        match = re.search(r'\[.*\]', outline_resp, re.DOTALL)
        nodes = json.loads(match.group(0)) if match else json.loads(re.sub(r'```json\n|\n```|```', '', outline_resp).strip())
        
        ast_skeleton_lines = ["【全局报告骨架 (AST结构)】"]
        for i, n in enumerate(nodes):
            ast_skeleton_lines.append(f"{i+1}. [节点: {n.get('node_id')}] {n.get('title')}")
        global_ast_skeleton_str = "\n".join(ast_skeleton_lines)
        
        global_citation_map = {} 
        global_citation_list = []
        citation_counter = [1]    
        
        final_raw_parts = []
        final_beautified_parts = []
        
        print(f">> 2/3 正在按节点进行生成并强制继承内嵌溯源标记 (共 {len(nodes)} 个节点) ...")
        
        # 🔴 强制继承底层角标的核心提示词
        writer_sys_prompt = """任务：根据全局 AST 骨架，撰写当前被分配的【多个节点】的正文内容。

【极为重要的溯源要求】
你必须在阐述任何事实、数据、结论的句子末尾，严格保留素材池中自带的溯源角标！
- 如果引用了本地文档中的内容，照抄对应段落的：^{LOC_REF_XXX}^
- 如果引用了网络搜索的内容，照抄对应段落的：^[WEB_REF_XXX]^
- 允许多来源融合标注，例如：“营收增长了20% ^{LOC_REF_123}^^[WEB_REF_456]^。”
- 不要在 JSON 结构里搞 used_sources 数组了！将角标直接写在 content 正文中！

输出严格的 JSON 数组格式，包含每个节点的 node_id。示例：
[
  {
    "node_id": "01_intro",
    "content": "节点一的分析正文内容...营收增长了20%^{LOC_REF_123}^^[WEB_REF_456]^。"
  }
]"""

        beautify_sys_prompt = """任务：对输入的文本进行 Markdown 格式重构排版（添加粗体、列表、表格）。不可修改原始事实内容。【绝对不可修改或删除】文中的 ^{LOC_REF_...}^ 和 ^[WEB_REF_...]^ 角标！仅输出格式化正文。"""

        batch_size = 2 
        
        for i in range(0, len(nodes), batch_size):
            batch_nodes = nodes[i:i+batch_size]
            batch_titles = [f"【{n.get('title')}】 (ID: {n.get('node_id')})" for n in batch_nodes]
            print(f"   -> 正在批量处理节点: {', '.join([n.get('title') for n in batch_nodes])} ...")
            
            node_prompt = f"""{STATIC_CONTEXT_PREFIX}
全局骨架树：
{global_ast_skeleton_str}

当前执行批次节点：
{chr(10).join(batch_titles)}

任务目标：{active_goal}

请一次性输出包含以上 {len(batch_nodes)} 个节点内容的 JSON 数组："""

            raw_resp = llm.chat_completion([{"role": "system", "content": writer_sys_prompt}, {"role": "user", "content": node_prompt}]).content.strip()
            
            batch_parsed_data = []
            try:
                json_match = re.search(r'\[.*\]', raw_resp, re.DOTALL)
                clean_json_str = json_match.group(0) if json_match else raw_resp
                batch_parsed_data = json.loads(clean_json_str)
            except Exception:
                print(f"   [警告] 批次 JSON 解析失败，将使用容错降级处理。")
                
            data_map = {}
            if isinstance(batch_parsed_data, list):
                for item in batch_parsed_data:
                    if isinstance(item, dict) and "node_id" in item:
                        data_map[item["node_id"]] = item
            elif isinstance(batch_parsed_data, dict):
                 data_map = batch_parsed_data

            # 节点解析与排版
            for node in batch_nodes:
                node_id = node.get("node_id", "unknown")
                node_title = node.get("title", "未命名章节")
                
                node_data = data_map.get(node_id, {})
                raw_content = node_data.get("content", f"(节点内容缺失或生成格式异常)")
                
                # 传入 LLM 进行 Markdown 排版美化
                beautified_content = llm.chat_completion([{"role": "system", "content": beautify_sys_prompt}, {"role": "user", "content": f"{raw_content}"}]).content.strip()
                
                # ==========================================
                # 执行该节点的角标提取与全局重分配映射
                # ==========================================
                node_sources = []
                node_indices = []
                
                def map_and_replace_citation(match, is_web):
                    ref_id = match.group(1)
                    if ref_id not in source_registry:
                        return match.group(0) # 未知角标原样返回
                        
                    src_meta = source_registry[ref_id]
                    matched_title = src_meta["title"]
                    matched_url = src_meta["url"]
                    source_type = src_meta["type"]
                    
                    if ref_id not in global_citation_map:
                        idx = citation_counter[0]
                        global_citation_map[ref_id] = idx
                        global_citation_list.append({
                            "index": idx,
                            "title": matched_title,
                            "url": matched_url,
                            "type": source_type
                        })
                        citation_counter[0] += 1
                        
                    idx = global_citation_map[ref_id]
                    if idx not in node_indices:
                        node_indices.append(idx)
                        node_sources.append({
                            "index": idx,
                            "title": matched_title,
                            "url": matched_url,
                            "type": source_type
                        })
                    
                    # 按照用户要求，网络角标为 ^[X]^，本地角标为 ^{X}^
                    return f"^[{idx}]^" if is_web else f"^{{{idx}}}^"

                # ==========================================
                # 🔴 核心修复：宽容匹配大模型可能漏写的符号，但只吞噬并替换残缺的 REF_ID。
                # 完美保留正文合法的文字与普通中括号 [2]，例如：[2][WEB_REF_XXX]^ -> [2]^[idx]^
                # ==========================================
                beautified_mapped = re.sub(
                    r'\^?\[?(WEB_REF_[\w\-]+)\]?\^?', 
                    lambda m: map_and_replace_citation(m, True), 
                    beautified_content
                )
                beautified_mapped = re.sub(
                    r'\^?[\{\[]?(LOC_REF_[\w\-]+)[\}\]]?\^?', 
                    lambda m: map_and_replace_citation(m, False), 
                    beautified_mapped
                )
                
                node["raw_content"] = raw_content
                node["beautified_content"] = beautified_mapped
                # 记录该节点引用了哪些资料，用于给前端返回 JSONL 溯源结构
                node["matched_sources"] = sorted(node_sources, key=lambda x: x["index"])
                
                final_raw_parts.append(f"## {node_title}\n\n{raw_content}\n")
                final_beautified_parts.append(f"## {node_title}\n\n{beautified_mapped}\n")

        # ==========================================
        # Step 4: 最终落盘 (生成引用尾页并写文件)
        # ==========================================
        print(">> 3/3 正在归档多版本报告及结构化溯源数据...")
        
        output_dir = agent_state.task_output_dir if agent_state and getattr(agent_state, 'task_output_dir', '') else DATA_PIPELINE["output_directory"]
        os.makedirs(output_dir, exist_ok=True)
        task_prefix = agent_state.task_id if agent_state and getattr(agent_state, 'task_id', '') else "最终研报"
        
        # 组装附录（被阻断和无关的实体说明）
        appendix_str = ""
        if audit_notes:
            appendix_str = "\n\n---\n## 附录：信息排查声明\n\n" + "\n".join(audit_notes) + "\n"

        # 1. 原始版 MD
        raw_report_path = os.path.join(output_dir, f"{task_prefix}_01_原生初稿版.md")
        with open(raw_report_path, "w", encoding="utf-8") as f:
            f.write("# 最终原生分析初稿\n\n" + "\n\n".join(final_raw_parts) + appendix_str)
            
        # 2. 排版版 MD
        beautified_report_path = os.path.join(output_dir, f"{task_prefix}_02_深度排版溯源版.md")
        full_beautified = "# 最终深度分析研报\n\n" + "\n\n".join(final_beautified_parts)
        
        reference_md = "\n\n---\n## 📚 结论与论据参考索引\n\n"
        if global_citation_list:
            for cite in sorted(global_citation_list, key=lambda x: x["index"]):
                if cite["type"] == "web":
                    reference_md += f"{cite['index']}. [🔗网络来源] [{cite['title']}]({cite['url']})\n"
                else:
                    reference_md += f"{cite['index']}. [📄本地文档] {cite['title']}\n"
        else:
            reference_md += "*(本次研报生成未触发明确的源文引用角标)*\n"
            
        with open(beautified_report_path, "w", encoding="utf-8") as f:
            f.write(full_beautified + reference_md + appendix_str)

        # 3. JSONL 数据溯源备份 (前端结构化读取展示用)
        jsonl_path = os.path.join(output_dir, f"{task_prefix}_03_结构化溯源数据.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "record_type": "global_citation_map", 
                "data": global_citation_list
            }, ensure_ascii=False) + "\n")
            
            for node in nodes:
                f.write(json.dumps({
                    "record_type": "report_node",
                    "node_id": node.get("node_id", "unknown"),
                    "title": node.get("title", "unknown"),
                    "content": node.get("beautified_content", ""),
                    "sources": node.get("matched_sources", []) 
                }, ensure_ascii=False) + "\n")
                
            f.write(json.dumps({
                "record_type": "final_beautified_markdown",
                "content": full_beautified + reference_md + appendix_str
            }, ensure_ascii=False) + "\n")

        print(f"[归档成功] 高级排版及解耦溯源报告: {beautified_report_path}")
        print(f"[归档成功] JSONL 零幻觉映射结构树: {jsonl_path}")
            
        # 内存释放与状态完结
        processed_abs_paths = [v for k, v in (working_memory or {}).items() if k.startswith("AbsPath_")]
        if processed_abs_paths: clear_checkpoints_for_files(processed_abs_paths)
        
        if agent_state:
            agent_state.is_finished = True
            agent_state.final_result = f"极致分析完成！\n排版研报: {beautified_report_path}\n精准解耦溯源 JSONL: {jsonl_path}"
            
        return "执行结束"
        
    except Exception as e: 
        error_info = f"报告汇聚生成失败: {e}"
        print(error_info)
        return error_info