# RWKV-ECRA/workflows/report_flow.py
import os
import json
import re
import uuid
import concurrent.futures
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
                    fname_no_ext = os.path.splitext(file_name)[0]
                    # 静态反解：从文件名剥离出 DOC_X 烙印
                    if "___" in fname_no_ext:
                        name_part, fid = fname_no_ext.rsplit("___", 1)
                    else:
                        name_part = fname_no_ext
                        fid = "UNKNOWN"
                        
                    tree[main_cat][sub_cat].append({
                        "name": name_part,
                        "fid": fid,
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
        # 防止重复累加 ___DOC_1___DOC_1
        if "___" in fname_no_ext:
            fname_no_ext = fname_no_ext.split("___")[0]
            
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
        # 静态烙印：将 fid 烧入文件名
        save_path = os.path.join(save_dir, f"{fname_no_ext}___{fid}.md")
        with open(save_path, "w", encoding="utf-8") as f: f.write(report_content)

        if main_cat not in cat_tree: cat_tree[main_cat] = {}
        if sub_cat not in cat_tree[main_cat]: cat_tree[main_cat][sub_cat] = []
        cat_tree[main_cat][sub_cat].append({"name": fname_no_ext, "fid": fid, "path": save_path})
        
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
    static_sources = [] 
    
    # [1.1] 装载本地归档 (直接从文件树读取烙印的 DOC_X)
    if cat_tree:
        for main_cat, subs in cat_tree.items():
            for sub_cat, docs in subs.items():
                for d in docs:
                    if os.path.exists(d.get("path", "")):
                        with open(d["path"], "r", encoding="utf-8") as f: 
                            fid = d.get("fid", "UNKNOWN")
                            orig_path = agent_state.id_to_path.get(fid, "") if agent_state else ""
                            source_registry[fid] = {"title": d['name'], "url": orig_path, "type": "local"}
                            static_sources.append({"ref_ids": [fid], "content": f.read().strip()})

    # [1.2] 装载未归类的本地提炼结果
    if working_memory:
        for k, text in working_memory.items():
            if k.startswith("Summary_"):
                fid = k.split("_", 1)[1]
                fname = working_memory.get(f"Path_{fid}", f"未知文档_{fid}")
                orig_path = agent_state.id_to_path.get(fid, "") if agent_state else ""
                source_registry[fid] = {"title": os.path.splitext(fname)[0], "url": orig_path, "type": "local"}
                static_sources.append({"ref_ids": [fid], "content": text.strip()})
                
        # [1.3] 注册网络事实 (原封不动)
        web_structured = working_memory.get("__web_structured_facts__", [])
        for item in web_structured:
            web_ref_id = item.get("ref_id")
            if web_ref_id:
                source_registry[web_ref_id] = {"title": item["title"], "url": item["url"], "type": "web"}
                
        for k, text in working_memory.items():
            if k.startswith("WebFact_"):
                static_sources.append({"ref_ids": [], "content": text.strip(), "is_web_raw": True})

    # [1.5] 提取附录无关项
    audit_notes = []
    # 🟢 获取用户最初的原始指令
    original_query = agent_state.user_query if agent_state and hasattr(agent_state, 'user_query') else kwargs.get("original_goal", "")
    
    if agent_state and agent_state.entity_audit:
        for ent, status in agent_state.entity_audit.items():
            if "卸载" in status or "无关" in status or "放弃" in status:
                # 🟢 核心修复：只声明那些用户在 Prompt 中点名问了，但最后证实无关的实体
                if ent.lower() in original_query.lower() or any(kw in ent for kw in original_query.split()):
                    audit_notes.append(f"- {ent}: 经检索与查证，确认与当前分析目标无关，已在研报生成链路中剔除。")

    if not static_sources:
        return "未找到任何本地归档文档、未归类提炼或联网事实，无法生成报告。"

    # ==========================================
    # 2. Token 容量溢出应急处理机制 (同源隔离压缩)
    # ==========================================
    total_tokens = sum(get_token_count(s["content"]) for s in static_sources)
    token_limit = DATA_PIPELINE.get("llm_safe_window_tokens", 60000)
    
    if total_tokens > token_limit:
        print(f"\n🚨 [容量重载预警] 聚合素材池已达 {total_tokens} Tokens！远超 {token_limit} 限制。")
        print("🔄 [底座接管] 开始执行同源隔离折叠降维策略 (防止跨文件强行关联)...")
        
        from clients.slm_client import SLMClient
        from workflows.map_reduce_flow import clean_slm_output
        from prompts.slm_prompts import build_slm_sequential_summary_prompt
        from config import SLM_CONFIG
        
        slm = SLMClient()
        max_chunk = DATA_PIPELINE.get("max_chunk_tokens", 800)
        concurrency = SLM_CONFIG.get("concurrency", 16)
        
        local_sources = [s for s in static_sources if not s.get("is_web_raw")]
        web_sources = [s for s in static_sources if s.get("is_web_raw")]
        
        current_local = local_sources
        pass_num = 1
        
        while pass_num <= 2 and (sum(get_token_count(s["content"]) for s in current_local) + sum(get_token_count(s["content"]) for s in web_sources) > token_limit):
            print(f"   -> 启动 SLM 高速同源压缩 (第 {pass_num} 轮)...")
            
            # 🟢 核心修改 1：按来源进行严格分组 (GroupBy)，绝不跨来源组装
            grouped_sources = {}
            for src in current_local:
                # 使用 tuple(sorted) 确保 [DOC_1, DOC_2] 和 [DOC_2, DOC_1] 会被分到同一组
                key = tuple(sorted(src["ref_ids"]))
                if key not in grouped_sources:
                    grouped_sources[key] = []
                grouped_sources[key].append(src["content"])
                
            batched_blocks = []
            for key, contents in grouped_sources.items():
                combined_text = "\n\n".join(contents)
                # 切割单个来源的合并长文本，严格保持该碎片只属于这个来源
                sub_chunks = semantic_chunk_text(combined_text, max_tokens=max_chunk, overlap_ratio=0.0)
                for sc in sub_chunks:
                    batched_blocks.append({"ref_ids": list(key), "content": sc})
                    
            slm_prompts = [
                build_slm_sequential_summary_prompt(
                    b["content"], i+1, len(batched_blocks), "极限提取结论与事实。保持不同概念的独立性，严禁强行关联！绝对不要输出任何角标、序号或引用声明", "详尽"
                ) for i, b in enumerate(batched_blocks)
            ]
            
            slm_res = []
            for i in range(0, len(slm_prompts), concurrency):
                batch = slm_prompts[i:i+concurrency]
                slm_res.extend(slm.batch_generate(batch, tracker=tracker))
                
            slm_cleaned = [clean_slm_output(r) for r in slm_res]
            
            next_local = []
            for i, r in enumerate(slm_cleaned):
                if r and "无实质内容" not in r and r not in ["无", "None", "none"]:
                    next_local.append({"ref_ids": batched_blocks[i]["ref_ids"], "content": f"【提炼区块】\n{r}"})
                    
            current_local = next_local
            pass_num += 1
            curr_tokens = sum(get_token_count(s["content"]) for s in current_local)
            print(f"   ✅ SLM 第 {pass_num-1} 轮压缩完毕，本地存量缩减至: {curr_tokens} Tokens。")

        # 🟢 核心修改 2：LLM 终极暴力兜底也必须执行同源隔离
        total_tokens = sum(get_token_count(s["content"]) for s in current_local) + sum(get_token_count(s["content"]) for s in web_sources)
        if total_tokens > token_limit:
            print(f"   ⚠️ SLM 二压后仍超限 ({total_tokens} Tokens)，启用 LLM 终极同源隔离提取兜底...")
            
            # 同样进行严格的来源分组
            grouped_sources = {}
            for src in current_local:
                key = tuple(sorted(src["ref_ids"]))
                if key not in grouped_sources:
                    grouped_sources[key] = []
                grouped_sources[key].append(src["content"])
                
            llm_merged = []
            for key, contents in grouped_sources.items():
                combined_text = "\n\n".join(contents)
                # 单来源太长则分块
                llm_chunks = semantic_chunk_text(combined_text, max_tokens=token_limit // 3, overlap_ratio=0.0)
                
                for c in llm_chunks:
                    sub_msg = [{"role": "system", "content": "极限提炼核心数据。必须保持不同实体的独立性，严禁强行关联！不输出任何角标。"}, {"role": "user", "content": c}]
                    try: compressed = llm.chat_completion(sub_msg).content
                    except: compressed = ""
                    if compressed: llm_merged.append({"ref_ids": list(key), "content": compressed})
            
            current_local = llm_merged
            
        static_sources = current_local + web_sources
        total_tokens = sum(get_token_count(s["content"]) for s in static_sources)
        print(f"✅ 最终容量锁定: {total_tokens} Tokens。")

    # ==========================================
    # 3. 构造传递给大模型的 Context
    # ==========================================
    combined_text_parts = []
    for src in static_sources:
        if src.get("is_web_raw"):
            combined_text_parts.append(src["content"])
        else:
            tag_str = "".join([f"^{{{fid}}}^" for fid in src["ref_ids"]])
            combined_text_parts.append(f"【可用事实素材 {tag_str}】\n{src['content']}")
            
    combined_text = "\n\n".join(combined_text_parts)
    STATIC_CONTEXT_PREFIX = f"【可用事实素材池】\n{combined_text}\n\n---\n\n"
    active_goal = agent_state.refined_query if (agent_state and hasattr(agent_state, 'refined_query') and agent_state.refined_query) else kwargs.get("original_goal", "未指定目标")

    # ==========================================
    # 4. AST 骨架生成与并发批处理渲染
    # ==========================================
    try:
        print(">> 1/3 正在生成报告骨架树(AST)...")
        outline_sys_prompt = """任务：基于输入的目标和素材池，生成报告结构的 JSON AST 骨架。

【🚨 极端重要的防幻觉约束】
1. 实体隔离：素材池中的文件可能相互之间【毫无关联】（例如 Tilelang 只是运算基建，RWKV 是模型，如果原文没写它们结合使用，就绝对不要将它们写在一起）。
2. 拒绝强行归纳：如果在不同文件中发现了独立的项目，应该在大纲中为它们建立【互相平行的独立章节】，而不是强行合并或编造“协同效应”。
3. 采用【总-分-总】结构。无确凿原文数据支撑的维度绝对不设章节。

输出 JSON 数组格式，包含 node_id 和 title 字段。示例：
[
  {"node_id": "01_intro", "title": "一、 全局执行摘要"},
  {"node_id": "02_rwkv_status", "title": "二、 RWKV 模型现状独立分析"},
  {"node_id": "03_tilelang_status", "title": "三、 Tilelang 框架独立分析"}
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
        
        print(f">> 2/3 正在并发与分批生成报告正文 (共 {len(nodes)} 个节点) ...")
        
        # 🟢 终极防崩溃：采用 XML 标签代替 JSON 数组
        writer_sys_prompt = """任务：根据全局 AST 骨架，撰写当前被分配的【特定批次节点】的正文内容。

【极为重要的溯源要求】
你必须在阐述任何事实、结论时，严格照抄素材自带的溯源角标！
- 本地素材头部会带有类似【可用事实素材 ^{DOC_1}^^{DOC_2}^】的标签，你在使用该段信息时句子末尾必须照抄：^{DOC_1}^^{DOC_2}^。
- 网络素材正文自带类似 ^[WEB_REF_XXX]^ 的标签，直接照抄。
- 绝对不要虚构角标！

【防崩溃格式要求】
为了防止格式解析崩溃，绝对不要输出 JSON！
请严格使用 XML 标签 <NODE id="节点ID">包裹</NODE> 来输出每个节点的正文。
示例：
<NODE id="01_intro">
这里是节点正文...由于种种原因^{DOC_1}^^{DOC_2}^^[WEB_REF_456]^。
</NODE>
<NODE id="02_detail">
这里是第二个节点的正文...
</NODE>"""

        beautify_sys_prompt = """任务：对输入的文本进行 Markdown 格式重构排版。不可修改事实内容。【绝对不可修改或删除】文中的 ^{DOC_...}^ 和 ^[WEB_REF_...]^ 角标！仅输出格式化正文。"""

        def generate_node_batch(batch_nodes):
            batch_titles = [f"【{n.get('title')}】 (ID: {n.get('node_id')})" for n in batch_nodes]
            node_prompt = f"""{STATIC_CONTEXT_PREFIX}
全局骨架树：
{global_ast_skeleton_str}

当前执行批次节点：
{chr(10).join(batch_titles)}

任务目标：{active_goal}

请按 XML 格式输出以上 {len(batch_nodes)} 个节点的正文："""

            raw_resp = llm.chat_completion([{"role": "system", "content": writer_sys_prompt}, {"role": "user", "content": node_prompt}]).content.strip()
            
            # 🟢 坚如磐石的正则 XML 解析
            data_map = {}
            for match in re.finditer(r'<NODE id="([^"]+)">\s*(.*?)\s*</NODE>', raw_resp, re.DOTALL):
                data_map[match.group(1)] = match.group(2).strip()
                
            # 兜底：如果模型完全忘记了写 XML 标签，且本批次只有一个节点，直接吞并全文
            if not data_map and len(batch_nodes) == 1:
                data_map[batch_nodes[0]["node_id"]] = raw_resp
                
            result_map = {}
            for node in batch_nodes:
                node_id = node.get("node_id", "unknown")
                raw_content = data_map.get(node_id, f"(节点 {node_id} 生成异常或内容丢失)")
                
                try:
                    beautified = llm.chat_completion([{"role": "system", "content": beautify_sys_prompt}, {"role": "user", "content": raw_content}]).content.strip()
                except Exception:
                    beautified = raw_content
                    
                result_map[node_id] = {"raw": raw_content, "beautified": beautified}
            
            return result_map

        batch_size = 2
        batches = [nodes[i:i + batch_size] for i in range(0, len(nodes), batch_size)]
        
        generated_results = {}
        max_workers = min(len(batches), 6)
        
        print(f"   -> 已拆分为 {len(batches)} 个批次，分配至 {max_workers} 个线程进行并发生成...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {executor.submit(generate_node_batch, b): b for b in batches}
            for future in concurrent.futures.as_completed(future_to_batch):
                batch_ref = future_to_batch[future]
                try:
                    res_map = future.result()
                    generated_results.update(res_map)
                    print(f"   ✅ 批次完成: {', '.join([n.get('title', '')[:10]+'...' for n in batch_ref])}")
                except Exception as e:
                    print(f"   ❌ 批次失败: {e}")

        # ==========================================
        # 5. 串行映射角标（保证编号按顺序）
        # ==========================================
        global_citation_map = {} 
        global_citation_list = []
        citation_counter = [1]    
        
        final_raw_parts = []
        final_beautified_parts = []

        for node in nodes:
            node_id = node.get("node_id", "unknown")
            node_title = node.get("title", "未命名章节")
            
            node_data = generated_results.get(node_id, {})
            raw_content = node_data.get("raw", "")
            beautified_content = node_data.get("beautified", "")
            
            node_sources = []
            node_indices = []
            
            def map_and_replace_citation(match, is_web):
                ref_id = match.group(1)
                if ref_id not in source_registry:
                    # 🟢 不再吞噬！如果有幻觉角标，原样保留在文本中，防止误伤正常文本
                    return match.group(0) 
                    
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
                
                return f"^[{idx}]^" if is_web else f"^{{{idx}}}^"

            beautified_mapped = re.sub(
                r'\^?\[?(WEB_REF_[\w\-]+)\]?\^?', 
                lambda m: map_and_replace_citation(m, True), 
                beautified_content
            )
            # 🟢 兼容 DOC_X 和 UNKNOWN_X 两种前缀
            beautified_mapped = re.sub(
                r'\^?[\{\[]?((?:DOC|UNKNOWN)_[\w\-]+)[\}\]]?\^?', 
                lambda m: map_and_replace_citation(m, False), 
                beautified_mapped
            )
            
            node["raw_content"] = raw_content
            node["beautified_content"] = beautified_mapped
            node["matched_sources"] = sorted(node_sources, key=lambda x: x["index"])
            
            final_raw_parts.append(f"## {node_title}\n\n{raw_content}\n")
            final_beautified_parts.append(f"## {node_title}\n\n{beautified_mapped}\n")

        # ==========================================
        # Step 6: 最终落盘 
        # ==========================================
        print(">> 3/3 正在归档多版本报告及结构化溯源数据...")
        
        output_dir = agent_state.task_output_dir if agent_state and getattr(agent_state, 'task_output_dir', '') else DATA_PIPELINE["output_directory"]
        os.makedirs(output_dir, exist_ok=True)
        task_prefix = agent_state.task_id if agent_state and getattr(agent_state, 'task_id', '') else "最终研报"
        
        appendix_str = ""
        if audit_notes:
            appendix_str = "\n\n---\n## 附录：信息排查声明\n\n" + "\n".join(audit_notes) + "\n"

        raw_report_path = os.path.join(output_dir, f"{task_prefix}_01_原生初稿版.md")
        with open(raw_report_path, "w", encoding="utf-8") as f:
            f.write("# 最终原生分析初稿\n\n" + "\n\n".join(final_raw_parts) + appendix_str)
            
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