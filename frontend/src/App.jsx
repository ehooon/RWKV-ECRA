import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  AlertCircle,
  ArrowUp,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  File,
  FileText,
  Files,
  Folder,
  FolderOpen,
  Gauge,
  Loader2,
  ListPlus,
  Play,
  RefreshCw,
  SearchCheck,
  StopCircle,
  Trash2,
  Upload,
  Workflow,
  X,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { getHistory, getReport, startAnalyze, stopTask, deleteTask, getFiles, deleteFile, getFileContent, uploadFile, getRuntimeConfig, getTokenUsage } from "./api.js";
import { extractMarkdownOutline, renderMarkdown, reportToMarkdown } from "./markdown.js";
import { AppSidebar } from "@/components/app-sidebar";
import { TaskStatusBadge } from "@/components/task-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

function formatCurrentTime() {
  const date = new Date();
  const Y = date.getFullYear();
  const M = String(date.getMonth() + 1).padStart(2, "0");
  const D = String(date.getDate()).padStart(2, "0");
  const h = String(date.getHours()).padStart(2, "0");
  const m = String(date.getMinutes()).padStart(2, "0");
  const s = String(date.getSeconds()).padStart(2, "0");

  return `${Y}-${M}-${D} ${h}:${m}:${s}`;
}

