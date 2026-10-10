# RWKV-ECRA/workflows/report_flow.py
import os
import json
import re
import uuid
import concurrent.futures
from typing import List, Dict
from clients.llm_client import LLMClient
from clients.slm_client import SLMClient
from config import (DATA_PIPELINE, REPORT_CONFIG, get_llm_concurrency, get_slm_concurrency,
                    get_report_writer, get_section_source_binding_enabled,
                    get_rolling_context_enabled, get_rolling_context_budget)
from utils.checkpoint import clear_checkpoints_for_files
from tools.registry import ToolRegistry
from utils.chunker import get_token_count, semantic_chunk_text
from prompts.slm_prompts import (build_slm_sequential_summary_prompt, build_slm_reduce_prompt,
                                 build_slm_section_binding_prompt, build_slm_section_write_prompt,
                                 build_slm_section_merge_prompt)
from workflows.map_reduce_flow import (llm_plan_execute_check_compression, clean_slm_output,
                                       _sequential_assemble, detect_line_repetition, detect_is_english)
import contextvars
from utils.token_tracker import current_task_id
from utils.task_manager import update_task_progress

# 🧹 静态清洗:绑定关系是静态的,凡不指向合法来源的"角标形状"残留一律物理剥离
#   ^ {[32],[18]} / $^{661be5}$ / 裸 [32][18] —— 均为模型抄录素材内部参考文献编号的产物
_GHOST_BRACED = re.compile(r'\^?\{\[[^\}]*\}\^?')
_GHOST_HASH = re.compile(r'\$\^\{[0-9a-zA-Z]{4,8}\}\$')
_GHOST_BARE = re.compile(r'(?<![!\[\]\^])\[\d{1,3}(?:\]\s*\[\d{1,3})*\](?![\]\(\]\^])')
_CODE_FENCE = re.compile(r'(```[\s\S]*?```)', re.S)

def strip_ghost_citations(text: str) -> str:
    """剥离幻觉角标;围栏代码块内的内容不处理(保护 A[0][1] 之类下标)。
    合法角标(^{N}^ / ^[N]^)先占位保护, ghost 剥离到不动点后再还原。"""
    if not text:
        return text
    legit_re = re.compile(r'\^\{\d{1,3}\}\^|\^\[\d{1,3}\]\^')
    out = []
    for i, seg in enumerate(_CODE_FENCE.split(text)):
        if i % 2 == 1:
            out.append(seg)
            continue
        held = []
        def _hold(m):
            held.append(m.group(0))
            return f"\x00{len(held) - 1}\x00"
        seg = legit_re.sub(_hold, seg)
        for _ in range(4):  # 链式残留需迭代到不动点,如 ^{4}^{[32]}^{[18]}
            new = _GHOST_BRACED.sub('', seg)
            new = _GHOST_HASH.sub('', new)
            new = _GHOST_BARE.sub('', new)
            if new == seg:
                break
            seg = new
        seg = re.sub(r'\x00(\d+)\x00', lambda m: held[int(m.group(1))], seg)
        out.append(seg)
    return ''.join(out)


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

# ==========================================
# SLM 滚动溯源报告生成 (report_writer = "slm")
# ==========================================

def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if get_token_count(text) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if get_token_count(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "\n...[超出本节资料预算，已截断]..."

def _build_section_digest(title: str, content: str, max_tokens: int = 1000) -> str:
    """抽取式章节摘要：各级小标题 + 每段首句，零额外 LLM 调用"""
    points = [h for h in re.findall(r'^#{2,4}\s+(.+)$', content, flags=re.M) if h.strip() != title]
    for para in content.split('\n'):
        para = para.strip().lstrip('-*').strip()
        if not para or para.startswith('#'):
            continue
        m = re.match(r'^([^。；;\n]{4,80}[。；;])', para)
        if m:
            points.append(m.group(1))
    if not points:
        return title
    return _truncate_to_tokens(f"{title}：" + "；".join(points), max_tokens)

def _slm_submit(prompts, slm_scheduler=None, tracker=None, task_id=None, max_tokens=2400):
    if not prompts:
        return []
    if slm_scheduler:
        return slm_scheduler.submit(prompts, tracker=tracker, task_id=task_id, max_tokens=max_tokens)
    return SLMClient().batch_generate(prompts, tracker=tracker, task_id=task_id, max_tokens=max_tokens)

def _slm_clean_checked(raw: str) -> tuple:
    """清洗 SLM 输出并报告是否发生周期性复读。返回 (clean_text, is_repeating)"""
    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).replace("</think>", "").strip()
    if "<think>" in text:
        text = text.split("<think>")[0].strip()
    for marker in ["User:", "Assistant:", "Q:", "A:", "Question:"]:
        if marker in text:
            text = text.split(marker)[0].strip()
    is_repeating, lines = detect_line_repetition(text.split('\n'))
    return "\n".join(lines).strip(), is_repeating

