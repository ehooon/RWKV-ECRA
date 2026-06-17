# RWKV-ECRA/tools/web_search.py
import os
import re
import uuid
import json
import concurrent.futures
from config import API_KEYS, SEARCH_CONFIG, DATA_PIPELINE, SLM_CONFIG, get_llm_provider
from tools.registry import ToolRegistry
from clients.slm_client import SLMClient
from clients.llm_client import LLMClient
from prompts.slm_prompts import build_slm_web_search_compress_prompt
from utils.chunker import get_token_count, semantic_chunk_text

slm_client = SLMClient()

def _generate_search_queries(query: str, active_goal: str) -> list:
    """让 AI 动态生成多维度搜索提示词"""
    llm = LLMClient()
    sys_prompt = "你是一个高级情报检索专家。请基于【核心实体】和【全局调查目标】，生成 3 个不同维度的搜索引擎查询短语（越精简越好，适合喂给谷歌/百度）。\n维度要求：1. 定义与背景； 2. 与调查目标的深度关联； 3. 最新新闻与动态。\n必须只输出 JSON 字符串数组格式，例如 [\"词1\", \"词2\", \"词3\"]。"
    
    try:
        resp = llm.chat_completion([
            {"role": "system", "content": sys_prompt}, 
            {"role": "user", "content": f"核心实体: {query}\n全局调查目标: {active_goal}"}
        ]).content
        match = re.search(r'\[.*\]', resp, re.DOTALL)
        if match:
            q_list = json.loads(match.group(0))
            if isinstance(q_list, list) and len(q_list) > 0:
                return [str(q)[:30] for q in q_list[:3]]
    except Exception:
        pass
    # 兜底搜索词
    return [f"{query} 是什么", f"{query} {active_goal[:8]} 关联", f"{query} 最新动态"]