function parseTaskTime(taskId) {
  if (!taskId) return null;
  const match = taskId.match(/TASK_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (!match) return null;
  return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`;
}

// ========================
// Utils: Scroll Shadow System
// ========================
function getScrollShadowState(element) {
  if (!element) return { canScrollUp: false, canScrollDown: false };
  const scrollTop = element.scrollTop;
  const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
  return {
    canScrollUp: scrollTop > 1,
    canScrollDown: scrollTop < maxScrollTop - 1,
  };
}

function useScrollShadows(resolveElement, dependencies = []) {
  const [shadows, setShadows] = useState({ canScrollUp: false, canScrollDown: false });

  useEffect(() => {
    const element = resolveElement();
    if (!element) {
      setShadows({ canScrollUp: false, canScrollDown: false });
      return undefined;
    }

    let frame = 0;
    const update = () => {
      frame = 0;
      setShadows(getScrollShadowState(element));
    };
    const requestUpdate = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(update);
    };

    update();
    element.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(requestUpdate) : null;
    resizeObserver?.observe(element);
    if (element.firstElementChild) {
      resizeObserver?.observe(element.firstElementChild);
    }

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      element.removeEventListener("scroll", requestUpdate);
      window.removeEventListener("resize", requestUpdate);
      resizeObserver?.disconnect();
    };
  }, dependencies);

  return shadows;
}

function useReportScrollAffordance(scrollRef, surfaceRef, dependencies = []) {
  const [affordance, setAffordance] = useState({
    canScrollUp: false,
    canScrollDown: false,
    frame: null,
  });

  useEffect(() => {
    const scrollElement = scrollRef.current;
    const surfaceElement = surfaceRef.current;

    if (!scrollElement || !surfaceElement) {
      setAffordance({ canScrollUp: false, canScrollDown: false, frame: null });
      return undefined;
    }

    let animationFrame = 0;
    const update = () => {
      animationFrame = 0;
      const scrollState = getScrollShadowState(scrollElement);
      const scrollRect = scrollElement.getBoundingClientRect();
      const surfaceRect = surfaceElement.getBoundingClientRect();
      const left = Math.max(scrollRect.left, surfaceRect.left);
      const right = Math.min(scrollRect.right, surfaceRect.right);
      const isSurfaceVisible = surfaceRect.bottom > scrollRect.top && surfaceRect.top < scrollRect.bottom;

      setAffordance({
        canScrollUp: scrollState.canScrollUp && isSurfaceVisible,
        canScrollDown: scrollState.canScrollDown && isSurfaceVisible,
        frame: right > left
          ? {
              left,
              width: right - left,
              top: scrollRect.top,
              bottom: window.innerHeight - scrollRect.bottom,
            }
          : null,
      });
    };

    const requestUpdate = () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(update);
    };

    update();
    scrollElement.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate);

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(requestUpdate) : null;
    resizeObserver?.observe(scrollElement);
    resizeObserver?.observe(surfaceElement);

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      scrollElement.removeEventListener("scroll", requestUpdate);
      window.removeEventListener("resize", requestUpdate);
      resizeObserver?.disconnect();
    };
  }, dependencies);

  return affordance;
}

function ScrollShadows({ canScrollUp, canScrollDown, variant = "panel", frame = null }) {
  if (variant === "viewport") {
    if (!frame) return null;
    return (
      <>
        <div className={cn("report-viewport-shadow report-scroll-shadow-top", canScrollUp && "is-visible")} style={{ left: `${frame.left}px`, top: `${frame.top}px`, width: `${frame.width}px` }} aria-hidden="true" />
        <div className={cn("report-viewport-shadow report-scroll-shadow-bottom", canScrollDown && "is-visible")} style={{ left: `${frame.left}px`, bottom: `${frame.bottom}px`, width: `${frame.width}px` }} aria-hidden="true" />
      </>
    );
  }
  return (
    <>
      <div className={cn("report-panel-shadow report-scroll-shadow-top", canScrollUp && "is-visible")} aria-hidden="true" />
      <div className={cn("report-panel-shadow report-scroll-shadow-bottom", canScrollDown && "is-visible")} aria-hidden="true" />
    </>
  );
}

// ========================
// Components: File Tree
// ========================
function buildFileTree(paths) {
  const root = { name: "root", type: "folder", children: {}, path: "" };
  paths.forEach((path) => {
    const parts = path.split(/[/\\]/).filter(Boolean);
    let current = root;
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      if (!current.children[part]) {
        current.children[part] = { name: part, type: isFile ? "file" : "folder", path: isFile ? path : parts.slice(0, index + 1).join("/"), children: {} };
      }
      current = current.children[part];
    });
  });
  return root;
}

function getAllFilePaths(node) {
  if (node.type === "file") return [node.path];
  return Object.values(node.children || {}).flatMap((child) => getAllFilePaths(child));
}

function getTaskLabel(task) {
  return task?.query?.trim() || task?.title || task?.id || "深度研究任务";
}

function FileTreeNode({ node, level = 0, activePath, onView, onDelete }) {
  const [isOpen, setIsOpen] = useState(level === 0);
  const paddingLeft = 12 + level * 16;

  if (node.type === "file") {
    return (
      <div className={cn("group flex items-center justify-between rounded-lg pr-2 transition-colors hover:bg-muted/70", activePath === node.path && "bg-muted")} style={{ paddingLeft }}>
        <button type="button" onClick={() => onView(node.path)} className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left text-sm">
          <File className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
        </button>
        <Button variant="ghost" size="icon-xs" title="删除文件" className="opacity-0 group-hover:opacity-100" onClick={(event) => { event.stopPropagation(); onDelete(node); }}>
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    );
  }

  const childrenNodes = Object.values(node.children).sort((a, b) => {
    if (a.type === b.type) return a.name.localeCompare(b.name);
    return a.type === "folder" ? -1 : 1;
  });

  return (
    <div>
      <div className="group flex items-center justify-between rounded-lg pr-2 transition-colors hover:bg-muted/70" style={{ paddingLeft }}>
        <button type="button" onClick={() => setIsOpen((value) => !value)} className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left text-sm font-medium">
          {isOpen ? <ChevronDown className="size-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="size-4 shrink-0 text-muted-foreground" />}
          <Folder className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
        </button>
        <Button variant="ghost" size="icon-xs" title="删除文件夹" className="opacity-0 group-hover:opacity-100" onClick={(event) => { event.stopPropagation(); onDelete(node); }}>
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      {isOpen && (
        <div className="space-y-0.5">
          {childrenNodes.map((child) => (
            <FileTreeNode key={`${node.path}-${child.name}`} node={child} level={level + 1} activePath={activePath} onView={onView} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  );
}

function FileManager() {
  const [files, setFiles] = useState([]);
  const [activePath, setActivePath] = useState("");
  const [preview, setPreview] = useState(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const revokePreviewUrl = useCallback((value) => {
    if (value?.type === "image" && value.url) URL.revokeObjectURL(value.url);
  }, []);

  const loadFiles = useCallback(async () => {
    try { setFiles(await getFiles()); } catch (error) { toast.error(`加载文件失败：${error.message}`); }
  }, []);

  useEffect(() => { loadFiles(); }, [loadFiles]);
  useEffect(() => { return () => revokePreviewUrl(preview); }, [preview, revokePreviewUrl]);

  async function handleUploadFiles(event) {
    if (!event.target.files?.length) return;
    try {
      await uploadFile(event.target.files);
      toast.success("文件已上传到工作区");
      await loadFiles();
    } catch (error) {
      toast.error(`上传失败：${error.message}`);
    } finally {
      event.target.value = "";
    }
  }

  async function handleView(path) {
    setActivePath(path);
    setIsPreviewLoading(true);
    try {
      const nextPreview = await getFileContent(path);
      setPreview((current) => { revokePreviewUrl(current); return nextPreview; });
    } catch (error) {
      toast.error(`无法加载文件内容：${error.message}`);
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function handleDelete(node) {
    const isFolder = node.type === "folder";
    const message = isFolder ? `确认删除整个文件夹 "${node.name}" 及其所有内容吗？` : `确认删除文件 "${node.name}" 吗？`;
    if (!window.confirm(message)) return;

    try {
      const pathsToDelete = getAllFilePaths(node);
      await Promise.all(pathsToDelete.map((path) => deleteFile(path)));
      if (pathsToDelete.includes(activePath)) {
        setActivePath("");
        setPreview((current) => { revokePreviewUrl(current); return null; });
      }
      toast.success(isFolder ? "文件夹已删除" : "文件已删除");
      await loadFiles();
    } catch (error) {
      toast.error(`删除失败：${error.message}`);
    }
  }

  const fileTree = useMemo(() => buildFileTree(files), [files]);
  const rootChildren = useMemo(() => Object.values(fileTree.children).sort((a, b) => {
    if (a.type === b.type) return a.name.localeCompare(b.name);
    return a.type === "folder" ? -1 : 1;
  }), [fileTree]);

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="border-border">
        <CardHeader><CardTitle className="text-base">文件树</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <label className="block">
              <input type="file" multiple accept=".md,.txt,.png,.jpg,.jpeg,.webp,.svg,.gif" className="hidden" onChange={handleUploadFiles} />
              <Button variant="outline" className="w-full justify-start rounded-lg" render={<span />}>
                <Upload className="size-4" /> 上传文件
              </Button>
            </label>
            <label className="block">
              <input type="file" multiple webkitdirectory="" className="hidden" onChange={handleUploadFiles} />
              <Button variant="outline" className="w-full justify-start rounded-lg" render={<span />}>
                <FolderOpen className="size-4" /> 上传整个文件夹
              </Button>
            </label>
          </div>
          <ScrollArea className="h-[420px] rounded-xl border border-border bg-muted p-2">
            {rootChildren.length ? (
              <div className="space-y-1">
                {rootChildren.map((child) => <FileTreeNode key={child.name} node={child} activePath={activePath} onView={handleView} onDelete={handleDelete} />)}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm leading-6 text-muted-foreground">暂无本地工作区文件。</div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
      <Card className="border-border">
        <CardHeader><CardTitle className="text-base">{activePath || "文件预览"}</CardTitle></CardHeader>
        <CardContent>
          {isPreviewLoading ? (
            <div className="flex h-[420px] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
              <Loader2 className="mr-2 size-4 animate-spin" />正在读取文件内容
            </div>
          ) : preview?.type === "image" ? (
            <div className="flex h-[420px] items-center justify-center overflow-hidden rounded-xl border border-border bg-muted p-4">
              <img src={preview.url} alt={activePath} className="max-h-full max-w-full rounded-lg object-contain" />
            </div>
          ) : preview?.type === "text" ? (
            <ScrollArea className="h-[420px] rounded-xl border border-border bg-muted">
              <pre className="p-4 text-xs leading-6 whitespace-pre-wrap text-foreground">{preview.content}</pre>
            </ScrollArea>
          ) : (
            <div className="flex h-[420px] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">选择文件后显示预览。</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ========================
// Components: Composers
// ========================
function Composer({ onSubmit, isAnyRunning, isSubmitting, asyncEnabled, variant = "compact", onOpenFiles }) {
  const [query, setQuery] = useState("");
  const textareaRef = useRef(null);
  const shouldEnqueue = !asyncEnabled && isAnyRunning;
  const isCreateMode = variant === "create";

  function resizeTextarea(target) {
    target.style.height = "auto";
    target.style.height = `${Math.min(target.scrollHeight, 220)}px`;
  }

  function handleSubmit() {
    if (!query.trim() || isSubmitting) return;
    onSubmit(query.trim());
    setQuery("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  return (
    <div className={cn("research-composer", isCreateMode && "research-composer-create")}>
      {isCreateMode && <label htmlFor="new-research-query" className="mb-2 block text-sm font-medium text-foreground">研究主题</label>}
      <div className={cn("flex gap-3", isCreateMode ? "flex-col" : "items-end")}>
        <div className="min-w-0 flex-1">
          <Textarea
            id={isCreateMode ? "new-research-query" : undefined}
            ref={textareaRef}
            value={query}
            rows={isCreateMode ? 5 : 1}
            aria-label="输入研究任务"
            placeholder={isCreateMode ? "描述你希望研究的问题、范围与输出要求" : "继续追问，或输入新的研究主题…"}
            className={cn("resize-none bg-transparent text-[15px] leading-6 shadow-none placeholder:text-muted-foreground", isCreateMode ? "min-h-36 max-h-[240px] rounded-md border-border px-3 py-3 focus-visible:ring-2" : "min-h-11 max-h-[160px] border-0 px-0 py-2.5 focus-visible:ring-0")}
            onChange={(event) => setQuery(event.target.value)}
            onInput={(event) => resizeTextarea(event.target)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); handleSubmit(); }
            }}
          />
          {!isCreateMode && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>Enter 发送</span><span aria-hidden="true">·</span><span>Shift + Enter 换行</span><span aria-hidden="true">·</span>
              <span>{asyncEnabled ? "并行模式" : isAnyRunning ? "将加入队列" : "顺序模式"}</span>
            </div>
          )}
        </div>
        {isCreateMode ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <button type="button" onClick={onOpenFiles} className="inline-flex min-h-8 items-center gap-2 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
                <Files className="size-3.5" /> 选择工作区资料
              </button>
              <span className="text-[11px] text-muted-foreground">未选择时使用工作区可用文件</span>
            </div>
            <Button size="sm" className="h-9 shrink-0 rounded-md px-4" disabled={isSubmitting || !query.trim()} onClick={handleSubmit}>
              {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : shouldEnqueue ? <ListPlus className="size-4" /> : <ArrowUp className="size-4" />}
              {shouldEnqueue ? "加入队列" : "开始分析"}
            </Button>
          </div>
        ) : (
          <Button size="icon" className="size-10 shrink-0 rounded-md" disabled={isSubmitting || !query.trim()} onClick={handleSubmit} aria-label={shouldEnqueue ? "加入排队" : "开始分析"} title={shouldEnqueue ? "加入排队" : "开始分析"}>
            {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : shouldEnqueue ? <ListPlus className="size-4" /> : <ArrowUp className="size-4" />}
          </Button>
        )}
      </div>
    </div>
  );
}

function QueuePanel({ taskQueue, isQueueOpen, onToggle, onClear, onRemove }) {
  return (
    <Card className="border-border bg-card">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div><CardTitle className="text-base">待处理队列</CardTitle></div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="rounded-md">{taskQueue.length}</Badge>
          <Button variant="outline" size="sm" onClick={onToggle}>{isQueueOpen ? "收起" : "展开"}</Button>
          <Button variant="ghost" size="sm" onClick={onClear}>清空</Button>
        </div>
      </CardHeader>
      {isQueueOpen && (
        <CardContent>
          <div className="space-y-2">
            {taskQueue.map((task, index) => (
              <div key={`${task.query}-${task.queuedAt}-${index}`} className="flex items-center gap-3 rounded-xl border border-border bg-muted/60 px-3 py-3">
                <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-foreground text-[11px] font-medium text-background">{index + 1}</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{task.query}</div>
                  <div className="text-xs text-muted-foreground">{task.queuedAt}</div>
                </div>
                <Button variant="ghost" size="icon-sm" title="移出队列" onClick={() => onRemove(index)}><X className="size-4" /></Button>
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ========================
// Components: Progress Bar
// ========================

// ✨ 新增函数：将扁平的 step_x 日志提取转化为主子层级树
function parseStepsHierarchy(rawSteps) {
  if (!rawSteps || !rawSteps.length) return [];

  const mainSteps = [];
  let currentMainStep = null;

  for (let i = 0; i < rawSteps.length; i++) {
    let rawLine = rawSteps[i];
    let timeMatch = rawLine.match(/^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)/);
    let time = "";
    let content = rawLine;

    if (timeMatch) {
      time = timeMatch[1];
      content = timeMatch[2];
    }

    const isError = /异常|错误|failed|error|cannot access|❌/i.test(content);
    const isDone = /完成|就绪|成功|✅/i.test(content);
    
    // 识别出哪些是主干动作。可以通过大模型特有输出，或者工具链标志等，在这里以特征字符开头作为界定
    const isMajor = /^\[思考步数|^🚀|^当前阶段|^🔧|^\[/i.test(content);

    const node = {
       time,
       content: content.replace(/^[🚀❌✅🔧]\s*/, ""),
       isError,
       isDone,
       subSteps: []
    };

    if (isMajor || mainSteps.length === 0) {
       currentMainStep = node;
       mainSteps.push(currentMainStep);
    } else {
       if (currentMainStep) {
          currentMainStep.subSteps.push(node);
       }
    }
  }

  // 默认标记最后一个主干动作处于活跃态
  if (mainSteps.length > 0) {
     mainSteps[mainSteps.length - 1].isActive = true;
  }

  return mainSteps;
}

// ✨ 新增组件：可展开层级的进度仪表盘
function TaskProgressAccordion({ task, onStop }) {
  const [isExpanded, setIsExpanded] = useState(task?.status === 'running');
  const stepsEndRef = useRef(null);

  useEffect(() => {
    if (isExpanded && task?.status === 'running' && stepsEndRef.current) {
      stepsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [task?.steps?.length, isExpanded, task?.status]);

  if (!task || (!task.steps?.length && !task.progress)) return null;

  // 兼容旧版仅存在单字符串的 progress
  const rawSteps = task.steps?.length 
    ? task.steps 
    : String(task.progress || "").split("\n").filter(Boolean);
    
  const hierarchy = parseStepsHierarchy(rawSteps);
  const errorCount = hierarchy.reduce((acc, s) => acc + (s.isError ? 1 : 0) + s.subSteps.reduce((a, sub) => a + (sub.isError ? 1 : 0), 0), 0);
  const isRunning = task.status === 'running';

  return (
    <Card className="border-border bg-card shadow-sm mb-6">
      <div className="flex items-center justify-between px-4 py-3 bg-muted/40 transition-colors">
         <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex flex-1 items-center gap-3 outline-none"
         >
            {isRunning ? <Loader2 className="size-[18px] animate-spin text-primary" /> : <CheckCircle2 className="size-[18px] text-emerald-500" />}
            <span className="text-sm font-semibold tracking-tight">执行过程监控 ({hierarchy.length} 个阶段)</span>
            {errorCount > 0 && <span className="text-[11px] font-medium text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md border border-rose-200">{errorCount} 项异常</span>}
            <div className="ml-auto mr-3">
               <ChevronDown className={cn("size-4 text-muted-foreground transition-transform duration-200", !isExpanded && "-rotate-90")} />
            </div>
         </button>
         {isRunning && onStop && (
           <Button variant="ghost" size="sm" onClick={onStop} className="h-7 text-xs px-2 text-muted-foreground hover:text-rose-600">
             <StopCircle className="size-3.5 mr-1" /> 中止
           </Button>
         )}
      </div>

      {isExpanded && (
        <CardContent className="px-4 py-4 border-t border-border bg-background/50 max-h-[500px] overflow-y-auto report-scroll-area">
           <div className="space-y-5">
             {hierarchy.map((step, idx) => (
                <div key={idx} className="relative">
                  <div className="flex items-start gap-3">
                    <div className="mt-[3px] bg-background">
                       {step.isError ? <AlertCircle className="size-4 text-rose-500" /> :
                        step.isActive && isRunning ? <Loader2 className="size-4 animate-spin text-primary" /> :
                        <CheckCircle2 className="size-4 text-emerald-500/70" />}
                    </div>
                    <div className="min-w-0 flex-1">
                       <div className="flex items-baseline gap-2">
                          <span className={cn("text-sm font-medium", step.isError ? "text-rose-700" : "text-foreground")}>{step.content}</span>
                          {step.time && <span className="text-[10px] font-mono text-muted-foreground/60 shrink-0">{step.time}</span>}
                       </div>
                       {step.subSteps.length > 0 && (
                          <div className="mt-2.5 space-y-2 border-l-2 border-border/60 pl-3.5 ml-1">
                             {step.subSteps.map((sub, sidx) => (
                                <div key={sidx} className="flex items-start gap-2.5 text-[13px] leading-snug">
                                   <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/30 shrink-0 mt-[6px]" />
                                   <div className="flex-1 flex items-baseline gap-2 min-w-0">
                                       <span className={cn("text-muted-foreground break-words", sub.isError && "text-rose-600")}>{sub.content}</span>
                                       {sub.time && <span className="text-[9px] font-mono text-muted-foreground/40 shrink-0">{sub.time}</span>}
                                   </div>
                                </div>
                             ))}
                          </div>
                       )}
                    </div>
                  </div>
                </div>
             ))}
             <div ref={stepsEndRef} className="h-1" />
           </div>
        </CardContent>
      )}
    </Card>
  )
}

// 修改一：时间线卡片
function TaskTimingCard({ task }) {
  if (!task) return null;
  // 优先使用后端的 start_time，兜底使用解析 ID 的时间
  const runTime = task.start_time || parseTaskTime(task.id) || task.updated_at || "-";
  const isDone = ["completed", "failed", "ready"].includes(task.status);
  // 优先使用 end_time
  const doneTime = isDone ? (task.end_time || task.updated_at || "-") : "进行中";

  const entries = [
    ["排队", task.queued_at || "-"],
    ["运行", runTime],
    ["完成", doneTime],
  ];
  return (
    <section className="report-side-section">
      <div className="flex items-center gap-2 text-sm font-semibold"><Clock3 className="size-4" />任务时间线</div>
      <div className="mt-3 space-y-2">
        {entries.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-3 text-xs">
            <span className="text-muted-foreground">{label}</span>
            <span className="truncate font-mono text-[10px] tabular-nums text-foreground/70" title={value}>{value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// 修改二：右上角的属性条
function MetricsStrip({ report, task }) {
  const sectionCount = report?.nodes?.length || (report?.markdown ? 1 : 0);
  const sourceCount = report?.sources?.length || 0;
  // 按照优先级读取最后更新时间：完成时间 > 开始时间 > 后备 timestamp
  const updatedAt = task?.end_time || task?.start_time || task?.updated_at || report?.updated_at || "-";

  return (
    <div className="report-meta-strip">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">状态</span>
        <TaskStatusBadge status={task?.status} className="px-1.5 py-0 text-[10px]" />
      </div>
      <div><span className="text-muted-foreground">章节</span><span className="ml-1.5 font-medium tabular-nums">{sectionCount}</span></div>
      <div><span className="text-muted-foreground">来源</span><span className="ml-1.5 font-medium tabular-nums">{sourceCount}</span></div>
      <div className="sm:ml-auto">
        <span className="text-muted-foreground">更新于</span>
        <span className="ml-1.5 font-mono text-[10px] tabular-nums text-foreground/70">{updatedAt}</span>
      </div>
    </div>
  );
}

function TokenUsageCard({ data }) {
  if (!data) return null;
  const rwkv = data.rwkv_slm || { input_tokens: 0, output_tokens: 0, execution_time_sec: 0 };
  const cloud = data.cloud_llm || { input_tokens: 0, output_tokens: 0, reasoning_tokens: 0, execution_time_sec: 0 };
  const totalRwkv = (rwkv.input_tokens || 0) + (rwkv.output_tokens || 0);
  const combinedCloudOutput = (cloud.output_tokens || 0) + (cloud.reasoning_tokens || 0);
  const totalCloud = (cloud.input_tokens || 0) + combinedCloudOutput;
  const rwkvTime = (rwkv.execution_time_sec || 0).toFixed(1);
  const cloudTime = (cloud.execution_time_sec || 0).toFixed(1);

  if (totalRwkv === 0 && totalCloud === 0) return null;
  return (
    <section className="report-side-section shadow-lg border border-border/60 bg-secondary/95 backdrop-blur">
      <div className="flex items-center gap-2 text-sm font-semibold"><Gauge className="size-4 text-primary" />资源消耗统计</div>
      <div className="mt-4 space-y-3">
        <div>
          <div className="flex items-center justify-between text-[11px] mb-1">
            <span className="text-muted-foreground font-medium">RWKV (本地基座)</span>
            <span className="font-mono font-medium text-foreground/80">{totalRwkv.toLocaleString()}</span>
          </div>
          <div className="flex items-baseline justify-between gap-3 text-[10px]">
            <span className="text-muted-foreground/50">输入 / 输出</span>
            <span className="font-mono tabular-nums text-muted-foreground/70">{rwkv.input_tokens?.toLocaleString() || 0} / {rwkv.output_tokens?.toLocaleString() || 0}</span>
          </div>
          {rwkv.execution_time_sec > 0 && (
            <div className="flex items-baseline justify-between gap-3 text-[10px] mt-0.5">
              <span className="text-muted-foreground/50">执行耗时</span>
              <span className="font-mono tabular-nums text-muted-foreground/70">{rwkvTime} s</span>
            </div>
          )}
        </div>
        <div className="pt-2 border-t border-border/50">
          <div className="flex items-center justify-between text-[11px] mb-1">
            <span className="text-muted-foreground font-medium">Cloud LLM (云端推理)</span>
            <span className="font-mono font-medium text-foreground/80">{totalCloud.toLocaleString()}</span>
          </div>
          <div className="flex items-baseline justify-between gap-3 text-[10px]">
            <span className="text-muted-foreground/50">输入 / 输出</span>
            <span className="font-mono tabular-nums text-muted-foreground/70">{cloud.input_tokens?.toLocaleString() || 0} / {combinedCloudOutput.toLocaleString()}</span>
          </div>
          {cloud.execution_time_sec > 0 && (
            <div className="flex items-baseline justify-between gap-3 text-[10px] mt-0.5">
              <span className="text-muted-foreground/50">执行耗时</span>
              <span className="font-mono tabular-nums text-muted-foreground/70">{cloudTime} s</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}



function OutlinePanel({ report, markdown }) {
  const items = report?.nodes?.length ? report.nodes.map((node, index) => ({ id: `node-${index}`, title: node.title || `章节 ${index + 1}` })) : extractMarkdownOutline(markdown);
  const [activeSectionId, setActiveSectionId] = useState(items[0]?.id || "");
  const outlineRef = useRef(null);

  useEffect(() => {
    if (!items.length) { setActiveSectionId(""); return undefined; }
    setActiveSectionId(items[0].id);

    const sections = items.map((item) => document.getElementById(item.id)).filter(Boolean);
    if (!sections.length || typeof IntersectionObserver === "undefined") return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) setActiveSectionId(visible[0].target.id);
      },
      { rootMargin: "-12% 0px -72% 0px", threshold: 0 }
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [items.map((item) => item.id).join("|")]);

  useEffect(() => {
    const activeLink = outlineRef.current?.querySelector('[aria-current="location"]');
    activeLink?.scrollIntoView({ block: "nearest" });
  }, [activeSectionId]);

  return (
    <aside className="report-outline-panel">
      <div className="mb-3 text-xs font-semibold text-foreground">目录</div>
      <ScrollArea className="report-outline-scroll">
        {items.length ? (
          <nav ref={outlineRef} className="space-y-0.5 pr-1" aria-label="报告目录">
            {items.map((item, index) => (
              <a key={item.id} href={`#${item.id}`} aria-current={activeSectionId === item.id ? "location" : undefined} className={cn("group flex gap-2 rounded-md px-1.5 py-1.5 text-xs leading-5 transition-colors focus-visible:ring-2 focus-visible:ring-ring", activeSectionId === item.id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground")}>
                <span className={cn("w-4 shrink-0 font-mono text-[9px] tabular-nums", activeSectionId === item.id ? "text-primary" : "text-foreground/35")}>{String(index + 1).padStart(2, "0")}</span>
                <span>{item.title}</span>
              </a>
            ))}
          </nav>
        ) : (
          <div className="text-xs text-muted-foreground">无目录</div>
        )}
      </ScrollArea>
    </aside>
  );
}

