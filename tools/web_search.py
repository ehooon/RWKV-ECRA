# RWKV-ECRA/tools/web_search.py
import os
import re
import uuid
import concurrent.futures
from config import API_KEYS, SEARCH_CONFIG, DATA_PIPELINE, SLM_CONFIG, get_llm_provider
from tools.registry import ToolRegistry
from clients.slm_client import SLMClient
from clients.llm_client import LLMClient
from prompts.slm_prompts import build_slm_web_search_compress_prompt
from utils.chunker import get_token_count, semantic_chunk_text

slm_client = SLMClient()

@ToolRegistry.register(
    name="execute_web_search",
    phase="ALL",
    signature="""[Tool] execute_web_search
- 功能: 联网检索外部事实。系统底层将根据模型配置自动路由：原生大模型联网聚合 或 Tavily生肉双路抓取。
- 参数: query (精简的单点搜索短语)"""
)
def execute_web_search(query: str, working_memory: dict = None, tracker=None, agent_state=None, **kwargs) -> str:
    provider = get_llm_provider()
    safe_query = re.sub(r'\W+', '_', query)[:20]
    
    # 初始化 web_structured_facts 存储结构
    if working_memory is not None and "__web_structured_facts__" not in working_memory:
        working_memory["__web_structured_facts__"] = []

    # ==========================================
    # 🌟 路线 A：百度文心原生联网架构 (携带溯源追踪)
    # ==========================================
    if provider == "baidu":
        print(f"[Web Search]: 🚀 正在启动文心原生联网检索 -> '{query}' ...")
        llm = LLMClient()
        prompt_msg = [
            {"role": "system", "content": "执行联网检索。提取与检索词相关的客观事实、数据与时间线。禁止输出推测。"},
            {"role": "user", "content": f"检索目标: {query}"}
        ]
        
        try:
            response_msg = llm.chat_completion(prompt_msg, enable_native_search=True)
            response_text = response_msg.content
            search_results = getattr(response_msg, "search_results", [])
            
            structured_facts = []
            
            # 将文心的局部角标 ^[1]^ 映射到全局唯一的 WEB_REF
            # 🔴 核心修复：按索引倒序排序，确保 [10] 在 [1] 之前被替换，防止映射错位
            sorted_results = sorted(
                search_results, 
                key=lambda x: int(x.get("index", 0)) if str(x.get("index", 0)).isdigit() else 0, 
                reverse=True
            )
            
            for res in sorted_results:
                idx = res.get("index")
                url = res.get("url", "")
                title = res.get("title", f"参考资料_{idx}")
                web_ref_id = f"WEB_REF_BD_{uuid.uuid4().hex[:6]}"
                
                # 替换正文中的文心原生角标 ^[n]^ 或 [n]
                response_text = response_text.replace(f"^[{idx}]^", f"^[{web_ref_id}]^")
                response_text = response_text.replace(f"[{idx}]", f"^[{web_ref_id}]^")
                
                structured_facts.append({
                    "ref_id": web_ref_id,
                    "title": title,
                    "url": url,
                    "content": f"系统抓取索引 ({title})"
                })
            
            clean_res = f"来源于《原生搜索引擎》:\n{response_text}"
            
            if working_memory is not None:
                working_memory[f"WebFact_{safe_query}"] = clean_res
                working_memory["__web_structured_facts__"].extend(structured_facts)
                if agent_state:
                    agent_state.memory_catalog[f"WebFact_{safe_query}"] = "状态: 已获取带有溯源角标的原生结构化事实"
                    
            return f"状态返回: 原生检索结束，发现 {len(search_results)} 个网页事实。"
        except Exception as e:
            return f"状态返回: 联网检索异常: {str(e)}"
            
    # ==========================================
    # 🐢 路线 B：Tavily 生肉 + SLM 单页面隔离清洗 (精准绑定)
    # ==========================================
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=API_KEYS.get("tavily", ""))
        max_res = SEARCH_CONFIG.get("max_results", 10)
        
        def run_tavily_search(topic: str):
            try:
                return client.search(query=query, search_depth=SEARCH_CONFIG.get("search_depth", "advanced"), 
                                     max_results=max(3, max_res // 2), include_raw_content=False, 
                                     time_range="month", search_topic=topic).get("results", [])
            except: return []

        print(f"[Web Search]: 🚀 启动 Tavily 并发检索 -> '{query}' ...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = executor.submit(run_tavily_search, "finance").result() + executor.submit(run_tavily_search, "news").result()
            
        seen_urls = set()
        unique_results = []
        for r in results:
            if r.get("url") and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)
        
        if not unique_results: return f"状态返回: 搜索 '{query}' 无结果。"
        
        prompts = []
        prompt_metadata = [] # 记录 prompt 对应的独立信息
        max_chunk = DATA_PIPELINE.get("max_chunk_tokens", 800)
        
        for r in unique_results:
            title = r.get("title", "未命名网页").strip()
            content = r.get("content", "").strip()
            url = r.get("url", "")
            web_ref_id = f"WEB_REF_TV_{uuid.uuid4().hex[:6]}" # 为每一个网页生成唯一绑定的 ID
            
            chunks = semantic_chunk_text(content, max_tokens=max_chunk, overlap_ratio=0.1)
            for chunk in chunks:
                prompts.append(build_slm_web_search_compress_prompt(query, f"【标题】: {title}\n【片段】: {chunk}"))
                prompt_metadata.append({"ref_id": web_ref_id, "title": title, "url": url})
            
        print(f"启动 SLM 隔离去噪...")
        all_responses = []
        for i in range(0, len(prompts), SLM_CONFIG.get("concurrency", 16)):
            all_responses.extend(slm_client.batch_generate(prompts[i:i+SLM_CONFIG.get("concurrency", 16)], tracker=tracker))
            
        structured_web_facts = []
        clean_parts = []
        processed_refs = set()
        
        # 组装：在合并文本时，强制为每个来源的每句话/段落打上对应专属的 ^[WEB_REF_X]^
        for idx, out in enumerate(all_responses):
            clean_out = out.split("</think>")[-1].strip() if "</think>" in out else out.strip()
            if clean_out and not any(m in clean_out for m in ["未找到", "无实质内容", "None"]):
                meta = prompt_metadata[idx]
                ref_id = meta["ref_id"]
                
                # 为这段事实附加上强绑定的网络角标
                clean_parts.append(f"【网络事实 ^[{ref_id}]^ 】 {meta['title']}：{clean_out}")
                
                if ref_id not in processed_refs:
                    structured_web_facts.append({"ref_id": ref_id, "title": meta["title"], "url": meta["url"], "content": "Tavily融合事实"})
                    processed_refs.add(ref_id)
                
        if not clean_parts: return "状态返回: 提取不到有效客观事实。"
            
        if working_memory is not None:
            working_memory[f"WebFact_{safe_query}"] = "\n".join(clean_parts)
            working_memory["__web_structured_facts__"].extend(structured_web_facts)
            if agent_state:
                agent_state.memory_catalog[f"WebFact_{safe_query}"] = f"状态: 已绑定 {len(processed_refs)} 个网页溯源"
            
        return f"状态返回: 联网检索结束，已载入记忆区。"
        
    except Exception as e:
        return f"状态返回: 联网搜索异常: {str(e)}"