# RWKV-ECRA/translator_plugin/core.py
import os
import re
import shutil
from clients.slm_client import SLMClient
from utils.chunker import semantic_chunk_text
from utils.file_reader import read_local_file
from config import SLM_CONFIG
from translator_plugin.prompts import build_translation_prompt
from translator_plugin.config import TRANSLATOR_CONFIG

try:
    from markdown_it import MarkdownIt
except ImportError:
    raise ImportError("🚨 请先安装 Markdown 渲染解析库: pip install markdown-it-py")

slm_client = SLMClient()
md_parser = MarkdownIt("default")

def parse_markdown_line_by_line(text: str) -> list[dict]:
    lines = text.split('\n')
    if not lines: return []
    
    line_types = ["text"] * len(lines)
    
    # 1. AST 渲染器扫描
    tokens = md_parser.parse(text)
    def traverse(tks):
        for t in tks:
            if t.map:
                if t.type in ['table_open', 'fence', 'html_block', 'hr']:
                    for i in range(t.map[0], t.map[1]):
                        if i < len(line_types):
                            line_types[i] = "raw"
            if t.children:
                traverse(t.children)
    traverse(tokens)
    
    # 2. 暴力 HTML 与复杂结构兜底
    html_tags = ['<td', '<th', '<tr', '<table', '<tbody', '<thead', '</td', '</th', '</tr', '</table', '</tbody', '</thead']
    in_math = False
    
    for i, line in enumerate(lines):
        if line_types[i] == "raw": continue
        stripped = line.strip()
        
        if i == 0 and stripped == "---":
            for j in range(i, len(lines)):
                line_types[j] = "raw"
                if j > i and lines[j].strip() == "---": break
            continue
            
        lower_line = stripped.lower()
        if any(tag in lower_line for tag in html_tags):
            line_types[i] = "raw"
            continue
            
        if stripped == "$$":
            in_math = not in_math
            line_types[i] = "raw"
            continue
        elif in_math:
            line_types[i] = "raw"
            continue
        elif stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 2:
            line_types[i] = "raw"
            continue

        if stripped.count('|') >= 2 and not stripped.startswith('#') and not stripped.startswith('>'):
            line_types[i] = "raw"
            continue

    # 3. 将连续的相同类型行合并为 Block
    blocks = []
    current_type = line_types[0]
    current_lines = [lines[0]]
    
    for i in range(1, len(lines)):
        if line_types[i] == current_type:
            current_lines.append(lines[i])
        else:
            blocks.append({"type": current_type, "content": '\n'.join(current_lines)})
            current_type = line_types[i]
            current_lines = [lines[i]]
            
    if current_lines:
        blocks.append({"type": current_type, "content": '\n'.join(current_lines)})
        
    return blocks

def clean_translation_output(text: str) -> str:
    """清理输出：实现 \n\n 双换行截断，去除多余输出"""
    clean_str = text.strip()
    
    if "<think>" in clean_str:
        clean_str = re.sub(r"<think>.*?</think>", "", clean_str, flags=re.DOTALL)
        clean_str = clean_str.split("<think>")[0].strip()
        
    # 以双换行为界截断输出
    if "\n\n" in clean_str:
        clean_str = clean_str.split("\n\n")[0]
        
    if "English:" in clean_str:
        clean_str = clean_str.split("English:")[0]
        
    return clean_str.strip()