function SourcesPanel({ sources = [] }) {
  const scrollRegionRef = useRef(null);
  const sourceShadows = useScrollShadows(useCallback(() => scrollRegionRef.current?.querySelector('[data-slot="scroll-area-viewport"]'), []), [sources.length]);

  return (
    <section className="report-side-section report-sources-section">
      <div className="flex items-center justify-between gap-3 shrink-0">
        <h2 className="text-sm font-semibold">引用来源</h2>
        <span className="text-[10px] tabular-nums text-muted-foreground">{sources.length}</span>
      </div>
      <div ref={scrollRegionRef} className="report-scroll-region mt-3 min-h-0 flex-1">
        <ScrollArea className="report-sources-scroll h-full">
          {sources.length ? (
            <div className="space-y-1 pr-1 pb-12">
              {sources.map((source) => (
                <div key={`${source.index}-${source.title}`} id={`source-${source.index}`} className="source-anchor">
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <a href={`#cite-ref-${source.index}`} className="citation-backlink" title="点击返回文章对应引用位置">[{source.index}]</a>
                    <span>{source.type === "web" ? "网页" : "本地文件"}</span>
                  </div>
                  <div className="mt-1.5 line-clamp-3 break-words text-xs leading-5 text-foreground/80">
                    {source.url ? (
                      <a href={source.url} target="_blank" rel="noreferrer" className="decoration-border underline-offset-4 hover:underline">{source.title || source.url}</a>
                    ) : (
                      <span>{source.title || "内部文档"}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">无引用来源</div>
          )}
        </ScrollArea>
        <ScrollShadows {...sourceShadows} />
      </div>
    </section>
  );
}

function ReportSurface({ report, surfaceRef, scrollAffordance }) {
  if (!report) return null;

  function isMissingNodeContent(content) {
    return /生成异常|内容丢失|生成失败|missing content/i.test(String(content || ""));
  }

  return (
    <main ref={surfaceRef} className="report-surface">
      <ScrollShadows variant="viewport" canScrollUp={scrollAffordance?.canScrollUp} canScrollDown={scrollAffordance?.canScrollDown} frame={scrollAffordance?.frame} />
      <div className="report-reader">
        {report.nodes?.length ? (
          <article className="space-y-16">
            {report.nodes.map((node, index) => (
              <section key={node.id || index} id={`node-${index}`} className="scroll-mt-20">
                <div className="report-section-heading">
                  <span className="pt-1 font-mono text-[10px] tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                  <h2 className="text-[22px] font-semibold leading-8 tracking-[-0.02em] text-foreground">
                    {(node.title || `章节 ${index + 1}`).replace(/^(?:第?[一二三四五六七八九十百]+[、，：\.]?\s*|\d+[\.、]\s*|（[一二三四五六七八九十百]+）\s*|\(\d+\)\s*)/, '')}
                  </h2>
                </div>
                {isMissingNodeContent(node.content) ? (
                  <div className="flex gap-3 rounded-md bg-amber-50 px-4 py-3 text-amber-950">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden="true" />
                    <div>
                      <div className="text-sm font-medium">本章节未能生成完整内容</div>
                      <p className="mt-1 text-xs leading-5 text-amber-900/75">其余章节不受影响。可重新运行任务以补全本节。</p>
                    </div>
                  </div>
                ) : (
                  <div className="report-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(node.content || "") }} />
                )}
              </section>
            ))}
          </article>
        ) : (
          <article className="report-markdown">
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(report.markdown || "") }} />
          </article>
        )}
      </div>
    </main>
  );
}

function LandingState({ onSubmit, isAnyRunning, isSubmitting, asyncEnabled, onAsyncEnabledChange, onOpenFiles }) {
  return (
    <div className="flex min-h-[calc(100vh-12rem)] items-start justify-center pt-[10vh]">
      <section className="w-full max-w-3xl">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-[-0.025em]">新建研究任务</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">描述研究目标，系统将结合工作区资料生成结构化报告。</p>
        </header>
        <Composer variant="create" onSubmit={onSubmit} isAnyRunning={isAnyRunning} isSubmitting={isSubmitting} asyncEnabled={asyncEnabled} onOpenFiles={onOpenFiles} />
        <div className="mt-4 flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <button type="button" onClick={onOpenFiles} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 transition-colors hover:bg-muted hover:text-foreground">
              <FolderOpen className="size-3.5" /> 文件目录
            </button>
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <Gauge className="size-3.5" />
              <span>{asyncEnabled ? "并行模式" : "顺序模式"}</span>
              <Switch checked={asyncEnabled} onCheckedChange={onAsyncEnabledChange} aria-label="切换异步并行" className="scale-[0.8]" />
            </label>
          </div>
          <span>Enter 开始 · Shift + Enter 换行</span>
        </div>
      </section>
    </div>
  );
}

export function App() {
  const [history, setHistory] = useState([]);
  const [tokenUsage, setTokenUsage] = useState({ tasks: {} });
  const [keyword, setKeyword] = useState("");
  const [activeId, setActiveId] = useState(null);
  const [report, setReport] = useState(null);
  const [fileManagerOpen, setFileManagerOpen] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isQueueOpen, setIsQueueOpen] = useState(false);
  const mainScrollRef = useRef(null);
  const reportSurfaceRef = useRef(null);
  const asyncPreferenceLoadedRef = useRef(false);
  const prevStatusRef = useRef(null);
  
  // 防抖轮询锁，防止网络抖动导致的堆积
  const isPollingRef = useRef(false);

  const [asyncEnabled, setAsyncEnabled] = useState(() => {
    try {
      const saved = localStorage.getItem("rwkv_async_parallel_enabled");
      if (saved !== null) {
        asyncPreferenceLoadedRef.current = true;
        return JSON.parse(saved);
      }
    } catch {}
    return false;
  });

  const [taskQueue, setTaskQueue] = useState(() => {
    try {
      const saved = localStorage.getItem("rwkv_task_queue");
      const parsed = saved ? JSON.parse(saved) : [];
      return parsed.map((item) => typeof item === "string" ? { query: item, queuedAt: formatCurrentTime() } : item);
    } catch {
      return [];
    }
  });

  const markdown = useMemo(() => reportToMarkdown(report), [report]);
  const isAnyRunning = history.some((task) => task.status === "running");
  const activeTaskItem = history.find((task) => task.id === activeId) || null;
  const reportScrollAffordance = useReportScrollAffordance(mainScrollRef, reportSurfaceRef, [Boolean(report), activeId]);

  const selectReport = useCallback(async (id, items = history) => {
    setActiveId(id);
    try {
      setError("");
      setReport(await getReport(id));
    } catch (reason) {
      const task = items.find((item) => item.id === id);
      if (!task || task.status === "running" || task.status === "queued") {
        setReport(null);
        return;
      }
      setError(`报告加载失败：${reason.message}`);
      setReport(null);
    }
  }, [history]);

  async function refreshHistory(selectFirst = false) {
    try {
      setError("");
      const items = await getHistory();
      setHistory(items);
      setTokenUsage(await getTokenUsage());

      const nextId = (selectFirst || !activeId) ? items[0]?.id : activeId;
      if (nextId) {
        await selectReport(nextId, items);
      } else {
        setActiveId(null);
        setReport(null);
      }
    } catch (reason) {
      setError(`历史记录获取异常：${reason.message}`);
    }
  }

  const pollHistory = useCallback(async () => {
    if (isPollingRef.current) return;
    isPollingRef.current = true;
    try {
      setHistory(await getHistory());
      setTokenUsage(await getTokenUsage());
    } catch {}
    isPollingRef.current = false;
  }, []);

  useEffect(() => {
    localStorage.setItem("rwkv_task_queue", JSON.stringify(taskQueue));
    if (!taskQueue.length) setIsQueueOpen(false);
  }, [taskQueue]);

  useEffect(() => {
    if (asyncPreferenceLoadedRef.current) localStorage.setItem("rwkv_async_parallel_enabled", JSON.stringify(asyncEnabled));
  }, [asyncEnabled]);

  useEffect(() => {
    async function loadRuntimeConfig() {
      try {
        const config = await getRuntimeConfig();
        const saved = localStorage.getItem("rwkv_async_parallel_enabled");
        if (saved === null && typeof config.slm_async_enabled === "boolean") {
          asyncPreferenceLoadedRef.current = true;
          setAsyncEnabled(config.slm_async_enabled);
        }
      } catch {}
    }
    loadRuntimeConfig();
  }, []);

  useEffect(() => {
    refreshHistory(true);
    const timer = setInterval(pollHistory, 3000);
    return () => clearInterval(timer);
  }, [pollHistory]);

  useEffect(() => {
    if (activeTaskItem) {
      const previous = prevStatusRef.current;
      const current = activeTaskItem.status;
      if (previous === "running" && (current === "completed" || current === "ready")) {
        selectReport(activeTaskItem.id);
      }
      prevStatusRef.current = current;
    } else {
      prevStatusRef.current = null;
    }
  }, [activeTaskItem, selectReport]);

  useEffect(() => {
    if (!asyncEnabled && !isAnyRunning && taskQueue.length > 0 && !isSubmitting) {
      const [nextTask, ...rest] = taskQueue;
      setTaskQueue(rest);
      executeTask(nextTask);
    }
  }, [asyncEnabled, isAnyRunning, taskQueue, isSubmitting]);

  useEffect(() => {
    const handleScrollJump = (event) => {
      const badge = event.target.closest(".citation-badge");
      if (badge) {
        const href = badge.getAttribute("href");
        if (href && href.startsWith("#source-")) {
          event.preventDefault(); 
          const targetId = href.substring(1);
          const targetElement = document.getElementById(targetId);
          if (targetElement) {
            const viewport = targetElement.closest('[data-slot="scroll-area-viewport"]');
            if (viewport) {
              const viewportRect = viewport.getBoundingClientRect();
              const targetRect = targetElement.getBoundingClientRect();
              const isVisible = (targetRect.top >= viewportRect.top) && (targetRect.bottom <= viewportRect.bottom);
              if (!isVisible) {
                const relativeTop = targetRect.top - viewportRect.top + viewport.scrollTop;
                viewport.scrollTo({ top: relativeTop - 15, behavior: "smooth" });
              }
              if (targetElement.classList.contains("source-anchor")) {
                targetElement.classList.add("source-anchor-highlight");
                setTimeout(() => targetElement.classList.remove("source-anchor-highlight"), 1500);
              }
            }
          }
        }
        return;
      }
      const backlink = event.target.closest(".citation-backlink");
      if (backlink) {
        const href = backlink.getAttribute("href");
        if (href && href.startsWith("#cite-ref-")) {
          event.preventDefault(); 
          const targetId = href.substring(1);
          const targetElement = document.getElementById(targetId);
          if (targetElement) targetElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    };
    document.addEventListener("click", handleScrollJump);
    return () => document.removeEventListener("click", handleScrollJump);
  }, []);

  function handleNewRun() {
    setActiveId(null);
    setReport(null);
    setError("");
  }

  async function handleNewTaskSubmitted(taskId) {
    try {
      const items = await getHistory();
      setHistory(items);
      if (taskId) await selectReport(taskId, items);
    } catch (error) {
      console.error("更新新任务状态失败:", error);
    }
  }

  async function executeTask(taskObj) {
    setIsSubmitting(true);
    try {
      const response = await startAnalyze({ query: taskObj.query, queued_at: taskObj.queuedAt, slm_async_enabled: asyncEnabled });
      toast.success("任务已提交");
      await handleNewTaskSubmitted(response.task_id);
    } catch (error) {
      toast.error(`提交失败：${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleQuerySubmit(newQuery) {
    const taskObj = { query: newQuery, queuedAt: formatCurrentTime() };
    if (!asyncEnabled && (isAnyRunning || isSubmitting)) {
      setTaskQueue((current) => [...current, taskObj]);
      setIsQueueOpen(true);
      toast.success("任务已加入队列");
      return;
    }
    await executeTask(taskObj);
  }

  async function handleStopTask(id) {
    try {
      await stopTask(id);
      toast.success("任务已请求停止");
      refreshHistory(false);
    } catch (reason) {
      toast.error(`中止失败：${reason.message}`);
    }
  }

  async function handleDeleteTask(id) {
    if (!window.confirm("确定彻底删除该研究记录及其所有落盘文件吗？此操作无法撤销。")) return;
    try {
      await deleteTask(id);
      toast.success("任务已删除");
      if (activeId === id) handleNewRun();
      refreshHistory(false);
    } catch (reason) {
      toast.error(`删除失败：${reason.message}`);
    }
  }

  async function copyMarkdown() {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      toast.success("报告 Markdown 已复制");
    } catch (error) {
      toast.error(`复制失败：${error.message}`);
    }
  }

  function handleAsyncEnabledChange(value) {
    asyncPreferenceLoadedRef.current = true;
    setAsyncEnabled(value);
  }

  const currentTitle = activeId ? getTaskLabel(activeTaskItem) : "准备新的研究任务";

  return (
    <>
      <SidebarProvider defaultOpen style={{ "--sidebar-width": "16rem" }}>
        <AppSidebar history={history} activeId={activeId} keyword={keyword} onKeywordChange={setKeyword} onSelect={selectReport} onNewRun={handleNewRun} onStop={handleStopTask} onDelete={handleDeleteTask} />

        <SidebarInset className="h-svh max-h-svh min-h-0 overflow-hidden">
          <header className="z-20 shrink-0 border-b border-border bg-background">
            <div className="grid h-11 w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center">
              <div className="flex h-11 items-center border-r border-border px-2.5"><SidebarTrigger className="size-8 rounded-md" /></div>
              <div className="min-w-0 truncate px-3 text-[13px] font-medium" title={currentTitle}>{currentTitle}</div>
              <div className="flex items-center gap-0.5 px-2.5">
                <Button variant="ghost" size="icon-sm" className="rounded-md" title="刷新任务" aria-label="刷新任务" onClick={() => refreshHistory(false)}><RefreshCw className="size-4" /></Button>
                {report && <Button size="sm" className="ml-1 rounded-md" onClick={copyMarkdown}><Copy className="size-4" /><span className="hidden sm:inline">复制报告</span></Button>}
              </div>
            </div>
          </header>

          <main ref={mainScrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto flex min-h-full w-full max-w-[1680px] flex-col gap-5 px-5 py-5 md:px-8 lg:px-10">
              {error && (
                <Card className="border-rose-200 bg-rose-50 text-rose-700">
                  <CardContent className="px-4 py-3 text-sm">{error}</CardContent>
                </Card>
              )}

              {taskQueue.length > 0 && <QueuePanel taskQueue={taskQueue} isQueueOpen={isQueueOpen} onToggle={() => setIsQueueOpen((value) => !value)} onClear={() => setTaskQueue([])} onRemove={(index) => setTaskQueue((current) => current.filter((_, itemIndex) => itemIndex !== index))} />}

              {!activeId && <LandingState onSubmit={handleQuerySubmit} isAnyRunning={isAnyRunning} isSubmitting={isSubmitting} asyncEnabled={asyncEnabled} onAsyncEnabledChange={handleAsyncEnabledChange} onOpenFiles={() => setFileManagerOpen(true)} />}

              {/* ✨ 核心渲染区：集成度更高、直接位于研报正上方 */}
              {activeId && activeTaskItem && (
                <div className="space-y-4">
                  <MetricsStrip report={report} task={activeTaskItem} />

                  <TaskProgressAccordion task={activeTaskItem} onStop={() => handleStopTask(activeTaskItem.id)} />

                  {report ? (
                    <>
                      <div className="report-workspace">
                        <OutlinePanel report={report} markdown={markdown} />
                        <ReportSurface report={report} surfaceRef={reportSurfaceRef} scrollAffordance={reportScrollAffordance} />
                        <aside className="report-side-rail">
                          <TaskTimingCard task={activeTaskItem} />
                          <SourcesPanel sources={report?.sources || []} />
                        </aside>
                      </div>
                      <div className="report-secondary-panels">
                        <TaskTimingCard task={activeTaskItem} />
                        <SourcesPanel sources={report?.sources || []} />
                      </div>
                    </>
                  ) : activeTaskItem.status === "running" ? (
                    <div className="py-24 flex flex-col items-center justify-center text-muted-foreground/60 animate-in fade-in duration-500">
                       <Loader2 className="size-12 animate-spin mb-6 text-primary/30" />
                       <p className="text-[15px] font-medium tracking-tight text-foreground/70">深度研究正在执行中...</p>
                       <p className="mt-2 text-xs">执行进度请查看上方状态栏，报告将在处理完成后自动呈现</p>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </main>

          {activeId && (
            <div className="z-20 shrink-0 bg-background px-5 py-3 md:px-8 lg:px-10">
              <div className="mx-auto w-full max-w-4xl">
                <Composer onSubmit={handleQuerySubmit} isAnyRunning={isAnyRunning} isSubmitting={isSubmitting} asyncEnabled={asyncEnabled} />
              </div>
            </div>
          )}
          {activeId && tokenUsage?.tasks?.[activeId] && (
            <div className="fixed bottom-6 left-6 md:left-[17.5rem] z-40 w-[240px] hidden sm:block pointer-events-none">
              <div className="pointer-events-auto"><TokenUsageCard data={tokenUsage.tasks[activeId]} /></div>
            </div>
          )}
        </SidebarInset>

        <Dialog open={fileManagerOpen} onOpenChange={setFileManagerOpen}>
          <DialogContent className="max-h-[90vh] max-w-[1200px] overflow-hidden p-0 sm:max-w-[1200px]">
            <div className="border-b border-border px-6 py-5">
              <DialogHeader><DialogTitle>本地工作区文件</DialogTitle><DialogDescription>`data/input`</DialogDescription></DialogHeader>
            </div>
            <div className="max-h-[calc(90vh-88px)] overflow-y-auto px-6 py-6"><FileManager /></div>
          </DialogContent>
        </Dialog>
      </SidebarProvider>
      <Toaster position="top-center" richColors />
    </>
  );
}