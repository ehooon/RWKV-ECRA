# RWKV-ECRA/frontend/server.py
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

FRONTEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = FRONTEND_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "data" / "output"
API_BASE_URL = os.environ.get("RWKV_ECRA_API_BASE", "http://127.0.0.1:8787")

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records

def file_time(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "-"

def find_report_files(base: Path) -> tuple[Path | None, Path | None]:
    jsonl_candidates = sorted(
        [p for p in base.glob("*.jsonl") if "结构化" in p.name or "_03_" in p.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    md_candidates = sorted(
        [p for p in base.glob("*.md") if "深度排版" in p.name or "_02_" in p.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not md_candidates:
        md_candidates = sorted(base.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return (jsonl_candidates[0] if jsonl_candidates else None, md_candidates[0] if md_candidates else None)

def collect_history() -> list[dict[str, Any]]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    items: dict[str, dict[str, Any]] = {}

    task_records = read_jsonl(OUTPUT_DIR / "tasks.jsonl")
    for record in task_records:
        task_id = str(record.get("task_id") or "").strip()
        if not task_id:
            continue
        result_dir = Path(record.get("result_dir") or OUTPUT_DIR / task_id)
        if not result_dir.is_absolute():
            result_dir = PROJECT_DIR / result_dir
        jsonl_path, md_path = find_report_files(result_dir) if result_dir.exists() else (None, None)
        items[task_id] = {
            "id": task_id,
            "title": task_id,
            "query": record.get("query") or "",
            "status": record.get("status") or "ready",
            "progress": record.get("progress") or "",
            "updated_at": record.get("timestamp") or file_time(jsonl_path or md_path or OUTPUT_DIR),
            "path": str(result_dir),
            "has_structured_report": bool(jsonl_path),
        }

    for child in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        jsonl_path, md_path = find_report_files(child)
        if not jsonl_path and not md_path:
            continue
        items.setdefault(
            child.name,
            {
                "id": child.name,
                "title": child.name,
                "query": "",
                "status": "ready",
                "progress": "",
                "updated_at": file_time(jsonl_path or md_path or child),
                "path": str(child),
                "has_structured_report": bool(jsonl_path),
            },
        )

    root_jsonl, root_md = find_report_files(OUTPUT_DIR)
    if root_jsonl or root_md:
        sample_id = "output-root"
        items.setdefault(
            sample_id,
            {
                "id": sample_id,
                "title": "data/output 根目录报告",
                "query": "本地样例或未归入任务目录的最终研报",
                "status": "ready",
                "progress": "",
                "updated_at": file_time(root_jsonl or root_md or OUTPUT_DIR),
                "path": str(OUTPUT_DIR),
                "has_structured_report": bool(root_jsonl),
            },
        )

    return sorted(items.values(), key=lambda item: item.get("updated_at") or "", reverse=True)

def resolve_report_paths(report_id: str) -> tuple[Path | None, Path | None, dict[str, Any] | None]:
    history = collect_history()
    match = next((item for item in history if item["id"] == report_id), None)
    if not match:
        return None, None, None
    base = Path(match["path"])
    jsonl_path, md_path = find_report_files(base)
    return jsonl_path, md_path, match

def structured_report(report_id: str) -> dict[str, Any]:
    jsonl_path, md_path, meta = resolve_report_paths(report_id)
    if not meta:
        raise FileNotFoundError(report_id)

    sources: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    markdown = ""

    if jsonl_path:
        for record in read_jsonl(jsonl_path):
            record_type = record.get("record_type")
            if record_type == "global_citation_map":
                sources = record.get("data") or []
            elif record_type == "report_node":
                nodes.append(
                    {
                        "id": record.get("node_id") or f"node_{len(nodes) + 1}",
                        "title": record.get("title") or f"章节 {len(nodes) + 1}",
                        "content": record.get("content") or "",
                        "sources": record.get("sources") or [],
                    }
                )
            elif record_type == "final_beautified_markdown":
                markdown = record.get("content") or markdown

    if not nodes and md_path:
        markdown = md_path.read_text(encoding="utf-8", errors="replace")

    return {
        "id": report_id,
        "title": meta.get("title") or report_id,
        "status": meta.get("status") or "ready",
        "updated_at": meta.get("updated_at") or "-",
        "kind": "structured" if nodes else "markdown",
        "sources": sources,
        "nodes": nodes,
        "markdown": markdown,
    }

# 🔴 改动：将 query 合并进入 target
def proxy_api(path: str, query: str, method: str, body: bytes | None = None) -> tuple[int, bytes, str]:
    full_path = f"{path}?{query}" if query else path
    target = urllib.parse.urljoin(API_BASE_URL, full_path)
    request = urllib.request.Request(
        target,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get_content_type()
    except OSError as exc:
        payload = json.dumps({"code": 502, "message": f"API proxy failed: {exc}"}, ensure_ascii=False).encode("utf-8")
        return 502, payload, "application/json"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/frontend-api/history":
            self.send_json({"code": 200, "data": collect_history()})
            return

        if path.startswith("/frontend-api/report/"):
            report_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            try:
                self.send_json({"code": 200, "data": structured_report(report_id)})
            except FileNotFoundError:
                self.send_json({"code": 404, "message": "report not found"}, status=404)
            return
            
        if path.startswith("/frontend-api/"):
            status, payload, content_type = proxy_api(parsed.path, parsed.query, "GET", None)
            self.send_response(status)
            self.send_header("Content-Type", content_type or "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/frontend-api/"):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b"{}"
            
            # 特殊处理 multipart/form-data 类型 (上传文件场景)
            content_type = self.headers.get("Content-Type", "application/json")
            full_path = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
            target = urllib.parse.urljoin(API_BASE_URL, full_path)
            
            request = urllib.request.Request(target, data=body, method="POST", headers={"Content-Type": content_type})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    status, payload, ctype = response.status, response.read(), response.headers.get_content_type()
            except urllib.error.HTTPError as exc:
                status, payload, ctype = exc.code, exc.read(), exc.headers.get_content_type()
            except OSError as exc:
                payload = json.dumps({"code": 502, "message": f"API proxy failed: {exc}"}, ensure_ascii=False).encode("utf-8")
                status, ctype = 502, "application/json"

            self.send_response(status)
            self.send_header("Content-Type", ctype or "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_json({"code": 404, "message": "not found"}, status=404)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/frontend-api/"):
            status, payload, content_type = proxy_api(parsed.path, parsed.query, "DELETE", None)
            self.send_response(status)
            self.send_header("Content-Type", content_type or "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_json({"code": 404, "message": "not found"}, status=404)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        relative = Path(urllib.parse.unquote(path.lstrip("/")))
        target = (FRONTEND_DIR / relative).resolve()
        if FRONTEND_DIR not in target.parents and target != FRONTEND_DIR:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

def main() -> None:
    parser = argparse.ArgumentParser(description="Serve RWKV-ECRA frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5177, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"RWKV-ECRA frontend: http://{args.host}:{args.port}")
    print(f"Project data output: {OUTPUT_DIR}")
    print(f"API proxy target: {API_BASE_URL}")
    server.serve_forever()

if __name__ == "__main__":
    main()