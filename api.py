# RWKV-ECRA/api.py
import os
import shutil
import json
import uvicorn
import uuid
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import config
from agent.orchestrator import Orchestrator
from utils.task_manager import record_task, get_all_tasks, request_stop, delete_task, is_task_stopped
from utils.token_tracker import global_token_tracker, current_task_id
from main import setup_env
import glob

setup_env()

app = FastAPI(title="RWKV-ECRA Agent API", description="支持前端隔离请求、文件上传与历史回溯")

# =====================================
# 1. 前端参数模型
# =====================================
class AnalyzeRequest(BaseModel):
    query: str
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_provider: Optional[str] = None
    slm_endpoint: Optional[str] = None
    slm_password: Optional[str] = None
    queued_at: Optional[str] = None  
    slm_async_enabled: Optional[bool] = None

# =====================================
# 2. 基础系统接口 (上传与清理)
# =====================================
@app.post("/api/v1/upload")
@app.post("/frontend-api/upload")
async def upload_files(files: List[UploadFile] = File(...), paths: List[str] = Form(None)):
    input_dir = config.DATA_PIPELINE["input_directory"]
    saved_files = []
    
    for i, file in enumerate(files):
        rel_path = paths[i] if paths and i < len(paths) else file.filename
        safe_path = os.path.normpath(rel_path).replace("\\", "/")
        if safe_path.startswith("..") or safe_path.startswith("/"):
            continue
        file_location = os.path.join(input_dir, safe_path)
        os.makedirs(os.path.dirname(file_location), exist_ok=True)
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        saved_files.append(safe_path)
    return {"code": 200, "message": "上传成功", "data": {"saved": saved_files}}

@app.post("/api/v1/cleanup")
@app.post("/frontend-api/cleanup")
def cleanup_environment():
    dirs_to_clean = [
        config.DATA_PIPELINE["input_directory"],
        config.DATA_PIPELINE["checkpoint_directory"],
        config.DATA_PIPELINE.get("debug_directory", "./data/debug_slm"),
        config.DATA_PIPELINE.get("asset_directory", "./data/knowledge_assets")
    ]
    for directory in dirs_to_clean:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    pass
                    
    # 🌟 一并清零 Token 全局与历史任务计数器
    global_token_tracker.reset()
    
    return {"code": 200, "message": "运行环境及缓存已重置"}

# =====================================
# ✨ 新增：Token 账本双重查询接口
# =====================================
@app.get("/api/v1/metrics/tokens")
@app.get("/frontend-api/metrics/tokens")
def get_global_token_metrics():
    """实时获取系统 SLM 和 LLM 的全局 Tokens 总开销和所有历史任务数据"""
    return {
        "code": 200,
        "message": "success",
        "data": global_token_tracker.get_stats()
    }

@app.get("/api/v1/metrics/tokens/{task_id}")
@app.get("/frontend-api/metrics/tokens/{task_id}")
def get_task_token_metrics(task_id: str):
    """精准获取某一个历史任务的 Token 开销"""
    return {
        "code": 200,
        "message": "success",
        "data": global_token_tracker.get_stats(task_id)
    }

# =====================================
# 3. 文件夹感知的文件管理 API 
# =====================================
@app.get("/api/v1/files")
@app.get("/frontend-api/files")
def list_input_files():
    input_dir = config.DATA_PIPELINE["input_directory"]
    files = []
    if os.path.exists(input_dir):
        for root, _, filenames in os.walk(input_dir):
            for f in filenames:
                if not f.startswith("."):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, input_dir)
                    files.append(rel_path.replace("\\", "/"))
    return {"code": 200, "data": files}

@app.delete("/api/v1/files")
@app.delete("/frontend-api/files")
def delete_input_file(path: str):
    input_dir = config.DATA_PIPELINE["input_directory"]
    safe_path = os.path.normpath(path).replace("\\", "/")
    if safe_path.startswith("..") or safe_path.startswith("/"):
        return {"code": 403, "message": "非法路径"}
    file_path = os.path.join(input_dir, safe_path)
    if os.path.exists(file_path):
        os.remove(file_path)
        dir_name = os.path.dirname(file_path)
        try:
            if not os.listdir(dir_name) and dir_name != input_dir:
                os.rmdir(dir_name)
        except Exception:
            pass
        return {"code": 200, "message": f"{path} 已删除"}
    return {"code": 404, "message": "文件不存在"}

