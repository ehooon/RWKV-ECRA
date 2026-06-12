// RWKV-ECRA/frontend/src/App.jsx
import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { getHistory, getReport, startAnalyze, stopTask, deleteTask, getFiles, deleteFile, getFileContent, uploadFile } from "./api.js";
import { extractMarkdownOutline, renderMarkdown, reportToMarkdown } from "./markdown.js";
import { Copy, FileText, Play, RefreshCw, Search, SquarePen, StopCircle, Trash2, ChevronDown, ChevronRight, Loader2, FolderOpen, Folder, File, ListPlus, X } from "lucide-react";
import ArchitectureGraph from "./ArchitectureGraph.jsx";

function formatCurrentTime() {
  const d = new Date();
  const Y = d.getFullYear();
  const M = String(d.getMonth() + 1).padStart(2, '0');
  const D = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  return `${Y}-${M}-${D} ${h}:${m}:${s}`;
}

function parseTaskTime(taskId) {
  if (!taskId) return null;
  const match = taskId.match(/TASK_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`;
  return null;
}

function TaskTimingWidget({ task }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!task) return null;
  const runTime = parseTaskTime(task.id);
  const isDone = task.status === 'completed' || task.status === 'failed' || task.status === 'ready';

  // 收起状态的简约 UI
  if (!isOpen) {
    return (
      <button className="task-timing-toggle" onClick={() => setIsOpen(true)} title="查看任务时间线">
        ⏱️ 任务耗时
      </button>
    );
  }

  // 展开状态的完整 UI
  return (
    <div className="task-timing-widget">
      <div className="timing-header" onClick={() => setIsOpen(false)}>
        <div className="timing-title">⏱️ 任务时间线</div>
        <button className="ghost-button compact-btn icon-only" title="收起面板">
          <ChevronDown size={14} />
        </button>
      </div>
      
      <div className="timing-body">
        {task.queued_at && (
          <div className="timing-row">
            <span className="timing-label">提交排队:</span>
            <span className="timing-val">{task.queued_at}</span>
          </div>
        )}
        <div className="timing-row">
          <span className="timing-label">开始运行:</span>
          <span className="timing-val">{runTime || task.updated_at}</span>
        </div>
        <div className="timing-row">
          <span className="timing-label">报告生成:</span>
          <span className="timing-val">{isDone ? task.updated_at : "正在执行..."}</span>
        </div>
      </div>
    </div>
  );
}

function buildFileTree(paths) {
  const root = { name: 'root', type: 'folder', children: {}, path: '' };
  paths.forEach(path => {
    const parts = path.split(/[/\\]/).filter(Boolean);
    let current = root;
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          type: isFile ? 'file' : 'folder',
          path: isFile ? path : parts.slice(0, index + 1).join('/'),
          children: {}
        };
      }
      current = current.children[part];
    });
  });
  return root;
}

function getAllFilePaths(node) {
  let paths = [];
  if (node.type === 'file') {
    paths.push(node.path);
  } else if (node.children) {
    Object.values(node.children).forEach(child => {
      paths = paths.concat(getAllFilePaths(child));
    });
  }
  return paths;
}

function FileTreeNode({ node, level = 0, onView, onDelete }) {
  const [isOpen, setIsOpen] = useState(false);
  const basePadding = 8;
  const currentIndent = basePadding + level * 16;
  const fileIndent = currentIndent + 22;

  if (node.type === 'file') {
    return (
      <div className="vsc-row" style={{ paddingLeft: `${fileIndent}px` }}>
        <div className="vsc-item" onClick={() => onView(node.path)}>
          <File size={14} className="vsc-icon file-icon" />
          <span className="vsc-label" title={node.name}>{node.name}</span>
        </div>
        <button className="vsc-action" onClick={(e) => { e.stopPropagation(); onDelete(node); }} title="删除文件">
          <Trash2 size={13}/>
        </button>
      </div>
    );
  }

  const childrenNodes = Object.values(node.children).sort((a, b) => {
    if (a.type === b.type) return a.name.localeCompare(b.name);
    return a.type === 'folder' ? -1 : 1;
  });

  return (
    <>
      <div className="vsc-row" style={{ paddingLeft: `${currentIndent}px` }} onClick={() => setIsOpen(!isOpen)}>
        <div className="vsc-item">
          <span className="vsc-chevron">
            {isOpen ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
          </span>
          <Folder size={14} className="vsc-icon folder-icon" fill={isOpen ? "#bae6fd" : "none"} />
          <span className="vsc-label" title={node.name}>{node.name}</span>
        </div>
        <button className="vsc-action" onClick={(e) => { e.stopPropagation(); onDelete(node); }} title="删除整个文件夹及其内容">
          <Trash2 size={13}/>
        </button>
      </div>
      {isOpen && childrenNodes.map(child => (
        <FileTreeNode key={child.name} node={child} level={level + 1} onView={onView} onDelete={onDelete} />
      ))}
    </>
  );
}

function StatusPill({ status }) {
  const normalized = String(status || "ready").toLowerCase();
  return <span className={`status-pill ${normalized}`}>{normalized}</span>;
}

function Sidebar({ history, activeId, keyword, onKeywordChange, onSelect, onNewRun, onStop, onDelete, onOpenFiles }) {
  const filtered = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return history.filter((item) => {
      const haystack = [item.id, item.title, item.query, item.status, item.updated_at].join(" ").toLowerCase();
      return !needle || haystack.includes(needle);
    });
  }, [history, keyword]);

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">R</div>
        <div>
          <div className="brand-title">RWKV-ECRA</div>
          <div className="brand-subtitle">RWKV 长文本分析</div>
        </div>
      </div>

      <div className="sidebar-section">
        <button className="primary-action mb-2" type="button" onClick={onNewRun}>
          <SquarePen size={16} />
          新建分析任务
        </button>
        <button className="ghost-button w-full justify-center" type="button" onClick={onOpenFiles}>
          <FolderOpen size={16} />
          本地工作区文件
        </button>
      </div>

      <div className="sidebar-section">
        <div className="section-label">历史记录</div>
        <label className="search-box">
          <Search size={15} />
          <input value={keyword} onChange={(event) => onKeywordChange(event.target.value)} type="search" placeholder="搜索任务、报告、状态" />
        </label>
        <div className="history-list" aria-live="polite">
          {filtered.length ? (
            filtered.map((item) => {
              const displayTitle = item.query ? (item.query.length > 20 ? item.query.substring(0, 20) + "..." : item.query) : item.id;
              
              return (
              <div key={item.id} className={`history-item ${item.id === activeId ? "active" : ""}`}>
                <div className="history-content" onClick={() => onSelect(item.id)}>
                  <div className="history-main">
                    <div className="history-title" title={item.query || item.title}>{displayTitle}</div>
                    <StatusPill status={item.status} />
                  </div>
                  <div className="history-meta">{item.updated_at || "-"}</div>
                </div>
                <div className="history-actions">
                  {item.status === "running" && (
                    <button className="action-btn stop-btn" type="button" onClick={(e) => { e.stopPropagation(); onStop(item.id); }} title="停止任务">
                      <StopCircle size={14} /> 停止
                    </button>
                  )}
                  <button className="action-btn delete-btn" type="button" onClick={(e) => { e.stopPropagation(); onDelete(item.id); }} title="彻底删除记录及其产出">
                    <Trash2 size={14} /> 删除
                  </button>
                </div>
              </div>
            )})
          ) : (
            <div className="history-meta">没有匹配的历史记录</div>
          )}
        </div>
      </div>
    </aside>
  );
}

function FileManager({ onClose }) {
  const [files, setFiles] = useState([]);
  const [viewingFile, setViewingFile] = useState(null);

  async function load() {
    try { setFiles(await getFiles()); } catch (e) { console.error(e); }
  }

  useEffect(() => { load(); }, []);

  async function handleUploadFiles(e) {
    if (!e.target.files.length) return;
    try {
      await uploadFile(e.target.files);
    } catch (err) {
      alert("上传失败：" + err.message);
    }
    load();
    e.target.value = null; 
  }

  async function handleView(f) {
    try {
      const data = await getFileContent(f);
      setViewingFile({ name: f, ...data });
    } catch (e) {
      alert("无法加载文件内容");
    }
  }

  async function handleDelete(node) {
    const isFolder = node.type === 'folder';
    const msg = isFolder 
      ? `确认删除整个文件夹 "${node.name}" 及其包含的所有文件？` 
      : `确认彻底删除本地工作区文件 "${node.name}" ?`;

    if (window.confirm(msg)) {
      try {
        const pathsToDelete = getAllFilePaths(node);
        await Promise.all(pathsToDelete.map(p => deleteFile(p)));
        load();
      } catch (err) {
        alert("删除失败：" + err.message);
      }
    }
  }

  const fileTree = useMemo(() => buildFileTree(files), [files]);
  const rootChildren = Object.values(fileTree.children).sort((a, b) => {
    if (a.type === b.type) return a.name.localeCompare(b.name);
    return a.type === 'folder' ? -1 : 1;
  });

  return (
    <div className="file-manager">
      <div className="vsc-tree">
        {rootChildren.length > 0 ? rootChildren.map(child => (
          <FileTreeNode key={child.name} node={child} level={0} onView={handleView} onDelete={handleDelete} />
        )) : <div className="history-meta" style={{padding: '12px'}}>暂无本地工作区文件，请点击下方上传。</div>}
      </div>
      
      <div className="file-actions mt-4">
        <label className="ghost-button upload-btn">
          上传文件 (MD/TXT/图片)
          <input type="file" multiple accept=".md,.txt,.png,.jpg,.jpeg,.webp,.svg,.gif" style={{display: 'none'}} onChange={handleUploadFiles}/>
        </label>
        <label className="ghost-button upload-btn">
          上传整个文件夹
          <input type="file" webkitdirectory="true" style={{display: 'none'}} onChange={handleUploadFiles}/>
        </label>
      </div>

      {viewingFile && (
        <div className="modal-overlay nested-overlay" onClick={() => setViewingFile(null)}>
           <div className="modal-content" onClick={e => e.stopPropagation()}>
             <div className="modal-header">
               <h3 title={viewingFile.name} style={{whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis', maxWidth:'80%'}}>
                 {viewingFile.name}
               </h3>
               <button className="ghost-button" onClick={() => setViewingFile(null)}>返回</button>
             </div>
             {viewingFile.type === 'image' ? (
               <div style={{flex: 1, overflow: 'auto', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                 <img src={viewingFile.url} alt={viewingFile.name} style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain'}}/>
               </div>
             ) : (
               <textarea readOnly value={viewingFile.content} />
             )}
           </div>
        </div>
      )}
    </div>
  );
}

function Composer({ onSubmit, isAnyRunning, isSubmitting }) {
  const [query, setQuery] = useState("");
  const textareaRef = useRef(null);

  function submit() {
    if (!query.trim() || isSubmitting) return;
    onSubmit(query.trim());
    setQuery("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  return (
    <div className="composer-wrapper">
      <div className="modern-composer">
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={1}
          placeholder="输入研究主题，开启深度探索... (例如：提取本地工作区中所有研报的核心逻辑)"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          onInput={(e) => {
            e.target.style.height = "auto";
            e.target.style.height = Math.min(e.target.scrollHeight, 150) + "px";
          }}
        />
        <button
          className={`send-btn ${isAnyRunning ? 'enqueue-btn' : ''}`}
          onClick={submit}
          disabled={isSubmitting || !query.trim()}
          title={isAnyRunning ? "当前系统执行中，点击加入排队" : "发送并执行"}
        >
          {isSubmitting ? <Loader2 className="spin" size={20} /> : (isAnyRunning ? <ListPlus size={20} /> : <Play size={20} fill="currentColor" />)}
        </button>
      </div>
      <div className="composer-footer">RWKV Agent 将自动拆解任务、检索文件与网络、并生成深度研究报告。</div>
    </div>
  );
}

function ThinkingProcess({ progress, onStop }) {
  const [expanded, setExpanded] = useState(true);
  const preRef = useRef(null);

  useEffect(() => {
    if (preRef.current && expanded) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
  }, [progress, expanded]);

  return (
    <div className="thinking-card">
      <div className="thinking-header" onClick={() => setExpanded(!expanded)}>
        <div className="thinking-title-left">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <span className="pulse-text">深度思考与研究执行中...</span>
        </div>
        <button className="ghost-button stop-btn compact-stop" onClick={(e) => { e.stopPropagation(); onStop(); }} title="中止任务">
          <StopCircle size={14} /> 中止
        </button>
      </div>
      {expanded && (
        <div className="thinking-body" ref={preRef}>
          <pre>{progress || "系统正在初始化执行环境，即将启动探索..."}</pre>
        </div>
      )}
    </div>
  );
}

function Metrics({ report }) {
  return (
    <section className="status-strip">
      <div>
        <span className="metric-label">状态</span>
        <strong>{report?.status || "-"}</strong>
      </div>
      <div>
        <span className="metric-label">章节规模</span>
        <strong>{report?.nodes?.length || (report?.markdown ? 1 : 0)} 节</strong>
      </div>
      <div>
        <span className="metric-label">数据来源</span>
        <strong>{report?.sources?.length || 0} 项</strong>
      </div>
      <div>
        <span className="metric-label">最近更新</span>
        <strong>{report?.updated_at || "-"}</strong>
      </div>
    </section>
  );
}

function Outline({ report, markdown }) {
  const items = report?.nodes?.length
    ? report.nodes.map((node, index) => ({ id: `node-${index}`, title: node.title || `章节 ${index + 1}` }))
    : extractMarkdownOutline(markdown);

  return (
    <nav className="outline-panel">
      <div className="section-label">大纲导航</div>
      <div className="outline-list">
        {items.length ? items.map((item) => <a key={item.id} className="outline-link" href={`#${item.id}`}>{item.title}</a>) : <div className="history-meta">无结构化大纲</div>}
      </div>
    </nav>
  );
}

