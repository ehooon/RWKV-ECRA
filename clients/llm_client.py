from openai import OpenAI
from config import API_KEYS
from utils.retry import retry_with_fallback

class LLMClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=API_KEYS.get("baidu", ""), 
            base_url="https://aistudio.baidu.com/llm/lmapi/v3"
        )
        self.model = "ernie-5.1"

    @retry_with_fallback(max_retries=3, delay=3)
    def chat_completion(self, messages: list, tools: list = None):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_completion_tokens": 65536,
            "extra_body": {
                "web_search": {
                    "enable": True
                }
            }
        }
        if tools: 
            kwargs["tools"] = tools
            
        return self.client.chat.completions.create(**kwargs).choices[0].message