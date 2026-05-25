import re
import tiktoken

_tokenizer = tiktoken.get_encoding("cl100k_base")

def get_token_count(text: str) -> int:
    return len(_tokenizer.encode(text, disallowed_special=()))

def semantic_chunk_text(text: str, max_tokens: int = 800, overlap_ratio: float = 0.1) -> list[str]:
    overlap_tokens = int(max_tokens * overlap_ratio)
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    
    chunks = []
    current_chunk = ""
    current_tokens = 0
    
    for para in paragraphs:
        para_tokens = get_token_count(para)
        
        if current_tokens + para_tokens <= max_tokens:
            separator = "\n\n" if current_chunk else ""
            current_chunk += (separator + para)
            current_tokens += para_tokens
            continue
            
        if current_chunk:
            chunks.append(current_chunk.strip())
            overlap_text = _extract_token_overlap(current_chunk, overlap_tokens)
            current_chunk = overlap_text
            current_tokens = get_token_count(overlap_text)
            
        if para_tokens > max_tokens:
            sentences = re.split(r'(?<=[。！？.!?])\s*(?=[A-Z\u4e00-\u9fa5])', para)
            for sentence in sentences:
                if not sentence.strip(): continue
                sent_tokens = get_token_count(sentence)
                separator = " " if _is_english_ending(current_chunk) else ""
                
                if current_tokens + sent_tokens <= max_tokens:
                    current_chunk += (separator + sentence)
                    current_tokens += sent_tokens
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        overlap_text = _extract_token_overlap(current_chunk, overlap_tokens)
                        current_chunk = overlap_text
                        current_tokens = get_token_count(overlap_text)
                    
                    if sent_tokens > max_tokens:
                        fallback_pieces = _safe_fallback_chunk(sentence, max_tokens)
                        for idx, piece in enumerate(fallback_pieces[:-1]):
                            chunks.append((current_chunk + " " + piece).strip())
                            current_chunk = _extract_token_overlap(piece, overlap_tokens)
                        current_chunk = current_chunk + " " + fallback_pieces[-1]
                        current_tokens = get_token_count(current_chunk)
                    else:
                        current_chunk = current_chunk + separator + sentence
                        current_tokens = get_token_count(current_chunk)
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para
            current_tokens = get_token_count(current_chunk)
            
    if current_chunk: chunks.append(current_chunk.strip())
    return chunks

def _extract_token_overlap(text: str, target_tokens: int) -> str:
    if target_tokens <= 0: return ""
    tokens = _tokenizer.encode(text, disallowed_special=())
    if len(tokens) <= target_tokens: return text
    tail_text = _tokenizer.decode(tokens[-target_tokens:])
    split_match = re.search(r'[。！？.!?\n]', tail_text)
    if split_match: return tail_text[split_match.start() + 1:].strip()
    return tail_text.strip()

def _is_english_ending(text: str) -> bool:
    if not text: return False
    return re.match(r'[a-zA-Z0-9.,!?;:]', text[-1]) is not None

def _safe_fallback_chunk(text: str, max_tokens: int) -> list[str]:
    tokens = _tokenizer.encode(text, disallowed_special=())
    pieces = []
    for i in range(0, len(tokens), max_tokens):
        pieces.append(_tokenizer.decode(tokens[i : i + max_tokens]))
    return pieces