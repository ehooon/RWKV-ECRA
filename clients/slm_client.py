import json
import requests
import time
from config import SLM_CONFIG

class SLMClient:
    def __init__(self):
        self.endpoint = SLM_CONFIG.get("endpoint", "http://192.168.0.125:8000/v1/chat/completions")
        self.password = SLM_CONFIG.get("password", "rwkv7_13.3b") 
        self.headers = {"Content-Type": "application/json"}

    def batch_generate(self, contents: list[str], tracker=None) -> list[str]:
        payload = {
            "contents": contents,
            "max_tokens": 1500,       # 🚨 限制最大输出，防止失控
            "temperature": 0.6,       # 🚨 降低随机性，保证提炼准确性
            "top_k": 50,
            "top_p": 0.85,
            "alpha_presence": 0.5,    # 🚨 鼓励输出新内容
            "alpha_frequency": 0.8,   # 🚨 强力压制重复词，根治复读机
            "alpha_decay": 0.99,
            "stream": True,
            "password": self.password
        }
        
        results = {i: "" for i in range(len(contents))}
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = requests.post(self.endpoint, json=payload, headers=self.headers, stream=True, timeout=120)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code} - {response.content.decode('utf-8', errors='ignore')}")

                received_valid_chunk = False 

                for line in response.iter_lines():
                    if not line: continue
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if "error" in decoded.lower() and not decoded.startswith("data:"):
                        raise RuntimeError(f"【后端业务致命报错】: {decoded}")

                    json_str = ""
                    if decoded.startswith("data:"):
                        json_str = decoded[5:].strip()
                    elif decoded.startswith("{"):
                        json_str = decoded
                        
                    if json_str == "[DONE]" or not json_str: continue

                    try:
                        data = json.loads(json_str)
                        if "error" in data:
                            raise RuntimeError(f"【数据流异常】: {data['error']}")
                            
                        for choice in data.get("choices", []):
                            raw_idx = choice.get("index")
                            if raw_idx is not None:
                                idx = int(raw_idx)
                                delta = choice.get("delta", {})
                                content = delta.get("content", choice.get("text", ""))
                                if idx in results and content:
                                    results[idx] += content
                                    received_valid_chunk = True
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        raise e 

                if not received_valid_chunk:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue

                final_responses = [results[i] for i in range(len(contents))]
                if tracker:
                    for idx, text in enumerate(final_responses):
                        tracker.track_slm(input_prompt=contents[idx], output_text=text)
                return final_responses
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"网络异常: {str(e)}")
            except RuntimeError as e:
                raise e