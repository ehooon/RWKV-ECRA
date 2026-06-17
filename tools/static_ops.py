# RWKV-ECRA/tools/static_ops.py
import os
import json
import random
from utils.file_reader import read_local_file
from config import DATA_PIPELINE
from tools.registry import ToolRegistry
from clients.slm_client import SLMClient
from prompts.slm_prompts import build_slm_preview_prompt

slm_client = SLMClient()

@ToolRegistry.register(
    name="search_local_file",
    phase="DISCOVERY",
    signature="""[Tool] search_local_file
- 功能: 基于关键词搜索本地工作区文件，返回文件路径及虚拟ID。传空字符串为全量查询。
- 参数: keyword (搜索关键词)"""
)
def search_local_file(keyword: str = "", path_to_id: dict = None, **kwargs) -> str:
    base_dir = DATA_PIPELINE["input_directory"]
    allowed_exts = DATA_PIPELINE["allowed_extensions"]
    found_info = []
    raw_paths = []
    
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.startswith("~") or file.startswith("."): continue
            if os.path.splitext(file)[1].lower() in allowed_exts and (not keyword or keyword.lower() in file.lower()):
                full_path = os.path.abspath(os.path.join(root, file))
                raw_paths.append(full_path)
                if path_to_id and full_path in path_to_id:
                    found_info.append(f"- ID: `{path_to_id[full_path]}` | 文件名: {file}")

    if not path_to_id:
        return json.dumps(raw_paths, ensure_ascii=False)
    if not found_info:
        return f"[系统状态] 未找到包含关键词 '{keyword}' 的文件。请尝试全量空词查询。"
    return f"[系统状态] 检索完成，找到 {len(found_info)} 个匹配文件:\n" + "\n".join(found_info)


@ToolRegistry.register(
    name="preview_document_content",
    phase="DISCOVERY",
    signature="""[Tool] preview_document_content
- 功能: [斥候试读] 让小模型读取本地文件片段，判别其主题和文件类型。用于排查本地工作区未知文件是否与任务相关，剔除干扰项。
- 参数: file_ids (待预览的文件ID数组)"""
)
def preview_document_content(file_paths: list = None, actual_file_ids: list = None, agent_state=None, tracker=None, working_memory: dict = None, **kwargs) -> str:
    if not file_paths or not actual_file_ids: return "未传入目标文件路径或ID。"
    
    res = []
    prompts = []
    valid_files = []
    
    for idx, path in enumerate(file_paths):
        try:
            text = read_local_file(path)
            total_len = len(text)
            
            if total_len <= 1500:
                preview_text = text
            else:
                head = text[:500]
                tail = text[-500:]
                mid_start = random.randint(500, total_len - 500)
                mid = text[mid_start:mid_start+500]
                preview_text = f"{head}\n\n...[中段随机抽样]...\n\n{mid}\n\n...[尾部抽样]...\n\n{tail}"
                
            prompts.append(build_slm_preview_prompt(preview_text))
            valid_files.append((actual_file_ids[idx], os.path.basename(path)))
        except Exception as e:
            res.append(f"文件 {os.path.basename(path)} 读取失败: {str(e)}")
            
    if not prompts:
        return "\n".join(res)
        
    print(f"[试读斥候]: 正在委派 SLM 全面抽样试读 {len(prompts)} 个未知文件...")
    
    slm_responses = slm_client.batch_generate(prompts, tracker=tracker)
    
    for i, out in enumerate(slm_responses):
        fid, fname = valid_files[i]
        clean_out = out.split("</think>")[-1].strip() if "</think>" in out else out.strip()
        
        catalog_desc = clean_out.replace('\n', ' | ') 
        
        if agent_state:
            agent_state.memory_catalog[f"Preview_{fid}"] = f"试读结论: {catalog_desc}"
        if working_memory is not None:
            working_memory[f"Preview_{fid}"] = catalog_desc
            
        res.append(f"[{fname}] 试读完成，情报已登记。")
        
    return "状态返回: 试读任务结束。请查阅环境上下文中的【运行缓存区】目录大纲，以评估文件关联度。"

@ToolRegistry.register(
    name="verify_keyword_in_file",
    phase="ALL",
    signature="""[Tool] verify_keyword_in_file
- 功能: [精准验真] 物理级全文检索，验证特定文件中是否真实提及了关键词。用于打破关联幻觉（例如查验A文档是否提到B实体）。
- 参数: file_ids (目标文件虚拟ID数组), keywords (待验证的关键词字符串数组)"""
)
def verify_keyword_in_file(file_ids: list = None, keywords: list = None, agent_state=None, **kwargs) -> str:
    # 1. 严格参数校验
    if not file_ids or not isinstance(file_ids, list): 
        return "[系统状态] 执行失败：未传入有效的目标文件ID数组(file_ids)。"
    if not keywords or not isinstance(keywords, list): 
        return "[系统状态] 执行失败：未提供需验证的关键词列表(keywords)。"

    # 2. 内置强制导包，彻底杜绝 NameError 报错
    import os
    import re
    from utils.file_reader import read_local_file
    
    results = []
    global_found_kws = set()
    
    # 3. 遍历文件检索
    for fid in file_ids:
        # 直接从环境状态中取路径，防止路径映射异常
        if agent_state and hasattr(agent_state, 'id_to_path') and fid in agent_state.id_to_path:
            path = agent_state.id_to_path[fid]
        else:
            results.append(f"📄 【{fid}】 验证跳过: ID无效或该文件已被物理屏蔽。")
            continue
            
        fname = os.path.basename(path)
        try:
            text = read_local_file(path)
            file_res = [f"📄 【{fname}】 验真结果:"]
            
            for kw in keywords:
                # 转义搜索词中的特殊符号，防止正则崩溃
                safe_kw = re.escape(str(kw))
                matches = list(re.finditer(safe_kw, text, re.IGNORECASE))
                count = len(matches)
                
                if count == 0:
                    file_res.append(f"  - 关键词 '{kw}': 出现 0 次")
                else:
                    global_found_kws.add(str(kw))  # 记录该词在全局找到了
                    first_m = matches[0]
                    start = max(0, first_m.start() - 30)
                    end = min(len(text), first_m.end() + 30)
                    context_snippet = text[start:end].replace('\n', ' ')
                    file_res.append(f"  - 关键词 '{kw}': 出现 {count} 次。片段: \"...{context_snippet}...\"")
            
            results.append("\n".join(file_res))
            
        except Exception as e:
            # 即使单文件读取失败（例如碰到不支持的格式），也能优雅降级而不崩溃
            results.append(f"📄 【{fname}】 验证读取失败: {str(e)}")

    # 4. 全局状态纠偏：如果指定的关键词在**所有传入查询的文件中**都没有出现，才打上“无关”标签
    if agent_state and hasattr(agent_state, 'entity_audit') and agent_state.entity_audit:
        for kw in keywords:
            if str(kw) not in global_found_kws:
                # 在状态树中寻找相关的实体
                for ent in list(agent_state.entity_audit.keys()):
                    if str(kw).lower() in ent.lower() or ent.lower() in str(kw).lower():
                        agent_state.entity_audit[ent] = f"确认无关 (在指定的 {len(file_ids)} 个文件中均未检出，已打破强制关联)"

    return "[系统状态] 全文验真执行完毕：\n\n" + "\n\n".join(results)