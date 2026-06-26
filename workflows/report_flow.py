# RWKV-ECRA/workflows/report_flow.py
import os
import json
import re
import uuid
import concurrent.futures
from typing import List, Dict
from clients.llm_client import LLMClient
from clients.slm_client import SLMClient
from config import DATA_PIPELINE, get_llm_concurrency, get_slm_concurrency
from utils.checkpoint import clear_checkpoints_for_files
from tools.registry import ToolRegistry
from utils.chunker import get_token_count, semantic_chunk_text
from prompts.slm_prompts import build_slm_sequential_summary_prompt, build_slm_reduce_prompt
from workflows.map_reduce_flow import llm_plan_execute_check_compression, clean_slm_output, _sequential_assemble

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
- 功能: 释放内存专用工具。目前所有文档已在提炼阶段自动资产化归档，调用此工具将直接清空无用短时缓存。
- 参数: file_ids (目标本地文件ID数组)"""
)
def batch_process_individual_reports(file_paths: List[str] = None, actual_file_ids: List[str] = None, working_memory: dict = None, tracker=None, **kwargs) -> str:
    if not actual_file_ids or working_memory is None: return "参数错误。"
    freed = 0
    for fid in actual_file_ids:
        summary_key = f"Summary_{fid}"
        if summary_key in working_memory:
            del working_memory[summary_key]
            freed += 1
    return f"本地文件资产化归档核验完毕，已成功释放 {freed} 个缓存节点内存。"

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
    llm = LLMClient()
    print("启动汇聚分析流程 (强绑定隔离溯源模式)...")
    
    source_registry = {}
    static_sources = [] 
    
    if working_memory:
        for k, text in working_memory.items():
            if k.startswith("Summary_"):
                fid = k.split("_", 1)[1]
                if fid in source_registry: continue
                fname = working_memory.get(f"Path_{fid}", f"未知文档_{fid}")
                orig_path = agent_state.id_to_path.get(fid, "") if agent_state else ""
                cat = working_memory.get(f"Category_{fid}", {"main": "综合领域", "sub": "默认分类"})
                
                source_registry[fid] = {"title": os.path.splitext(fname)[0], "url": orig_path, "type": "local", "main_cat": cat["main"], "sub_cat": cat["sub"]}
                static_sources.append({"ref_ids": [fid], "content": text.strip(), "main_cat": cat["main"], "sub_cat": cat["sub"], "is_web_raw": False})
                
        web_structured = working_memory.get("__web_structured_facts__", [])
        for item in web_structured:
            web_ref_id = item.get("ref_id")
            if web_ref_id:
                source_registry[web_ref_id] = {"title": item["title"], "url": item["url"], "type": "web"}
                
        for k, text in working_memory.items():
            if k.startswith("WebFact_"):
                static_sources.append({"ref_ids": [], "content": text.strip(), "is_web_raw": True})

    audit_notes = []
    original_query = agent_state.user_query if agent_state and hasattr(agent_state, 'user_query') else kwargs.get("original_goal", "")
    active_goal = agent_state.refined_query if (agent_state and hasattr(agent_state, 'refined_query') and agent_state.refined_query) else kwargs.get("original_goal", "未指定目标")
    
    if agent_state and agent_state.entity_audit:
        for ent, status in agent_state.entity_audit.items():
            if "卸载" in status or "无关" in status or "放弃" in status:
                if ent.lower() in original_query.lower() or any(kw in ent for kw in original_query.split()):
                    audit_notes.append(f"- {ent}: 经检索与查证，确认与当前分析目标无关，已在研报生成链路中剔除。")

    if not static_sources:
        return "未找到任何本地归档文档、未归类提炼或联网事实，无法生成报告。"

    total_tokens = sum(get_token_count(s["content"]) for s in static_sources)
    token_limit = DATA_PIPELINE.get("llm_safe_window_tokens", 60000)
    
    # ==========================================
    # 2. 全局二次压缩 (复用第一次 map_reduce 流程进行二次提炼)
    # ==========================================
    if total_tokens > token_limit:
        print(f"\n🚨 [容量超限] 聚合素材池总字数 ({total_tokens} Tokens) 超出极限。")
        print("🔄 正在触发全局降维 (直接复用第一次的 map_reduce_flow.py 进行二次提炼并重新绑定)...")
        
        asset_paths = []
        origin_fids = []
        
        for src in static_sources:
            if not src.get("is_web_raw") and src.get("ref_ids"):
                fid = src["ref_ids"][0]
                asset_path = working_memory.get(f"AbsPath_{fid}")
                if asset_path and os.path.exists(asset_path):
                    asset_paths.append(asset_path)
                    origin_fids.append(fid)
                    
        if asset_paths:
            # 局部导入避免循环引用
            from workflows.map_reduce_flow import delegate_to_small_models
            
            # 直接复用 map1 提炼流程，传入原 origin_fids 保持绑定，开启 is_temporary 防止覆盖物理资产
            delegate_to_small_models(
                file_paths=asset_paths,
                actual_file_ids=origin_fids,
                working_memory=working_memory,
                tracker=tracker,
                task_id=kwargs.get("task_id") or (agent_state.task_id if agent_state else None),
                slm_scheduler=kwargs.get("slm_scheduler"),
                agent_state=agent_state,
                is_temporary=True
            )
            
            # 重新加载压缩更新后的 content 内容，保持原始属性
            new_static_sources = []
            for src in static_sources:
                if not src.get("is_web_raw") and src.get("ref_ids"):
                    fid = src["ref_ids"][0]
                    updated_content = working_memory.get(f"Summary_{fid}", "")
                    new_src = src.copy()
                    new_src["content"] = updated_content
                    new_static_sources.append(new_src)
                else:
                    new_static_sources.append(src)
                    
            static_sources = new_static_sources
            total_tokens = sum(get_token_count(s["content"]) for s in static_sources)
            print(f"   ✅ [MAP/REDUCE] 溯源重组完毕 -> 当前体积: {total_tokens} Tokens")

        # ---------------------------------------------------------
        # 💥 [防爆保障] 如果二次 MAP/REDUCE 压缩后仍旧超量，则执行按大类/小类并发写小报告的逻辑
        # ---------------------------------------------------------
        if total_tokens > token_limit:
            print(f"\n🚨 [极限超载] 经过二次 MAP/REDUCE 提炼后体积仍然超限 ({total_tokens} Tokens)！启动大类/小类分批打包与 LLM 局部小报告生成机制...")
            
            report_jobs = []
            main_cat_groups = {}
            web_sources = []
            
            for src in static_sources:
                if src.get("is_web_raw"): web_sources.append(src)
                else:
                    mc = src.get("main_cat", "综合领域")
                    if mc not in main_cat_groups: main_cat_groups[mc] = []
                    main_cat_groups[mc].append(src)
                    
            for mc, sources in main_cat_groups.items():
                mc_tokens = sum(get_token_count(s["content"]) for s in sources)
                if mc_tokens <= token_limit:
                    report_jobs.append({"title": f"【大类聚合】{mc}", "sources": sources})
                else:
                    print(f"      -> 分类 [{mc}] 依然超限，向下拆分为细分领域...")
                    sub_cat_groups = {}
                    for s in sources:
                        sc = s.get("sub_cat", "综合应用")
                        if sc not in sub_cat_groups: sub_cat_groups[sc] = []
                        sub_cat_groups[sc].append(s)
                        
                    for sc, sc_sources in sub_cat_groups.items():
                        sc_tokens = sum(get_token_count(s["content"]) for s in sc_sources)
                        if sc_tokens <= token_limit:
                            report_jobs.append({"title": f"【小类聚合】{mc}/{sc}", "sources": sc_sources})
                        else:
                            print(f"      -> 细分领域 [{mc}/{sc}] 依然超限 ({sc_tokens} Tokens)，严格按篇目进行安全打包...")
                            job_sources = []
                            job_tokens = 0
                            part_idx = 1
                            small_report_limit = token_limit // 2
                            
                            for src in sc_sources:
                                src_tokens = get_token_count(src["content"])
                                
                                if src_tokens > small_report_limit:
                                    print(f"         - 警告：单篇篇目庞大 ({src_tokens} Tokens)，触发文段裁切...")
                                    chunks = semantic_chunk_text(src["content"], max_tokens=small_report_limit, overlap_ratio=0.0)
                                    for c_idx, chunk in enumerate(chunks):
                                        chunk_src = src.copy()
                                        chunk_src["content"] = chunk
                                        report_jobs.append({"title": f"【小类聚合】{mc}/{sc} (拆分文段 {c_idx+1})", "sources": [chunk_src]})
                                else:
                                    if job_tokens + src_tokens > small_report_limit and job_sources:
                                        report_jobs.append({"title": f"【小类聚合】{mc}/{sc} (打包部分{part_idx})", "sources": job_sources})
                                        part_idx += 1
                                        job_sources = []
                                        job_tokens = 0
                                        
                                    job_sources.append(src)
                                    job_tokens += src_tokens
                                    
                            if job_sources:
                                report_jobs.append({"title": f"【小类聚合】{mc}/{sc} (打包部分{part_idx})", "sources": job_sources})
                                
            if web_sources:
                web_tokens = sum(get_token_count(s["content"]) for s in web_sources)
                if web_tokens <= token_limit:
                    report_jobs.append({"title": "【网络事实聚合】", "sources": web_sources})
                else:
                    job_sources = []
                    job_tokens = 0
                    part_idx = 1
                    small_report_limit = token_limit // 2
                    for src in web_sources:
                        src_tokens = get_token_count(src["content"])
                        if src_tokens > small_report_limit:
                            chunks = semantic_chunk_text(src["content"], max_tokens=small_report_limit, overlap_ratio=0.0)
                            for c_idx, chunk in enumerate(chunks):
                                chunk_src = src.copy()
                                chunk_src["content"] = chunk
                                report_jobs.append({"title": f"【网络事实聚合】 (拆分文段 {c_idx+1})", "sources": [chunk_src]})
                        else:
                            if job_tokens + src_tokens > small_report_limit and job_sources:
                                report_jobs.append({"title": f"【网络事实聚合】 (打包部分{part_idx})", "sources": job_sources})
                                part_idx += 1
                                job_sources = []
                                job_tokens = 0
                            job_sources.append(src)
                            job_tokens += src_tokens
                    if job_sources:
                        report_jobs.append({"title": f"【网络事实聚合】 (打包部分{part_idx})", "sources": job_sources})

            small_reports = [None] * len(report_jobs)

            def generate_small_report(job_index, job):
                parts = []
                ref_ids = []
                for s in job["sources"]:
                    if s.get("is_web_raw"):
                        parts.append(s["content"])
                    else:
                        tag_str = "".join([f"^{{{fid}}}^" for fid in s["ref_ids"]])
                        parts.append(f"【可用事实素材 {tag_str}】\n{s['content']}")
                    ref_ids.extend(s.get("ref_ids", []))
                chunk_content = "\n\n".join(parts)
                ref_ids = list(dict.fromkeys(ref_ids))

                sub_msg = [
                    {
                        "role": "system",
                        "content": (
                            f"你正在为最终大报告撰写一个【{job['title']}】分类小报告。\n"
                            "请基于输入素材，高度提炼并聚合该分类下的核心事实，写成结构化 Markdown 小报告。\n"
                            "绝对保留并照抄素材中的 ^{DOC_...}^ 和 ^[WEB_REF_...]^ 角标！没有原文支撑的关联不要写。"
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"任务目标：{active_goal}\n\n"
                            f"当前处理分类：{job['title']}\n"
                            f"{chunk_content}\n\n"
                            "请输出该分类下的高度提炼小报告："
                        )
                    }
                ]
                try:
                    report = llm.chat_completion(sub_msg).content.strip()
                    if not report: return None
                    return {
                        "ref_ids": ref_ids,
                        "content": report,
                        "main_cat": job["sources"][0].get("main_cat", ""),
                        "sub_cat": job["sources"][0].get("sub_cat", ""),
                        "is_web_raw": job["sources"][0].get("is_web_raw", False)
                    }
                except Exception as e:
                    print(f"   ❌ LLM 小报告分块 {job['title']} 生成失败: {e}")
                    return None

            if report_jobs:
                max_workers = min(len(report_jobs), get_llm_concurrency())
                print(f"   -> 准备完毕。正在并发生成 {len(report_jobs)} 份局部小报告 (分配线程数: {max_workers})...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 🔴 已修正: 使用 futures_dict 避免与下方的 future 循环命名冲突
                    futures_dict = {executor.submit(generate_small_report, idx, job): idx for idx, job in enumerate(report_jobs)}
                    for future in concurrent.futures.as_completed(futures_dict):
                        idx = futures_dict[future]
                        res = future.result()
                        if res: small_reports[idx] = res

            static_sources = [report for report in small_reports if report]
            total_tokens = sum(get_token_count(s["content"]) for s in static_sources)
            print(f"✅ LLM 分类小报告汇聚完成！最终容量锁定在: {total_tokens} Tokens。")
    else:
        print(f"\n✅ 容量安全 ({total_tokens} Tokens)，直接进入最终研报生成阶段。")

    # ==========================================
    # 3. 构造传递给大模型的 Context
    # ==========================================
    combined_text_parts = []
    for i, src in enumerate(static_sources):
        if src.get("is_web_raw"):
            combined_text_parts.append(f"📖 [情报源 {i+1} | 互联网检索]\n{src['content']}")
        else:
            tag_str = "".join([f"^{{{fid}}}^" for fid in src["ref_ids"]])
            combined_text_parts.append(f"📖 [情报源 {i+1} | 本地档案 {tag_str}]\n{src['content']}")
            
    combined_text = "\n\n".join(combined_text_parts)
    STATIC_CONTEXT_PREFIX = (
        "====================\n"
        "【全局可用情报素材池】\n"
        "(注：以下是按物理文件碎片化排列的底层素材。你必须跨越文件的物理边界，提取业务维度的核心逻辑，切勿将单篇素材生硬转为独立章节)\n\n"
        f"{combined_text}\n"
        "====================\n\n"
    )

    # ==========================================
    # 4. AST 骨架生成与并发批处理渲染
    # ==========================================
    try:
        print(">> 1/3 正在生成报告骨架树(AST)...")
        outline_sys_prompt = """任务：基于输入的目标和【全局可用情报素材池】，生成一份逻辑高度凝练的报告 AST 骨架。

