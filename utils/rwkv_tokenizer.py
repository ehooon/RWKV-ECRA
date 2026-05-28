import os

# ==========================================
# The RWKV Language Model Official Tokenizer
# https://github.com/BlinkDL/RWKV-LM
# ==========================================

class TRIE:
    __slots__ = tuple("ch,to,values,front".split(","))
    to:list
    values:set
    def __init__(self, front=None, ch=None):
        self.ch = ch
        self.to = [None for ch in range(256)]
        self.values = set()
        self.front = front

    def __repr__(self):
        fr = self
        ret = []
        while(fr!=None):
            if(fr.ch!=None):
                ret.append(fr.ch)
            fr = fr.front
        return "<TRIE %s %s>"%(ret[::-1], self.values)
    
    def add(self, key:bytes, idx:int=0, val=None):
        if(idx == len(key)):
            if(val is None):
                val = key
            self.values.add(val)
            return self
        ch = key[idx]
        if(self.to[ch] is None):
            self.to[ch] = TRIE(front=self, ch=ch)
        return self.to[ch].add(key, idx=idx+1, val=val)
    
    def find_longest(self, key:bytes, idx:int=0):
        u:TRIE = self
        ch:int = key[idx]
        
        while(u.to[ch] is not None):
            u = u.to[ch]
            idx += 1
            if(u.values):
                ret = idx, u, u.values
            if(idx==len(key)):
                break
            ch = key[idx]
        return ret


class RWKVTokenizer:
    def __init__(self, file_name="rwkv_vocab_v20230424.txt"):
        self.idx2token = {}
        sorted_tokens = [] # must be already sorted
        
        # --- 补充工程级鲁棒性：寻找词表文件 ---
        possible_paths = [
            file_name,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), file_name)
        ]
        
        actual_path = None
        for p in possible_paths:
            if os.path.exists(p):
                actual_path = p
                break
                
        if not actual_path:
            raise FileNotFoundError(f"未找到词表文件 {file_name}，请确保其位于项目目录中。")
        # -----------------------------------

        with open(actual_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for l in lines:
            idx = int(l[:l.index(' ')])
            x = eval(l[l.index(' '):l.rindex(' ')])
            x = x.encode("utf-8") if isinstance(x, str) else x
            assert isinstance(x, bytes)
            assert len(x) == int(l[l.rindex(' '):])
            sorted_tokens += [x]
            self.idx2token[idx] = x

        self.token2idx = {}
        for k,v in self.idx2token.items():
            self.token2idx[v] = int(k)

        self.root = TRIE()
        for t, i in self.token2idx.items():
            _ = self.root.add(t, val=(t, i))

    def encodeBytes(self, src:bytes):
        idx:int = 0
        tokens = []
        while (idx < len(src)):
            _idx:int = idx
            idx, _, values = self.root.find_longest(src, idx)
            assert(idx != _idx)
            _, token = next(iter(values))            
            tokens.append(token)
        return tokens

    def decodeBytes(self, tokens):
        return b''.join(map(lambda i: self.idx2token[i], tokens))

    def encode(self, src: str) -> list[int]:
        return self.encodeBytes(src.encode("utf-8"))

    def decode(self, tokens: list[int]) -> str:
        # 🚨 略微修改官方的 try-except 机制：
        # 因为 chunker.py 在强行切断 Token 时，可能会刚好把一个汉字的三字节切开，导致 decode 失败。
        # 官方代码会直接 catch 整个错误并返回单个 '\ufffd' 导致整个段落丢失。
        # 这里改用 errors='replace'，遇到断裂字节只产生单个乱码字符，保留全文其他 99% 的有效内容。
        return self.decodeBytes(tokens).decode('utf-8', errors='replace')

    def printTokens(self, tokens):
        for i in tokens:
            s = self.idx2token[i]
            try:
                s = s.decode('utf-8')
            except:
                pass
            print(f'{repr(s)}{i}', end=' ')
        print()