def _build_source_pool(static_sources: list, source_registry: dict) -> list:
    """把聚合素材池整理成可供 SLM 绑定的候选清单。网络块使用合成 label，并预提取其内联 WEB_REF。"""
    pool = []
    for i, src in enumerate(static_sources):
        content = (src.get("content") or "").strip()
        if not content:
            continue
        is_web_raw = bool(src.get("is_web_raw"))
        if is_web_raw:
            label = f"WEBFACT_{i}"
            title = f"网络情报聚合块 {i+1}"
            inline_refs = list(dict.fromkeys(re.findall(r'WEB_REF_[\w\-]+', content)))
        else:
            label = src["ref_ids"][0] if src.get("ref_ids") else f"UNKNOWN_SRC_{i}"
            title = source_registry.get(label, {}).get("title", label)
            inline_refs = [r for r in (src.get("ref_ids") or []) if r != label]
        pool.append({
            "label": label,
            "ref_ids": src.get("ref_ids", []),
            "inline_refs": inline_refs,
            "title": title,
            "content": content,
            "tokens": get_token_count(content),
            "is_web_raw": is_web_raw,
            "main_cat": src.get("main_cat", ""),
            "sub_cat": src.get("sub_cat", "")
        })
    return pool

def _bind_sections_to_sources(nodes: list, source_pool: list, active_goal: str,
                              slm_scheduler=None, tracker=None, task_id=None, tid=None) -> dict:
    """SLM 绑定阶段：每个小节显式挑选相关素材 label，保证溯源确定性。解析失败回退为全量素材。"""
    label_set = {s["label"] for s in source_pool}
    candidate_lines = []
    for s in source_pool:
        preview = _truncate_to_tokens(s["content"], 200)
        candidate_lines.append(f"{s['label']} | {s['title']} | {preview}")
    candidate_str = "\n".join(candidate_lines)

    prompts = [
        build_slm_section_binding_prompt(n.get("title", "未命名章节"), active_goal, candidate_str)
        for n in nodes
    ]

    print(f"   -> 🔗 [SLM 绑定] 正在为 {len(nodes)} 个章节并发关联参考资料...")
    if tid and tid != "UNKNOWN_TASK":
        update_task_progress(tid, f"🔗 [研报生成] 小模型正在为 {len(nodes)} 个章节绑定溯源参考资料...")

    try:
        raws = _slm_submit(prompts, slm_scheduler, tracker, task_id, max_tokens=800)
    except Exception as e:
        print(f"   ⚠️ [SLM 绑定] 批量绑定异常，全部回退为全量素材: {e}")
        raws = [""] * len(prompts)

    bindings = {}
    for n, raw in zip(nodes, raws):
        nid = n.get("node_id", "unknown")
        picked = []
        try:
            clean, _ = _slm_clean_checked(raw)
            m = re.search(r'\[.*?\]', clean, re.DOTALL)
            if m:
                arr = json.loads(m.group(0))
                if isinstance(arr, list):
                    picked = [str(x) for x in arr if str(x) in label_set]
        except Exception:
            picked = []

        if not picked:
            print(f"   ⚠️ [SLM 绑定] 节点 {nid} 未选出有效素材，回退为全量素材池。")
            picked = [s["label"] for s in source_pool]
        bindings[nid] = picked
        print(f"   🔗 节点 [{nid}] 《{n.get('title', '')}》 绑定素材: {picked}")

    return bindings

