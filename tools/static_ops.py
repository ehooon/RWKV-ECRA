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
        return f"未找到包含关键词 '{keyword}' 的文件。请尝试放宽搜索词或全量空词查询。"
    return f"🔎 检索成功，找到 {len(found_info)} 个匹配文件:\n" + "\n".join(found_info)


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
            
        res.append(f"✅ {fname} 试读完成，情报已登记至目录大纲。")
        
    return "状态返回: 试读任务结束。请查阅环境上下文中的【运行缓存区】目录大纲，以评估文件关联度。"