@app.get("/api/v1/files/content")
@app.get("/frontend-api/files/content")
def get_input_file(path: str):
    input_dir = config.DATA_PIPELINE["input_directory"]
    safe_path = os.path.normpath(path).replace("\\", "/")
    if safe_path.startswith("..") or safe_path.startswith("/"):
        return PlainTextResponse("Invalid path", status_code=403)
    file_path = os.path.join(input_dir, safe_path)
    if os.path.exists(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']:
            return FileResponse(file_path)
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse("File not found", status_code=404)

# =====================================
# 4. 核心执行接口 (后台异步挂载)
# =====================================
def background_analyze(task_id: str, req: AnalyzeRequest, task_output_dir: str):
    # ✨ 核心绑定：在当前执行上下文中注入 task_id，后续所有 LLM 的子线程调用都能感知到
    token_ctx = current_task_id.set(task_id)
    
    if req.llm_api_key: config.override_llm_key.set(req.llm_api_key)
    if req.llm_base_url: config.override_llm_url.set(req.llm_base_url)
    if req.llm_provider: config.override_llm_provider.set(req.llm_provider)
    if req.slm_endpoint: config.override_slm_endpoint.set(req.slm_endpoint)
    if req.slm_password is not None: config.override_slm_password.set(req.slm_password)
    if req.slm_async_enabled is not None: config.override_slm_async_enabled.set(req.slm_async_enabled)

    try:
        agent = Orchestrator()
        result = agent.run(user_query=req.query, task_id=task_id)
        if not is_task_stopped(task_id):
            record_task(task_id, req.query, "completed", task_output_dir)
    except Exception as e:
        if not is_task_stopped(task_id):
            record_task(task_id, req.query, "failed", task_output_dir, str(e))
    finally:
        config.override_llm_key.set(None)
        config.override_llm_url.set(None)
        config.override_llm_provider.set(None)
        config.override_slm_endpoint.set(None)
        config.override_slm_password.set(None)
        config.override_slm_async_enabled.set(None)
        current_task_id.reset(token_ctx)

@app.get("/frontend-api/config")
def get_frontend_config():
    return {
        "code": 200,
        "data": {
            "slm_async_enabled": config.get_slm_async_enabled(),
            "slm_concurrency": config.get_slm_concurrency(),
            "slm_async_parallelism": config.get_slm_async_parallelism(),
            "llm_concurrency": config.get_llm_concurrency()
        }
    }

@app.post("/api/v1/analyze")
@app.post("/frontend-api/analyze")
def analyze_endpoint(req: AnalyzeRequest, bg_tasks: BackgroundTasks):
    task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    task_output_dir = os.path.join(config.DATA_PIPELINE["output_directory"], task_id)
    
    record_task(task_id, req.query, "running", task_output_dir, queued_at=req.queued_at)
    bg_tasks.add_task(background_analyze, task_id, req, task_output_dir)
    
    return {
        "code": 200,
        "status": "success",
        "task_id": task_id,
        "message": "分析任务已提交后台执行"
    }

# =====================================
# 5. 数据回溯及运维控制接口
# =====================================
@app.get("/frontend-api/history")
def get_task_history():
    return {"code": 200, "data": get_all_tasks()}

@app.post("/api/v1/analyze/{task_id}/stop")
@app.post("/frontend-api/analyze/{task_id}/stop")
@app.post("/frontend-api/history/{task_id}/stop")
def stop_task_endpoint(task_id: str):
    if not task_id or task_id == "undefined":
        return {"code": 400, "message": "无效的任务 ID"}
    request_stop(task_id)
    return {"code": 200, "message": f"任务 {task_id} 已发出停止指令"}

@app.delete("/api/v1/history/{task_id}")
@app.delete("/frontend-api/history/{task_id}")
def delete_task_endpoint(task_id: str):
    if not task_id or task_id == "undefined":
        return {"code": 400, "message": "无效的任务 ID"}
    delete_task(task_id)
    return {"code": 200, "message": f"任务 {task_id} 及其数据已被物理删除"}



@app.get("/frontend-api/history/{task_id}/report")
def get_task_report(task_id: str):
    if not task_id or task_id == "undefined":
        return {"code": 404, "message": "无有效的任务 ID 供查询"}
        
    task_output_dir = os.path.join(config.DATA_PIPELINE["output_directory"], task_id)
    if not os.path.exists(task_output_dir):
        return {"code": 404, "message": "报告文件夹在物理系统上已丢失或被移除"}
        
    jsonl_candidates = []
    md_candidates = []
    
    for root_dir, _, files in os.walk(task_output_dir):
        for f in files:
            full_path = os.path.join(root_dir, f)
            if f.endswith(".jsonl"):
                jsonl_candidates.append(full_path)
            elif f.endswith(".md"):
                md_candidates.append(full_path)

    if jsonl_candidates:
        target = sorted(jsonl_candidates, key=os.path.getmtime, reverse=True)[0]
        report_data = []
        with open(target, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    report_data.append(json.loads(line.strip()))
        return {"code": 200, "data": report_data}
        
    if md_candidates:
        target = sorted(md_candidates, key=os.path.getmtime, reverse=True)[0]
        with open(target, "r", encoding="utf-8") as f:
            md_content = f.read()
        return {"code": 200, "data": [{"record_type": "final_beautified_markdown", "content": md_content}]}

    return {"code": 404, "message": "系统已扫描文件夹，但未发现任何 JSONL 或 MD 格式的报告"}

if __name__ == "__main__":
    print("[系统] API 服务启动中... 监听: http://0.0.0.0:8787")
    uvicorn.run("api:app", host="0.0.0.0", port=8787)