def _execute_slm_jobs_with_retry(jobs: list, max_retries: int, output_tokens: int,
                                 slm_scheduler=None, tracker=None, task_id=None) -> dict:
    """并发执行 SLM 生成任务，复读/空输出自动重试，超过次数标记失败(None)。"""
    results = {}
    pending = list(jobs)
    concurrency = get_slm_concurrency()

    for attempt in range(max_retries):
        if not pending:
            break
        prompts = [j["prompt"] for j in pending]
        raws = []
        for i in range(0, len(prompts), concurrency):
            batch = prompts[i:i + concurrency]
            try:
                raws.extend(_slm_submit(batch, slm_scheduler, tracker, task_id, max_tokens=output_tokens))
            except Exception as e:
                print(f"   ❌ [SLM 研报] 批次发射异常: {e}")
                raws.extend([""] * len(batch))

        next_pending = []
        for j, raw in zip(pending, raws):
            clean, is_repeating = _slm_clean_checked(raw)
            if clean and not is_repeating:
                results[j["key"]] = clean
            else:
                reason = "周期性复读" if is_repeating else "空输出"
                print(f"   ⚠️ [SLM 研报] {j['key']} 第 {attempt + 1}/{max_retries} 次生成失败({reason})")
                next_pending.append(j)
        pending = next_pending

    for j in pending:
        results[j["key"]] = None
        print(f"   ❌ [SLM 研报] {j['key']} 重试 {max_retries} 次仍失败，已标记。")
    return results