function Sources({ sources = [] }) {
  return (
    <aside className="sources-panel">
      <div className="section-label">溯源索引 (Sources)</div>
      <div className="sources-list">
        {sources.length ? (
          sources.map((source) => (
            <div key={`${source.index}-${source.title}`} id={`source-${source.index}`} className="source-item">
              <div className="source-index">[{source.index}]</div>
              <div className="source-title">
                {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title || source.url}</a> : source.title || "内部文档"}
              </div>
              <div className="source-type">{source.type === "web" ? "🌎 互联网检索" : "📂 本地工作区文件"}</div>
            </div>
          ))
        ) : (
          <div className="history-meta">纯内省推演，无外部溯源</div>
        )}
      </div>
    </aside>
  );
}

function ReportView({ report }) {
  if (!report) return null;

  if (report.nodes?.length) {
    return (
      <article className="report-view">
        {report.nodes.map((node, index) => (
          <section key={node.id || index} id={`node-${index}`} className="report-node">
            <h2 className="report-node-title">{node.title || `章节 ${index + 1}`}</h2>
            <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(node.content || "") }} />
          </section>
        ))}
      </article>
    );
  }

  return (
    <article className="report-view">
      <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(report.markdown || "") }} />
    </article>
  );
}

export function App() {
  const [history, setHistory] = useState([]);
  const [keyword, setKeyword] = useState("");
  const [activeId, setActiveId] = useState(null);
  const [report, setReport] = useState(null);
  const [fileManagerOpen, setFileManagerOpen] = useState(false);
  const [error, setError] = useState("");
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const [taskQueue, setTaskQueue] = useState(() => {
    try {
      const saved = localStorage.getItem("rwkv_task_queue");
      const parsed = saved ? JSON.parse(saved) : [];
      return parsed.map(q => typeof q === "string" ? { query: q, queuedAt: formatCurrentTime() } : q);
    } catch {
      return [];
    }
  });
  const [isQueueOpen, setIsQueueOpen] = useState(false);

  const prevStatusRef = useRef(null);
  const markdown = useMemo(() => reportToMarkdown(report), [report]);

  const isAnyRunning = history.some(t => t.status === "running");
  const runningTask = history.find(t => t.status === "running");
  const activeTaskItem = history.find(t => t.id === activeId);

  useEffect(() => {
    localStorage.setItem("rwkv_task_queue", JSON.stringify(taskQueue));
    if (taskQueue.length === 0) setIsQueueOpen(false);
  }, [taskQueue]);

  const pollHistory = useCallback(async () => {
    try {
      const items = await getHistory();
      setHistory(items);
    } catch (e) {}
  }, []);

  async function refreshHistory(selectFirst = false) {
    try {
      setError("");
      const items = await getHistory();
      setHistory(items);
      if ((selectFirst || !activeId) && items.length) {
        await selectReport(items[0].id);
      }
    } catch (reason) {
      setError(`历史记录获取异常：${reason.message}`);
    }
  }

  async function selectReport(id) {
    setActiveId(id);
    try {
      setError("");
      setReport(await getReport(id));
    } catch (reason) {
      const task = history.find(t => t.id === id);
      if (task && task.status === "running") {
        setReport(null);
      } else {
        setError(`报告加载失败：${reason.message}`);
        setReport(null);
      }
    }
  }

  async function handleNewTaskSubmitted(taskId) {
    await refreshHistory(false);
    if (taskId) {
      await selectReport(taskId);
    }
  }

  function handleNewRun() {
    setActiveId(null);
    setReport(null);
  }

  async function copyMarkdown() {
    if (!markdown) return;
    await navigator.clipboard.writeText(markdown);
  }

  async function handleStopTask(id) {
    try {
      await stopTask(id);
      refreshHistory(false);
    } catch (reason) {
      setError(`中止失败：${reason.message}`);
    }
  }

  async function handleDeleteTask(id) {
    if (!window.confirm("确定彻底删除该研究记录及其所有落盘文件吗？此操作无法撤销。")) return;
    try {
      await deleteTask(id);
      if (activeId === id) {
        handleNewRun();
      }
      refreshHistory(false);
    } catch (reason) {
      setError(`删除失败：${reason.message}`);
    }
  }

  async function handleQuerySubmit(newQuery) {
    const taskObj = { query: newQuery, queuedAt: formatCurrentTime() };
    if (isAnyRunning || isSubmitting) {
      setTaskQueue(prev => [...prev, taskObj]);
    } else {
      await executeTask(taskObj);
    }
  }

  async function executeTask(taskObj) {
    setIsSubmitting(true);
    try {
      const response = await startAnalyze({ query: taskObj.query, queued_at: taskObj.queuedAt });
      await handleNewTaskSubmitted(response.task_id);
    } catch (err) {
      alert(`提交失败：${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  function removeQueuedTask(index) {
    setTaskQueue(prev => prev.filter((_, i) => i !== index));
  }

  useEffect(() => {
    if (!isAnyRunning && taskQueue.length > 0 && !isSubmitting) {
      const nextTask = taskQueue[0];
      setTaskQueue(prev => prev.slice(1));
      executeTask(nextTask);
    }
  }, [isAnyRunning, taskQueue, isSubmitting]);

  useEffect(() => {
    refreshHistory(true);
    const timer = setInterval(pollHistory, 3000);
    return () => clearInterval(timer);
  }, [pollHistory]);

  useEffect(() => {
    if (activeTaskItem) {
      const prev = prevStatusRef.current;
      const curr = activeTaskItem.status;
      if (prev === "running" && (curr === "completed" || curr === "ready")) {
        selectReport(activeTaskItem.id);
      }
      prevStatusRef.current = curr;
    } else {
      prevStatusRef.current = null;
    }
  }, [activeTaskItem, history]); 

  return (
    <div className="app-shell">
      <Sidebar 
        history={history} 
        activeId={activeId} 
        keyword={keyword} 
        onKeywordChange={setKeyword} 
        onSelect={selectReport} 
        onNewRun={handleNewRun} 
        onStop={handleStopTask}
        onDelete={handleDeleteTask}
        onOpenFiles={() => setFileManagerOpen(true)}
      />

      <main className="workspace">
        {taskQueue.length > 0 && (
          <div className="queue-widget">
            {!isQueueOpen ? (
              <button className="queue-toggle-btn" onClick={() => setIsQueueOpen(true)}>
                <ListPlus size={18} />
                <span>任务排队中 ({taskQueue.length})</span>
              </button>
            ) : (
              <div className="queue-panel">
                <div className="queue-header">
                  <span style={{display: 'flex', alignItems: 'center', gap: '6px', color: '#0f172a'}}>
                    <ListPlus size={16}/> 待处理队列 ({taskQueue.length})
                  </span>
                  <div style={{display: 'flex', gap: '6px'}}>
                    <button className="ghost-button compact-btn" onClick={() => setTaskQueue([])}>清空</button>
                    <button className="ghost-button compact-btn icon-only" onClick={() => setIsQueueOpen(false)}>
                      <X size={14}/>
                    </button>
                  </div>
                </div>
                <div className="queue-list">
                  {taskQueue.map((q, i) => (
                    <div key={i} className="queue-item">
                      <span className="queue-number">{i + 1}</span>
                      <span className="queue-text" title={q.query}>{q.query}</span>
                      <button onClick={() => removeQueuedTask(i)} title="移出排队"><X size={14}/></button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="workspace-scroll-area">
          {activeId && (
            <header className="topbar">
              <div>
                <div className="kicker">{activeTaskItem?.status === "running" ? "研究执行中..." : (report?.kind === "markdown" ? "综合研报 (Markdown)" : "结构化解耦研报")}</div>
                <h1 title={activeTaskItem?.query || activeTaskItem?.title}>
                  {activeTaskItem?.query || activeTaskItem?.title || "深度研究任务"}
                </h1>
              </div>
              <div className="topbar-actions">
                <button className="topbar-btn btn-refresh" type="button" onClick={() => refreshHistory(false)}>
                  <RefreshCw size={16} /> 刷新状态
                </button>
                {report && (
                  <button className="topbar-btn btn-copy" type="button" onClick={copyMarkdown}>
                    <Copy size={16} /> 复制全文
                  </button>
                )}
              </div>
            </header>
          )}

          {error ? <div className="error-banner">{error}</div> : null}

          {!activeId && !isAnyRunning && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 0' }}>
              <div className="empty-home" style={{ height: 'auto', margin: '40px 0 20px' }}>
                <div className="brand-mark large-mark mb-4" style={{ margin: '0 auto 16px' }}>R</div>
                <h1>开启长文本分析</h1>
                <p>系统将调度最新的RWKV和外部云端大模型完成任务</p>
              </div>
              
              {/* 这里插入架构图组件 */}
              <ArchitectureGraph />
            </div>
          )}

          {activeId && activeTaskItem?.status === "running" && (
            <ThinkingProcess progress={activeTaskItem.progress} onStop={() => handleStopTask(activeTaskItem.id)} />
          )}
          {!activeId && isAnyRunning && runningTask && (
            <ThinkingProcess progress={runningTask.progress} onStop={() => handleStopTask(runningTask.id)} />
          )}

          {report && (
            <div className="report-container fade-in">
              <Metrics report={report} />
              <div className="content-layout">
                <Outline report={report} markdown={markdown} />
                <ReportView report={report} />
                <Sources sources={report?.sources || []} />
              </div>
            </div>
          )}
          
          <div style={{ height: "140px" }} />
        </div>
        
        <div className="workspace-bottom-dock">
          <Composer onSubmit={handleQuerySubmit} isAnyRunning={isAnyRunning} isSubmitting={isSubmitting} />
        </div>
        
        {activeTaskItem && <TaskTimingWidget task={activeTaskItem} />}
      </main>

      {fileManagerOpen && (
        <div className="modal-overlay" onClick={() => setFileManagerOpen(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>📂 本地工作区 (data/input)</h3>
              <button className="ghost-button" onClick={() => setFileManagerOpen(false)}>关闭</button>
            </div>
            <FileManager onClose={() => setFileManagerOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}