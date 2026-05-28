# RWKV-ECRA/clients/llm_client.py
from openai import OpenAI
from config import API_KEYS
from utils.retry import retry_with_fallback

class LLMClient:
    def __init__(self):
        # ✅ OpenAI 官方库在底层会自动帮你完成 "Authorization: Bearer " + key 的字符串拼接！
        self.client = OpenAI(
            api_key=API_KEYS.get("volcengine", ""), 
            base_url="https://ark.cn-beijing.volces.com/api/v3"
        )
        self.model = "doubao-seed-2-0-lite-260428"

    @retry_with_fallback(max_retries=3, delay=3)
    def chat_completion(self, messages: list, tools: list = None):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # ✅ 把你 curl 中的 reasoning_effort 加到 extra_body 中
            # 这样既能成功传给火山服务器，又能防止本地版本较老的 openai SDK 报错
            "extra_body": {
                "reasoning_effort": "minimal"
            }
        }
        
        if tools: 
            kwargs["tools"] = tools
            # 🔴 强制锁死模型行为，剥夺选择权，必须调用我们的路由工具
            kwargs["tool_choice"] = {"type": "function", "function": {"name": "system_router"}}
            
        return self.client.chat.completions.create(**kwargs).choices[0].message