@ToolRegistry.register(
    name="execute_web_search",
    phase="ALL",
    signature="""[Tool] execute_web_search
- 功能: 联网检索外部事实。底层集成了 AI 自动搜索词扩展与多源抓取，用于调查缺乏本地文件支撑的特定实体或逻辑。
- 参数: query (精简的实体名称或搜素短语)"""
)
def execute_web_search(query: str, working_memory: dict = None, tracker=None, agent_state=None, **kwargs) -> str:
    provider = get_llm_provider()
    safe_query = re.sub(r'\W+', '_', query)[:20]
    
    # 动态获取当前正在执行的全局目标
    active_goal = agent_state.refined_query if (agent_state and hasattr(agent_state, 'refined_query') and agent_state.refined_query) else kwargs.get("original_goal", "当前主线任务")

    if working_memory is not None and "__web_structured_facts__" not in working_memory:
        working_memory["__web_structured_facts__"] = []

    # ==========================================
    # 🌟 路线 A：百度文心原生联网架构
    # ==========================================
    if provider == "baidu":
        print(f"[Web Search]: 🚀 启动文心原生关联检索 -> 实体: '{query}' ...")
        llm = LLMClient()
        prompt_msg = [
            {"role": "system", "content": "执行深度联网检索。你必须自主判断该实体与用户目标的关联性。如果它与当前业务领域毫无关系（例如是毫不相干的网红/娱乐/游戏等跨界实体），请直接指出其真实身份并明确声明“与调查目标无关”。"},
            {"role": "user", "content": f"全局调查目标: {active_goal}\n请全面调查: {query} 是什么？它最近有什么动态？它与我们的调查目标是否有实质性影响或关联？"}
        ]
        
        try:
            response_msg = llm.chat_completion(prompt_msg, enable_native_search=True)
            response_text = response_msg.content
            search_results = getattr(response_msg, "search_results", [])
            
            structured_facts = []
            sorted_results = sorted(search_results, key=lambda x: int(x.get("index", 0)) if str(x.get("index", 0)).isdigit() else 0, reverse=True)
            
            for res in sorted_results:
                idx = res.get("index")
                title = res.get("title", f"参考资料_{idx}")
                web_ref_id = f"WEB_REF_BD_{uuid.uuid4().hex[:6]}"
                
                response_text = response_text.replace(f"^[{idx}]^", f"^[{web_ref_id}]^").replace(f"[{idx}]", f"^[{web_ref_id}]^")
                structured_facts.append({"ref_id": web_ref_id, "title": title, "url": res.get("url", ""), "content": "系统原生抓取"})
            
            clean_res = f"来源于《原生搜索引擎》:\n{response_text}"
            
            if working_memory is not None:
                working_memory[f"WebFact_{safe_query}"] = clean_res
                working_memory["__web_structured_facts__"].extend(structured_facts)
                if agent_state:
                    agent_state.memory_catalog[f"WebFact_{safe_query}"] = "状态: 已提炼完成，直接可用，切勿再次提取"
                    # 若文心判定为无关，直接将状态置为无关
                    status_str = "确认无关 (跨界干扰项)" if "无关" in response_text and query in response_text else "确认相关 (已完成提炼)"
                    for ent in list(agent_state.entity_audit.keys()):
                        if ent.lower() in query.lower() or query.lower() in ent.lower():
                            agent_state.entity_audit[ent] = status_str
                    
            return f"[系统状态] 实体 '{query}' 联网检索完成。数据已挂载至记忆区并更正实体状态，切勿再次提取。请推进下一步或进入 SYNTHESIS 阶段。"
        except Exception as e:
            return f"[系统异常] 联网检索报错: {str(e)}"
            
    # ==========================================
    # 🚀 路线 B：Tavily AI搜索词扩展 + SLM 全文校验去噪
    # ==========================================
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=API_KEYS.get("tavily", ""))
        
        # 1. 动态生成 3 个维度的查询词
        queries_to_run = _generate_search_queries(query, active_goal)
        print(f"[Web Search]: 🧠 AI 动态扩展多维检索词: {queries_to_run}")
        
        def run_tavily_search(q: str, topic: str):
            try:
                return client.search(query=q, search_depth="basic", max_results=4, include_raw_content=False, time_range="month", search_topic=topic).get("results", [])
            except: return []

        # 2. 高并发多维度、多分类抓取 (极大扩充参考网页数量)
        print(f"[Web Search]: 🚀 正在向 Tavily 并发发射检索探针...")
        all_raw_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for q in queries_to_run:
                futures.append(executor.submit(run_tavily_search, q, "finance"))
                futures.append(executor.submit(run_tavily_search, q, "news"))
                futures.append(executor.submit(run_tavily_search, q, "general"))
            for f in concurrent.futures.as_completed(futures):
                all_raw_results.extend(f.result())
            
        seen_urls = set()
        unique_results = []
        for r in all_raw_results:
            if r.get("url") and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)
        
        if not unique_results: return f"[系统状态] 搜索实体 '{query}' 无有效结果返回。"
        
        # 3. 构建 SLM 校验队列
        prompts = []
        prompt_metadata = []
        max_chunk = DATA_PIPELINE.get("max_chunk_tokens", 800)
        
        for r in unique_results:
            title = r.get("title", "未命名网页").strip()
            web_ref_id = f"WEB_REF_TV_{uuid.uuid4().hex[:6]}"
            chunks = semantic_chunk_text(r.get("content", "").strip(), max_tokens=max_chunk, overlap_ratio=0.1)
            for chunk in chunks:
                # 传入 active_goal 进行目标锚定
                prompts.append(build_slm_web_search_compress_prompt(query, f"【标题】: {title}\n【片段】: {chunk}", active_goal))
                prompt_metadata.append({"ref_id": web_ref_id, "title": title, "url": r.get("url", "")})
            
        print(f"[Web Search]: 🛡️ 启动 SLM 全文隔离与目标去噪 (共 {len(prompts)} 个分块)...")
        all_responses = []
        for i in range(0, len(prompts), SLM_CONFIG.get("concurrency", 16)):
            all_responses.extend(slm_client.batch_generate(prompts[i:i+SLM_CONFIG.get("concurrency", 16)], tracker=tracker))
            
        structured_web_facts = []
        clean_parts = []
        processed_refs = set()
        
        irrelevant_votes = 0  
        valid_chunk_count = 0
        
        # 4. 组装与跨界投票裁决 (兼容小模型的自然语言输出)
        for idx, out in enumerate(all_responses):
            clean_out = out.split("</think>")[-1].strip() if "</think>" in out else out.strip()
            if not clean_out or any(m in clean_out for m in ["未找到", "无实质内容", "None"]):
                continue
                
            valid_chunk_count += 1
            
            # 🟢 兼容自然语言判定：捕捉小模型话语中暗示“不沾边”的口语化特征词
            if any(kw in clean_out for kw in ["无关", "毫无关系", "不相干", "没有关系", "真实身份"]):
                irrelevant_votes += 1
                
            meta = prompt_metadata[idx]
            ref_id = meta["ref_id"]
            
            clean_parts.append(f"【网络情报 ^[{ref_id}]^ 】 {meta['title']}：{clean_out}")
            if ref_id not in processed_refs:
                structured_web_facts.append({"ref_id": ref_id, "title": meta["title"], "url": meta["url"], "content": "Tavily智能多源融合事实"})
                processed_refs.add(ref_id)
                
        # 👑 核心裁决机制：超过一半说没关系，全盘推翻
        is_irrelevant = valid_chunk_count > 0 and (irrelevant_votes / valid_chunk_count >= 0.5)
        
        if is_irrelevant:
            print(f"🚫 [跨界拦截]: 发现 {irrelevant_votes}/{valid_chunk_count} 的网页判定 '{query}' 与调查目标无关！")
            clean_parts = [f"【目标偏离判定】经 {len(processed_refs)} 个网页交叉验证，实体 '{query}' 的真实领域与当前主线调查毫无关联。"]
            status_str = "确认无关 (已跨界拦截)"
        else:
            status_str = "确认相关 (已完成提炼)"
            
        if not clean_parts: return "[系统状态] 未能从有效网页中提取到客观事实。"
            
        if working_memory is not None:
            working_memory[f"WebFact_{safe_query}"] = "\n".join(clean_parts)
            working_memory["__web_structured_facts__"].extend(structured_web_facts)
            if agent_state:
                agent_state.memory_catalog[f"WebFact_{safe_query}"] = f"状态: 已绑定 {len(processed_refs)} 个网页源，严禁再次提取"
                for ent in list(agent_state.entity_audit.keys()):
                    if ent.lower() in query.lower() or query.lower() in ent.lower():
                        agent_state.entity_audit[ent] = status_str
            
        return f"[系统状态] 实体 '{query}' 联网多源检索完成。已载入记忆区并更正状态，切勿再次提取。请推进下一步或进入 SYNTHESIS 阶段。"
        
    except Exception as e:
        return f"[系统异常] 联网搜索报错: {str(e)}"