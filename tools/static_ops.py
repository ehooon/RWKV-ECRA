# RWKV-ECRA/tools/static_ops.py
import os
import json
from utils.file_reader import read_local_file
from config import DATA_PIPELINE

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

def preview_document_content(file_paths: list = None, **kwargs) -> str:
    if not file_paths: return "未传入目标文件路径。"
    res = []
    for path in file_paths:
        try:
            text = read_local_file(path)
            # 纯物理试读，极速返回前800字
            preview = text[:800] + "\n...(后略)" if len(text) > 800 else text
            res.append(f"📄 文件: {os.path.basename(path)}\n【前言物理截断试读】:\n{preview}")
        except Exception as e:
            res.append(f"📄 文件: {os.path.basename(path)} 读取失败: {str(e)}")
    return "\n\n".join(res)