【🧠 核心分析与结构排版逻辑】
1. 宏观主题聚类：你必须从杂乱无章的碎片素材中，提炼出具有逻辑穿透力的核心分析维度（例如：背景概述、核心技术、市场动态、风险挑战等）。
2. 拒绝碎纸机式大纲：绝对不要把素材池中的“每一个单篇文章”或“每一个琐碎的子标题”直接映射为顶级章节！请合并同类项，将细碎的事实收拢到宏观维度中。
3. 隔离但可共存：如果素材中包含多个相互独立、毫无关联的实体或项目，绝对不可强行编造它们之间的合作关系（防幻觉）。但你可以设立一个例如“各项目发展现状”的宏观章节，在章节内部进行分段论述，而不是为每个独立的实体都去新建一个顶级节点！
4. 采用【总-分-总】结构。
5. 【🔴 数量绝对限制】：必须高度提炼与聚合！整个大纲的节点总数必须严格控制在 3 到 7 个以内。

输出 JSON 数组格式，包含 node_id 和 title 字段。示例：
[
  {"node_id": "01_exec_summary", "title": "一、 全局执行摘要"},
  {"node_id": "02_tech_analysis", "title": "二、 核心技术与架构剖析"},
  {"node_id": "03_market_status", "title": "三、 相关实体与市场现状总览"},
  {"node_id": "04_conclusion", "title": "四、 综合研判与结论"}
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
        
        writer_sys_prompt = """任务：根据全局 AST 骨架，撰写当前被分配的【特定批次节点】的正文内容。

【极为重要的溯源要求】
你必须在阐述任何事实、结论时，严格照抄素材自带的溯源角标！
- 本地素材头部会带有类似【本地档案 ^{DOC_1}^^{DOC_2}^】的标签，你在使用该段信息时句子末尾必须照抄：^{DOC_1}^^{DOC_2}^。
- 网络素材正文自带类似 ^[WEB_REF_XXX]^ 的标签，直接照抄。
- 绝对不要虚构角标！

【防崩溃格式要求】
为了防止格式解析崩溃，绝对不要输出 JSON！
请严格使用 XML 标签 <NODE id="节点ID">包裹</NODE> 来输出每个节点的正文。
示例：
<NODE id="01_exec_summary">
这里是节点正文...由于种种原因^{DOC_1}^^{DOC_2}^^[WEB_REF_456]^。
</NODE>
<NODE id="02_tech_analysis">
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
            
            data_map = {}
            for match in re.finditer(r'<NODE id="([^"]+)">\s*(.*?)\s*</NODE>', raw_resp, re.DOTALL):
                data_map[match.group(1)] = match.group(2).strip()
                
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
        max_workers = min(len(batches), get_llm_concurrency())
        
        print(f"   -> 已将大纲拆分为 {len(batches)} 个批次，正在由 {max_workers} 个线程同时撰写正文...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 🔴 已修正: 使用 future_to_batch 以确保和下方逻辑变量名匹配
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