def _generate_report_via_slm(nodes: list, static_sources: list, source_registry: dict,
                             active_goal: str, skeleton_str: str, llm, beautify_sys_prompt: str,
                             tracker=None, tid=None, task_id=None, slm_scheduler=None) -> tuple:
    """小模型滚动溯源写报告：绑定 -> 分步并行写作 -> 合并 -> (LLM 仅排版美化)。
    返回 (generated_results, bindings, source_pool)"""
    ref_budget = int(REPORT_CONFIG.get("slm_section_ref_budget_tokens", 8000))
    max_ctx = int(REPORT_CONFIG.get("slm_max_context_tokens", 16000))
    max_retries = int(REPORT_CONFIG.get("slm_section_max_retries", 3))
    output_tokens = int(REPORT_CONFIG.get("slm_report_output_tokens", 4000))

    source_pool = _build_source_pool(static_sources, source_registry)
    pool_by_label = {s["label"]: s for s in source_pool}

    bindings = _bind_sections_to_sources(nodes, source_pool, active_goal,
                                         slm_scheduler=slm_scheduler, tracker=tracker,
                                         task_id=task_id, tid=tid)

    # ---- 写作阶段：按节把绑定素材打包成 <= 8k 的组，超过则分步 ----
    write_jobs = []
    for n in nodes:
        nid = n.get("node_id", "unknown")
        labels = bindings.get(nid, [])
        groups = []
        cur, cur_t = [], 0
        for lb in labels:
            s = pool_by_label.get(lb)
            if not s:
                continue
            # 单份素材超过 8k 预算时切片分步，绝不截断丢弃事实
            pieces = []
            if s["tokens"] > ref_budget:
                for chunk in semantic_chunk_text(s["content"], max_tokens=ref_budget, overlap_ratio=0.0):
                    pieces.append({"label": lb, "content": chunk, "is_web_raw": s["is_web_raw"],
                                   "tokens": get_token_count(chunk)})
            else:
                pieces.append({"label": lb, "content": s["content"], "is_web_raw": s["is_web_raw"],
                               "tokens": s["tokens"]})
            for piece in pieces:
                t = piece["tokens"]
                if cur_t + t > ref_budget and cur:
                    groups.append(cur)
                    cur, cur_t = [], 0
                cur.append(piece)
                cur_t += t
        if cur:
            groups.append(cur)

        if not groups:
            n["_slm_failed"] = True
            continue

        total = len(groups)
        is_eng = detect_is_english(active_goal + n.get("title", ""))
        for pi, grp in enumerate(groups):
            refs_parts = []
            for item in grp:
                if item["is_web_raw"]:
                    refs_parts.append(f"[互联网检索]\n{item['content']}")
                else:
                    refs_parts.append(f"【资料 ^{{{item['label']}}}^】\n{item['content']}")
            refs_text = "\n\n".join(refs_parts)

            # 16k 总上下文护栏：模板+骨架+资料+输出 <= max_ctx
            refs_cap = max_ctx - output_tokens - get_token_count(skeleton_str) - 800
            if get_token_count(refs_text) > max(2000, refs_cap):
                refs_text = _truncate_to_tokens(refs_text, max(2000, refs_cap))

            prompt = build_slm_section_write_prompt(
                n.get("title", "未命名章节"), nid, skeleton_str, active_goal,
                refs_text, pi + 1, total, is_eng
            )
            write_jobs.append({
                "key": f"{nid}__part{pi + 1}",
                "node_id": nid,
                "part_idx": pi + 1,
                "total_parts": total,
                "prompt": prompt
            })

    print(f"   -> ✍️ [SLM 写作] 共 {len(write_jobs)} 个分步写作任务，并发下发 (并发池: {get_slm_concurrency()})...")
    if tid and tid != "UNKNOWN_TASK":
        update_task_progress(tid, f"✍️ [研报生成] 小模型正在并行撰写 {len(nodes)} 个章节 (共 {len(write_jobs)} 个分步任务)...")

    write_results = _execute_slm_jobs_with_retry(write_jobs, max_retries, output_tokens,
                                                 slm_scheduler=slm_scheduler, tracker=tracker, task_id=task_id)

    # ---- 合并阶段：多步产出的小节合并去重 ----
    node_texts = {}
    for n in nodes:
        nid = n.get("node_id", "unknown")
        if n.get("_slm_failed"):
            continue
        parts = []
        failed = False
        for j in write_jobs:
            if j["node_id"] != nid:
                continue
            text = write_results.get(j["key"])
            if text is None:
                failed = True
                break
            parts.append((j["part_idx"], text))
        if failed:
            n["_slm_failed"] = True
            continue
        parts = [t for _, t in sorted(parts, key=lambda x: x[0])]
        node_texts[nid] = parts

    for _ in range(3):  # 合并轮数兜底，防止极长小节无限递归
        merge_jobs = []
        for n in nodes:
            nid = n.get("node_id", "unknown")
            if n.get("_slm_failed") or nid not in node_texts:
                continue
            parts = node_texts[nid]
            if len(parts) <= 1:
                continue
            # 按 ref_budget 分组合并
            groups, g, gt = [], [], 0
            for p in parts:
                t = get_token_count(p)
                if gt + t > ref_budget and g:
                    groups.append(g)
                    g, gt = [], 0
                g.append(p)
                gt += t
            if g:
                groups.append(g)
            if len(groups) <= 1:
                parts_text = "\n\n".join([f"片段{k + 1}:\n{p}" for k, p in enumerate(parts)])
                merge_jobs.append({
                    "key": f"{nid}__merge",
                    "node_id": nid,
                    "prompt": build_slm_section_merge_prompt(n.get("title", "未命名章节"), parts_text,
                                                             detect_is_english(parts_text))
                })
                node_texts[nid] = "__PENDING_SINGLE__"
            else:
                for gi, grp in enumerate(groups):
                    parts_text = "\n\n".join([f"片段{k + 1}:\n{p}" for k, p in enumerate(grp)])
                    merge_jobs.append({
                        "key": f"{nid}__merge_g{gi}",
                        "node_id": nid,
                        "group_idx": gi,
                        "prompt": build_slm_section_merge_prompt(n.get("title", "未命名章节"), parts_text,
                                                                 detect_is_english(parts_text))
                    })
                node_texts[nid] = {"__groups__": len(groups)}

        if not merge_jobs:
            break

        print(f"   -> 🧬 [SLM 合并] 正在合并 {len(merge_jobs)} 个多步章节片段...")
        merge_results = _execute_slm_jobs_with_retry(merge_jobs, max_retries, output_tokens,
                                                     slm_scheduler=slm_scheduler, tracker=tracker, task_id=task_id)
        for n in nodes:
            nid = n.get("node_id", "unknown")
            if n.get("_slm_failed") or nid not in node_texts:
                continue
            state = node_texts[nid]
            if state == "__PENDING_SINGLE__":
                text = merge_results.get(f"{nid}__merge")
                if text is None:
                    n["_slm_failed"] = True
                    del node_texts[nid]
                else:
                    node_texts[nid] = [text]
            elif isinstance(state, dict) and "__groups__" in state:
                new_parts = []
                failed = False
                for gi in range(state["__groups__"]):
                    text = merge_results.get(f"{nid}__merge_g{gi}")
                    if text is None:
                        failed = True
                        break
                    new_parts.append(text)
                if failed:
                    n["_slm_failed"] = True
                    del node_texts[nid]
                else:
                    node_texts[nid] = new_parts

    # ---- 组装 + LLM 仅做排版美化 ----
    generated_results = {}
    for n in nodes:
        nid = n.get("node_id", "unknown")
        parts = node_texts.get(nid)
        if n.get("_slm_failed") or not parts:
            fail_text = "*(本节生成失败：小模型多次复读或输出异常，已跳过本节)*"
            generated_results[nid] = {"raw": fail_text, "beautified": fail_text, "failed": True}
            continue

        raw = "\n\n".join(parts)
        try:
            beautified = llm.chat_completion([
                {"role": "system", "content": beautify_sys_prompt},
                {"role": "user", "content": raw}
            ]).content.strip()
            if not beautified:
                beautified = raw
        except Exception:
            beautified = raw
        generated_results[nid] = {"raw": raw, "beautified": beautified}

    return generated_results, bindings, source_pool

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
    
    # 获取任务ID供前端推送使用
    tid = kwargs.get("task_id") or (agent_state.task_id if agent_state and getattr(agent_state, "task_id", "") else current_task_id.get())
    
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
    # 2. 全局二次压缩
    # ==========================================
    if total_tokens > token_limit:
        print(f"\n[容量超限] 聚合素材池总字数 ({total_tokens} Tokens) 超出极限。")
        print("正在触发全局降维 (直接复用第一次的 map_reduce_flow.py 进行二次提炼并重新绑定)...")
        if tid and tid != "UNKNOWN_TASK":
            update_task_progress(tid, f"🗜️ [研报生成] 聚合池容量超限({total_tokens} Tokens)，正在触发全局二次降维压缩...")
            
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
            from workflows.map_reduce_flow import delegate_to_small_models
            
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
            print(f"   [MAP/REDUCE] 溯源重组完毕 -> 当前体积: {total_tokens} Tokens")

        if total_tokens > token_limit:
            print(f"\n[极限超载] 经过二次 MAP/REDUCE 提炼后体积仍然超限 ({total_tokens} Tokens)！启动大类/小类分批打包与 LLM 局部小报告生成机制...")
            if tid and tid != "UNKNOWN_TASK":
                update_task_progress(tid, "📦 [研报生成] 容量仍然超限，正在启动大模型分批打包与局部小报告生成机制...")
                
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
                            job_sources = []
                            job_tokens = 0
                            part_idx = 1
                            small_report_limit = token_limit // 2
                            
                            for src in sc_sources:
                                src_tokens = get_token_count(src["content"])
                                if src_tokens > small_report_limit:
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
                            f"基于输入素材为最终报告撰写一个【{job['title']}】分类小报告。\n"
                            "高度提炼核心事实、发言人观点及具体数据数值（增减百分比、具体数据、精确时间节点等），写成结构化 Markdown。\n"
                            "必须严格原样保留素材中给出的引用角标，禁止自行编造。"
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
                
                import contextvars
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures_dict = {}

                    for idx, job in enumerate(report_jobs):
                        ctx = contextvars.copy_context()
                        futures_dict[executor.submit(ctx.run, generate_small_report, idx, job)] = idx
                        
                    for future in concurrent.futures.as_completed(futures_dict):
                        idx = futures_dict[future]
                        res = future.result()
                        if res: small_reports[idx] = res

            static_sources = [report for report in small_reports if report]
            total_tokens = sum(get_token_count(s["content"]) for s in static_sources)
            print(f"LLM 分类小报告汇聚完成！最终容量锁定在: {total_tokens} Tokens。")
    else:
        print(f"\n容量安全 ({total_tokens} Tokens)，直接进入最终研报生成阶段。")

    # ==========================================
    # 3. 构造传递给大模型的 Context
    # ==========================================
    combined_text_parts = []
    for src in static_sources:
        if src.get("is_web_raw"):
            combined_text_parts.append(f"[互联网检索]\n{src['content']}")
        else:
            tag_str = "".join([f"^{{{fid}}}^" for fid in src["ref_ids"]])
            combined_text_parts.append(f"[本地档案 {tag_str}]\n{src['content']}")
            
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
        # ✅ 推送 AST 生成状态
        if tid and tid != "UNKNOWN_TASK":
            update_task_progress(tid, "📝 [研报生成 1/3] 大模型正在根据所有素材提炼全局报告骨架(AST大纲)...")
            
        print(">> 1/3 正在生成报告骨架树(AST)...")
        outline_sys_prompt = """任务：基于输入目标和素材，生成一份逻辑紧凑的报告大纲。

规范：
1. 主题聚类：将碎片事实提炼成宏观分析维度，合并同类项，禁止直接映射单篇微观大纲。
2. 防幻觉：无关联的独立实体切勿强行编造联系，可放入统一现状章节内分段论述。
3. 结构与规模：采用总分总结构，大纲节点总数控制在3到9个以内。

输出 JSON 数组格式（含 node_id 和 title）。示例：
[
  {"node_id": "01_exec_summary", "title": "一、 全局执行摘要"},
  {"node_id": "02_tech_analysis", "title": "二、 核心技术剖析"},
  {"node_id": "03_market_status", "title": "三、 市场现状总览"},
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

        writer_sys_prompt = """任务：根据大纲撰写指定节点的正文。

