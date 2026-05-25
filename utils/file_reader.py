import os

def _read_with_fallback(file_path: str) -> str:
    encodings = ['utf-8', 'gb18030', 'gbk', 'utf-16', 'big5', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def read_txt(file_path: str) -> str:
    return _read_with_fallback(file_path)

def read_md(file_path: str) -> str:
    return _read_with_fallback(file_path)

# 🚨 在此预留接入你的 PaddleOCR 等扩展插槽
FILE_READERS = {
    ".txt": read_txt,
    ".md": read_md
}

def read_local_file(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"未找到文件: {file_path}")
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in FILE_READERS:
        return FILE_READERS[ext](file_path)
    else:
        raise ValueError(f"暂不支持读取 {ext} 类型。当前支持: {list(FILE_READERS.keys())}")