# RWKV-ECRA/api.py
import os
import shutil
import json
import uvicorn
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import config
from agent.orchestrator import Orchestrator
from utils.task_manager import record_task, get_all_tasks, request_stop, delete_task, is_task_stopped
from main import setup_env

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

# =====================================
# 2. 基础系统接口 (上传与清理)
# =====================================
@app.post("/api/v1/upload")
@app.post("/frontend-api/upload")
async def upload_files(files: List[UploadFile] = File(...), paths: List[str] = Form(None)):
    input_dir = config.DATA_PIPELINE["input_directory"]
    saved_files = []
    
    for i, file in enumerate(files):
        # 兼容处理带层级的相对路径
        rel_path = paths[i] if paths and i < len(paths) else file.filename
        safe_path = os.path.normpath(rel_path).replace("\\", "/")
        
        # 拦截跨目录穿越攻击
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
        config.DATA_PIPELINE.get("debug_directory", "./data/debug_slm")
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
    return {"code": 200, "message": "运行环境及缓存已重置"}

# =====================================
# 3. 文件夹感知的文件管理 API 
# =====================================
@app.get("/api/v1/files")
@app.get("/frontend-api/files")
def list_input_files():
    input_dir = config.DATA_PIPELINE["input_directory"]
    files = []
    if os.path.exists(input_dir):
        # 递归遍历所有文件夹与子文件
        for root, _, filenames in os.walk(input_dir):
            for f in filenames:
                if not f.startswith("."):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, input_dir)
                    # 统一为前端返回正斜杠路径
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
        # 尝试顺手清理空文件夹
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
        # 若是图片资源则直接作为文件流返回
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']:
            return FileResponse(file_path)
            
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return PlainTextResponse(f.read())
            
    return PlainTextResponse("File not found", status_code=404)

# =====================================
# 4. 核心执行接口 (后台异步挂载)
# =====================================
def background_analyze(task_id: str, req: AnalyzeRequest, task_output_dir: str):
    if req.llm_api_key: config.override_llm_key.set(req.llm_api_key)
    if req.llm_base_url: config.override_llm_url.set(req.llm_base_url)
    if req.llm_provider: config.override_llm_provider.set(req.llm_provider)
    if req.slm_endpoint: config.override_slm_endpoint.set(req.slm_endpoint)
    if req.slm_password is not None: config.override_slm_password.set(req.slm_password)

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

@app.post("/api/v1/analyze")
@app.post("/frontend-api/analyze")
def analyze_endpoint(req: AnalyzeRequest, bg_tasks: BackgroundTasks):
    task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    task_output_dir = os.path.join(config.DATA_PIPELINE["output_directory"], task_id)
    
    record_task(task_id, req.query, "running", task_output_dir)
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
    jsonl_path = os.path.join(task_output_dir, f"{task_id}_03_结构化溯源数据.jsonl")
    
    if not os.path.exists(jsonl_path):
        return {"code": 404, "message": "该任务未生成结构化报告，可能仍在执行中"}
        
    report_data = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                report_data.append(json.loads(line.strip()))
                
    return {"code": 200, "data": report_data}

if __name__ == "__main__":
    print("[系统] API 服务启动中... 监听: http://0.0.0.0:8787")
    uvicorn.run("api:app", host="0.0.0.0", port=8787)