规范：
1. 溯源引用：严格引用素材原文中提供的角标。**绝对禁止自行编造或虚构角标内容**。
2. 精准事实与数据：必须保留并引用具体指标、增减变化数值、以及机构或个人的具体观点。若素材中包含精确的时间或日期，必须明确交代事件发生的时间线，严禁使用模糊词汇替代。
3. 格式：禁止输出 JSON。必须且只能使用 XML 标签 <NODE id="节点ID">正文内容</NODE> 包裹。

示例：
<NODE id="01_exec_summary">
正文内容...
</NODE>"""

        rolling_enabled = get_rolling_context_enabled()
        if rolling_enabled:
            writer_sys_prompt = writer_sys_prompt.replace(
                "示例：",
                "4. 滚动续写：承接已完成章节的逻辑终点，围绕本节主题充分展开，给出详细完整的事实、数据与论据。\n\n示例："
            )

        beautify_sys_prompt = """任务：对输入的 Markdown 进行格式美化。禁止修改任何事实内容，绝对不可删除或修改原始文本中的引用角标。

规范：
1. 标题层级递进：严禁标题层级混用或跳跃（如：## 之后只能递进到 ###，严禁在二级标题下直接出现四级标题）。
2. 全文一致性：同级标题在全文的逻辑和样式必须保持一致。
3. 可读性优化：合理使用加粗和列表进行核心信息排版。"""

        # ✅ 推送正文并发撰写状态
        writer_mode = get_report_writer()
        binding_enabled = get_section_source_binding_enabled()
        node_bindings = None
        pool_by_label = {}
        generated_results = {}

        if writer_mode == "slm":
            # 🧊 小模型滚动溯源写报告：SLM 绑定资料 -> 分步并行写作 -> 合并 -> LLM 仅排版
            if tid and tid != "UNKNOWN_TASK":
                update_task_progress(tid, f"✍️ [研报生成 2/3] 大纲生成完毕(共{len(nodes)}节)。小模型正在绑定溯源资料并并行撰写正文...")

            print(f">> 2/3 [SLM 滚动溯源模式] 正在由小模型并行生成报告正文 (共 {len(nodes)} 个节点) ...")
            generated_results, node_bindings, source_pool = _generate_report_via_slm(
                nodes, static_sources, source_registry, active_goal, global_ast_skeleton_str,
                llm, beautify_sys_prompt,
                tracker=tracker, tid=tid, task_id=tid,
                slm_scheduler=kwargs.get("slm_scheduler")
            )
            pool_by_label = {s["label"]: s for s in source_pool}
        else:
            if binding_enabled:
                # 可选项（默认关闭，耗 token）：LLM 撰写时也启用 SLM 并行滚动溯源绑定
                try:
                    source_pool = _build_source_pool(static_sources, source_registry)
                    pool_by_label = {s["label"]: s for s in source_pool}
                    node_bindings = _bind_sections_to_sources(
                        nodes, source_pool, active_goal,
                        slm_scheduler=kwargs.get("slm_scheduler"), tracker=tracker,
                        task_id=tid, tid=tid
                    )
                except Exception as e:
                    print(f"⚠️ [滚动溯源] SLM 绑定阶段失败，回退为全量素材池模式: {e}")
                    node_bindings = None

            if tid and tid != "UNKNOWN_TASK":
                update_task_progress(tid, f"✍️ [研报生成 2/3] 大纲生成完毕(共{len(nodes)}节)。大模型正在并发撰写各章节正文...")

            print(f">> 2/3 正在并发与分批生成报告正文 (共 {len(nodes)} 个节点) ...")

            def generate_node_batch(batch_nodes, rolling_str=""):
                batch_titles = [f"【{n.get('title')}】 (ID: {n.get('node_id')})" for n in batch_nodes]
                if node_bindings:
                    # 滚动溯源：每个节点只注入其 SLM 绑定的素材，而非全量素材池
                    context_blocks = []
                    for n in batch_nodes:
                        nid = n.get("node_id", "unknown")
                        bound = []
                        for lb in node_bindings.get(nid, []):
                            s = pool_by_label.get(lb)
                            if not s:
                                continue
                            if s["is_web_raw"]:
                                bound.append(f"[互联网检索]\n{s['content']}")
                            else:
                                bound.append(f"[本地档案 ^{{{lb}}}^]\n{s['content']}")
                        bound_text = "\n\n".join(bound) if bound else "(本节无绑定素材)"
                        bound_text = _truncate_to_tokens(bound_text, token_limit)
                        context_blocks.append(
                            f"====================\n【节点 {nid} 的绑定溯源素材】\n{bound_text}\n===================="
                        )
                    context_str = "\n\n".join(context_blocks) + "\n\n"
                else:
                    context_str = STATIC_CONTEXT_PREFIX

                node_prompt = f"""{context_str}
{rolling_str}全局骨架树：
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

            if rolling_enabled:
                # 滚动生成：逐节串行撰写，节间注入已完成章节摘要
                rolling_budget = get_rolling_context_budget()
                print(f"   -> 滚动生成模式：逐节串行撰写，节间注入已完成章节摘要 (预算 {rolling_budget} Tokens)...")
                rolling_parts = []
                for n in nodes:
                    nid = n.get("node_id", "unknown")
                    rolling_str = ""
                    if rolling_parts:
                        rolling_str = "【已完成章节内容】\n" + "\n".join(rolling_parts) + "\n\n"
                    try:
                        res_map = generate_node_batch([n], rolling_str)
                        generated_results.update(res_map)
                        print(f"   节点完成: {n.get('title', '')[:10]}...")
                    except Exception as e:
                        print(f"   节点失败: {e}")
                    content = generated_results.get(nid, {}).get("beautified", "")
                    if content:
                        rolling_parts.append(_build_section_digest(n.get("title", "未命名章节"), content))
                    else:
                        rolling_parts.append(f"{n.get('title', '未命名章节')}：(本节生成失败)")
                    while len(rolling_parts) > 1 and sum(get_token_count(p) for p in rolling_parts) > rolling_budget:
                        # 超出预算时按从新到旧的逆序之外、由旧到新把摘要压缩到只剩标题
                        progressed = False
                        for i in range(len(rolling_parts) - 1):
                            if "：" in rolling_parts[i]:
                                rolling_parts[i] = rolling_parts[i].split("：", 1)[0]
                                progressed = True
                        if not progressed:
                            break
            else:
                batch_size = 2
                batches = [nodes[i:i + batch_size] for i in range(0, len(nodes), batch_size)]

                max_workers = min(len(batches), get_llm_concurrency())

                print(f"   -> 已将大纲拆分为 {len(batches)} 个批次，正在由 {max_workers} 个线程同时撰写正文...")

                import contextvars
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_batch = {}
                    for b in batches:
                        ctx = contextvars.copy_context()
                        future_to_batch[executor.submit(ctx.run, generate_node_batch, b)] = b

                    for future in concurrent.futures.as_completed(future_to_batch):
                        batch_ref = future_to_batch[future]
                        try:
                            res_map = future.result()
                            generated_results.update(res_map)
                            print(f"   批次完成: {', '.join([n.get('title', '')[:10]+'...' for n in batch_ref])}")
                        except Exception as e:
                            print(f"   批次失败: {e}")

        # ✅ 推送排版溯源状态
        if tid and tid != "UNKNOWN_TASK":
            update_task_progress(tid, "✨ [研报生成 3/3] 正文生成完毕！正在进行深度排版美化与溯源角标对齐...")
            
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

            def register_citation(ref_id):
                if ref_id not in source_registry:
                    return None

                src_meta = source_registry[ref_id]
                if ref_id not in global_citation_map:
                    idx = citation_counter[0]
                    global_citation_map[ref_id] = idx
                    global_citation_list.append({
                        "index": idx,
                        "title": src_meta["title"],
                        "url": src_meta["url"],
                        "type": src_meta["type"]
                    })
                    citation_counter[0] += 1

                idx = global_citation_map[ref_id]
                if idx not in node_indices:
                    node_indices.append(idx)
                    node_sources.append({
                        "index": idx,
                        "title": src_meta["title"],
                        "url": src_meta["url"],
                        "type": src_meta["type"]
                    })
                return idx

            # 🔗 SLM 绑定溯源：绑定清单优先注册入册，保证章节↔来源映射绝对稳定
            bound_ref_set = None
            if node_bindings:
                bound_ref_set = set()
                for lb in node_bindings.get(node_id, []):
                    if lb in source_registry:
                        bound_ref_set.add(lb)
                    pool_entry = pool_by_label.get(lb)
                    if pool_entry:
                        bound_ref_set.update(pool_entry.get("inline_refs", []))
                        bound_ref_set.update(r for r in pool_entry.get("ref_ids", []) if r != lb)
                for ref_id in bound_ref_set:
                    register_citation(ref_id)

            def map_and_replace_citation(match, is_web):
                ref_id = match.group(1)
                # 绑定模式下，凡不在本节绑定集合内的角标一律视为幻觉，物理剥离
                if bound_ref_set is not None and ref_id not in bound_ref_set:
                    return ""
                idx = register_citation(ref_id)
                if idx is None:
                    return ""
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

            # 🧹 静态清洗:绑定关系是静态的,凡不指向合法来源的"角标形状"残留一律物理剥离
            beautified_mapped = strip_ghost_citations(beautified_mapped)
            
            node["raw_content"] = raw_content
            node["beautified_content"] = beautified_mapped
            node["matched_sources"] = sorted(node_sources, key=lambda x: x["index"])
            node["failed"] = bool(node_data.get("failed", False))
            
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
        
        reference_md = "\n\n---\n## 结论与论据参考索引\n\n"
        if global_citation_list:
            for cite in sorted(global_citation_list, key=lambda x: x["index"]):
                if cite["type"] == "web":
                    reference_md += f"{cite['index']}. [网络来源] [{cite['title']}]({cite['url']})\n"
                else:
                    reference_md += f"{cite['index']}. [本地文档] {cite['title']}\n"
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
                    "sources": node.get("matched_sources", []),
                    "failed": node.get("failed", False)
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
            agent_state.final_result = f"分析完成。\n排版研报: {beautified_report_path}\n精准解耦溯源 JSONL: {jsonl_path}"
            
        return "执行结束"
        
    except Exception as e: 
        error_info = f"报告汇聚生成失败: {e}"
        print(error_info)
        return error_info