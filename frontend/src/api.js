// RWKV-ECRA/frontend/src/api.js

export async function apiFetch(path, options) {
  const response = await fetch(path, options);
  
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.message || `${response.status} ${response.statusText}`);
  }
  
  const data = await response.json();
  
  if (data && data.code && data.code !== 200) {
    throw new Error(data.message || `Error code: ${data.code}`);
  }
  
  return data;
}

export async function getHistory() {
  const payload = await apiFetch("/frontend-api/history");
  const items = payload.data || [];
  
  return items.map(item => ({
    id: item.task_id || item.id,
    title: item.title || item.task_id || item.id,
    query: item.query || "",
    status: item.status || "ready",
    progress: item.progress || "",
    updated_at: item.timestamp || item.updated_at || "-",
    queued_at: item.queued_at || "",  // ✨ 这里就是映射过来的排队时间
    path: item.result_dir || item.path || ""
  }));
}

export async function getReport(id) {
  const payload = await apiFetch(`/frontend-api/history/${encodeURIComponent(id)}/report`);
  
  const records = payload.data || [];
  const report = {
    id,
    sources: [],
    nodes: [],
    markdown: ""
  };
  
  for (const record of records) {
    if (record.record_type === "global_citation_map") {
      report.sources = record.data || [];
    } else if (record.record_type === "report_node") {
      report.nodes.push({
        id: record.node_id,
        title: record.title,
        content: record.content,
        sources: record.sources || []
      });
    } else if (record.record_type === "final_beautified_markdown") {
      report.markdown = record.content || "";
    }
  }
  
  report.kind = report.nodes.length > 0 ? "structured" : "markdown";
  return report;
}

export async function startAnalyze(body) {
  return apiFetch("/frontend-api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function stopTask(id) {
  return apiFetch(`/frontend-api/analyze/${encodeURIComponent(id)}/stop`, {
    method: "POST",
  });
}

export async function deleteTask(id) {
  return apiFetch(`/frontend-api/history/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ===================================
// 文件管理系列接口
// ===================================
export async function getFiles() {
  const payload = await apiFetch("/frontend-api/files");
  return payload.data || [];
}

export async function deleteFile(path) {
  return apiFetch(`/frontend-api/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
}

export async function getFileContent(path) {
  const response = await fetch(`/frontend-api/files/content?path=${encodeURIComponent(path)}`);
  if (!response.ok) throw new Error("获取文件内容失败");
  
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.startsWith("image/")) {
    const blob = await response.blob();
    return { type: "image", url: URL.createObjectURL(blob) };
  }
  
  return { type: "text", content: await response.text() };
}

export async function uploadFile(fileList) {
  const formData = new FormData();
  
  for (let i = 0; i < fileList.length; i++) {
    const file = fileList[i];
    formData.append("files", file);
    formData.append("paths", file.webkitRelativePath || file.name);
  }
  
  const response = await fetch("/frontend-api/upload", {
    method: "POST",
    body: formData,
  });
  
  if (!response.ok) throw new Error("上传失败");
  const data = await response.json();
  if (data.code && data.code !== 200) throw new Error(data.message);
  return data;
}