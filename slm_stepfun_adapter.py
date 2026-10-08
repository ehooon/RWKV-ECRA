# RWKV-ECRA/slm_stepfun_adapter.py
# 本机无足够显存跑 RWKV 7.2B 时的替代方案：
# 用 StepFun 小模型模拟 models/rwkv_lightning 的 /high_throughput/chat/completions 端点。
# 协议与 clients/slm_client.py 的解析保持一致：
#   请求: {"contents": [...], "max_tokens": N, "stream": true, "password": "..."}
#   响应: SSE，每行 data: {"choices":[{"index": i, "delta": {"content": "..."}}]}，结尾 data: [DONE]
import asyncio
import re

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AsyncOpenAI

from config import API_KEYS, LLM_ENDPOINTS, get_slm_password

SIM_MODEL = "step-3.5-flash"          # 模拟 7B 级 SLM；不要改成 step-5-preview（那是 LLM 的角色）
UPSTREAM_CONCURRENCY = 3              # step_plan 账号级并发上限为 5，留 2 路给 LLM(step-5-preview)

app = FastAPI()
client = AsyncOpenAI(
    api_key=API_KEYS["stepfun"],
    base_url=LLM_ENDPOINTS["stepfun"]["base_url"],
    timeout=300.0,
    max_retries=6,
)
_sem = asyncio.Semaphore(UPSTREAM_CONCURRENCY)


def _to_user_message(raw: str) -> str:
    """把 RWKV 风格的裸提示词转成 chat 消息：去掉 'User: ' 前缀和 'Assistant: <think>' 后缀"""
    text = raw.strip()
    text = re.sub(r"^User:\s*", "", text)
    text = re.sub(r"Assistant:\s*<think>\s*</think>\s*$", "", text)
    return text.strip()


async def _stream_one(idx: int, content: str, max_tokens: int, queue: asyncio.Queue):
    async with _sem:
        try:
            # step-3.5-flash 是推理模型，reasoning 会吃掉 max_tokens 且不单独计数，
            # 上游额度加余量，保证 content 能完整产出（对下游等价于 RWKV 的 max_tokens 截断）。
            # 实测推理消耗可达 6k+ tokens（长章节写作），余量不足会让正文在半句处断掉。
            upstream_max_tokens = max_tokens + 8192
            stream = await client.chat.completions.create(
                model=SIM_MODEL,
                messages=[{"role": "user", "content": _to_user_message(content)}],
                max_tokens=upstream_max_tokens,
                temperature=1.0,
                top_p=0.95,
                stream=True,
                extra_body={"reasoning_effort": "low"},
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    await queue.put((idx, piece))
        except Exception as e:
            print(f"⚠️ [SLM 适配器] 第 {idx} 路上游调用失败: {e}")
        finally:
            await queue.put((idx, None))


@app.post("/high_throughput/chat/completions")
async def high_throughput_chat(request: Request):
    payload = await request.json()
    if payload.get("password") != get_slm_password():
        return JSONResponse({"error": "invalid password"}, status_code=401)

    contents = payload.get("contents") or []
    max_tokens = int(payload.get("max_tokens", 2400))
    print(f"📥 [SLM 适配器] 批次大小 {len(contents)}, max_tokens={max_tokens} -> {SIM_MODEL}")

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        tasks = [
            asyncio.create_task(_stream_one(i, c, max_tokens, queue))
            for i, c in enumerate(contents)
        ]
        finished = 0
        while finished < len(tasks):
            idx, piece = await queue.get()
            if piece is None:
                finished += 1
                continue
            chunk = {"choices": [{"index": idx, "delta": {"content": piece}}]}
            yield f"data: {json_dumps(chunk)}\n\n"
        await asyncio.gather(*tasks, return_exceptions=True)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8008, log_level="warning")
