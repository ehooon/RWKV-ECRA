# RWKV-ECRA/clients/llm_client.py
from openai import OpenAI
from config import get_llm_api_key, get_llm_base_url, get_llm_provider, get_llm_model, LLM_ENDPOINTS
from utils.retry import retry_with_fallback

class LLMClient:
    def __init__(self):
        pass

    @property
    def provider(self):
        return get_llm_provider()

    @property
    def model(self):
        return get_llm_model()
        
    @property
    def client(self):
        return OpenAI(
            api_key=get_llm_api_key(), 
            base_url=get_llm_base_url()
        )

    @retry_with_fallback(max_retries=3, delay=3)
    def chat_completion(self, messages: list, tools: list = None, enable_native_search: bool = False):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        
        provider_config = LLM_ENDPOINTS.get(self.provider, {})

        if self.provider == "baidu":
            kwargs["max_completion_tokens"] = provider_config.get("max_completion_tokens", 65536)
            
            # 🔴 全量开启文心自带的网络搜索、溯源角标及来源追踪
            if enable_native_search and provider_config.get("enable_web_search", False):
                kwargs["extra_body"] = {
                    "web_search": {
                        "enable": True,
                        "enable_citation": True,
                        "enable_trace": True
                    }
                }
                
        elif self.provider == "volcengine":
            reasoning = provider_config.get("reasoning_effort")
            if reasoning:
                kwargs["extra_body"] = {"reasoning_effort": reasoning}

        if tools: 
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "function", "function": {"name": "system_router"}}
            
        resp = self.client.chat.completions.create(**kwargs)
        
        # 🔴 拦截解析：提取附加的溯源信息（兼容 OpenAI SDK 对 extra_body 响应的处理）
        msg = resp.choices[0].message
        raw_dict = resp.model_dump()
        msg.search_results = raw_dict.get("search_results", [])
        
        return msg