def process_translation_task(input_dir: str, output_dir: str):
    if not os.path.exists(input_dir):
        print(f"⚠️ 输入目录不存在: {input_dir}")
        return

    concurrency_limit = SLM_CONFIG.get("concurrency", 16)
    trans_chunk_size = TRANSLATOR_CONFIG.get("max_chunk_tokens", 1200)
    trans_overlap = TRANSLATOR_CONFIG.get("overlap_ratio", 0.0)
    found_files = False

    for root, dirs, files in os.walk(input_dir):
        for file_name in files:
            if file_name.startswith('.'):
                continue
                
            found_files = True
            input_path = os.path.join(root, file_name)
            
            rel_path = os.path.relpath(root, input_dir)
            target_out_dir = os.path.join(output_dir, rel_path) if rel_path != "." else output_dir
            os.makedirs(target_out_dir, exist_ok=True)
            
            if not file_name.endswith(('.txt', '.md')):
                target_file_path = os.path.join(target_out_dir, file_name)
                shutil.copy2(input_path, target_file_path)
                display_name = os.path.join(rel_path, file_name) if rel_path != "." else file_name
                print(f"🖼️  复制资源附件: {display_name}")
                continue
                
            base_name = os.path.splitext(file_name)[0]
            output_path = os.path.join(target_out_dir, f"{base_name}_ZH.md")
            display_name = os.path.join(rel_path, file_name) if rel_path != "." else file_name
            print(f"\n🌐 开始翻译文档: {display_name}")
            
            try:
                text = read_local_file(input_path)
                blocks = parse_markdown_line_by_line(text)
                
                translation_tasks = []
                para_images_map = {} # 🔴 用于存放分离出来的图片

                for b_idx, block in enumerate(blocks):
                    if block["type"] == "raw" or not block["content"].strip():
                        continue
                    
                    paras = block["content"].split('\n\n')
                    for p_idx, para in enumerate(paras):
                        if not para.strip(): continue
                        
                        # 🖼️ 新增：正则分离图片与文本，防止被翻译插件破坏！
                        images = []
                        def repl(m):
                            images.append(m.group(0))
                            return f"［IMG_{len(images)-1}］" # 替换为全角占位符
                        
                        # 匹配标准 Markdown 图片 ![alt](url) 或 HTML 图片 <img src="...">
                        masked_para = re.sub(r'!\[.*?\]\(.*?\)|<img\b[^>]*>', repl, para, flags=re.IGNORECASE)
                        para_images_map[(b_idx, p_idx)] = images
                        
                        chunks = semantic_chunk_text(masked_para, max_tokens=trans_chunk_size, overlap_ratio=trans_overlap)
                        for c_idx, chunk in enumerate(chunks):
                            translation_tasks.append({
                                "b_idx": b_idx,
                                "p_idx": p_idx,
                                "content": chunk
                            })

                total_tasks = len(translation_tasks)
                print(f"✂️ 行级隔离成功，生成 {total_tasks} 个待翻译的纯净段落...")

                if total_tasks > 0:
                    prompts = [build_translation_prompt(t["content"]) for t in translation_tasks]
                    global_results = {i: "" for i in range(total_tasks)}

                    for i in range(0, total_tasks, concurrency_limit):
                        batch_prompts = prompts[i : i + concurrency_limit]
                        print(f"🚀 发送批次 {i+1} ~ {min(i+concurrency_limit, total_tasks)} / {total_tasks}")
                        batch_res = slm_client.batch_generate(batch_prompts)
                        
                        for j, res_text in enumerate(batch_res):
                            absolute_index = i + j
                            global_results[absolute_index] = clean_translation_output(res_text)

                    # 拼合段落
                    translated_paras = {}
                    for t_idx, task in enumerate(translation_tasks):
                        key = (task["b_idx"], task["p_idx"])
                        if key not in translated_paras:
                            translated_paras[key] = ""
                        translated_paras[key] += global_results[t_idx]
                        
                    # 写回 block 并还原图片
                    for b_idx, block in enumerate(blocks):
                        if block["type"] == "raw" or not block["content"].strip():
                            continue
                        
                        paras = block["content"].split('\n\n')
                        final_paras = []
                        for p_idx, para in enumerate(paras):
                            if not para.strip():
                                final_paras.append(para)
                            else:
                                trans_text = translated_paras.get((b_idx, p_idx), "")
                                
                                # 🖼️ 还原图片：将占位符替换回原汁原味的图片链接！
                                images = para_images_map.get((b_idx, p_idx), [])
                                for img_i, img in enumerate(images):
                                    trans_text = trans_text.replace(f"［IMG_{img_i}］", img)
                                    trans_text = trans_text.replace(f"[IMG_{img_i}]", img) # 兼容模型把全角变为半角
                                    trans_text = trans_text.replace(f"IMG_{img_i}", img)  # 兜底兼容
                                    
                                final_paras.append(trans_text)
                                
                        block["content"] = '\n\n'.join(final_paras)

                final_markdown = '\n'.join([b["content"] for b in blocks])

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(final_markdown)
                    
                print(f"✅ 翻译完成并保存至: {output_path}")

            except Exception as e:
                print(f"❌ 翻译 {display_name} 时发生错误: {str(e)}")

    if not found_files:
        print(f"ℹ️ 源目录 {input_dir} 及其子文件夹中，没有找到可翻译的文档。")