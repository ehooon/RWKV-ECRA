import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  File,
  FileText,
  Folder,
  FolderOpen,
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

import ArchitectureGraph from "./ArchitectureGraph.jsx";
import { getHistory, getReport, startAnalyze, stopTask, deleteTask, getFiles, deleteFile, getFileContent, uploadFile, getRuntimeConfig } from "./api.js";
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
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
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

function buildFileTree(paths) {
  const root = { name: "root", type: "folder", children: {}, path: "" };

  paths.forEach((path) => {
    const parts = path.split(/[/\\]/).filter(Boolean);
    let current = root;

    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;

      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          type: isFile ? "file" : "folder",
          path: isFile ? path : parts.slice(0, index + 1).join("/"),
          children: {},
        };
      }

      current = current.children[part];
    });
  });

  return root;
}

function getAllFilePaths(node) {
  if (node.type === "file") {
    return [node.path];
  }

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
      <div
        className={cn(
          "group flex items-center justify-between rounded-lg pr-2 transition-colors hover:bg-muted/70",
          activePath === node.path && "bg-muted",
        )}
        style={{ paddingLeft }}
      >
        <button
          type="button"
          onClick={() => onView(node.path)}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left text-sm"
        >
          <File className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
        </button>

        <Button
          variant="ghost"
          size="icon-xs"
          title="删除文件"
          className="opacity-0 group-hover:opacity-100"
          onClick={(event) => {
            event.stopPropagation();
            onDelete(node);
          }}
        >
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
      <div
        className="group flex items-center justify-between rounded-lg pr-2 transition-colors hover:bg-muted/70"
        style={{ paddingLeft }}
      >
        <button
          type="button"
          onClick={() => setIsOpen((value) => !value)}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left text-sm font-medium"
        >
          {isOpen ? (
            <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
          )}
          <Folder className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{node.name}</span>
        </button>

        <Button
          variant="ghost"
          size="icon-xs"
          title="删除文件夹"
          className="opacity-0 group-hover:opacity-100"
          onClick={(event) => {
            event.stopPropagation();
            onDelete(node);
          }}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>

      {isOpen ? (
        <div className="space-y-0.5">
          {childrenNodes.map((child) => (
            <FileTreeNode
              key={`${node.path}-${child.name}`}
              node={child}
              level={level + 1}
              activePath={activePath}
              onView={onView}
              onDelete={onDelete}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function FileManager() {
  const [files, setFiles] = useState([]);
  const [activePath, setActivePath] = useState("");
  const [preview, setPreview] = useState(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const revokePreviewUrl = useCallback((value) => {
    if (value?.type === "image" && value.url) {
      URL.revokeObjectURL(value.url);
    }
  }, []);

  const loadFiles = useCallback(async () => {
    try {
      setFiles(await getFiles());
    } catch (error) {
      toast.error(`加载文件失败：${error.message}`);
    }
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    return () => revokePreviewUrl(preview);
  }, [preview, revokePreviewUrl]);

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
      setPreview((current) => {
        revokePreviewUrl(current);
        return nextPreview;
      });
    } catch (error) {
      toast.error(`无法加载文件内容：${error.message}`);
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function handleDelete(node) {
    const isFolder = node.type === "folder";
    const message = isFolder
      ? `确认删除整个文件夹 "${node.name}" 及其所有内容吗？`
      : `确认删除文件 "${node.name}" 吗？`;

    if (!window.confirm(message)) return;

    try {
      const pathsToDelete = getAllFilePaths(node);
      await Promise.all(pathsToDelete.map((path) => deleteFile(path)));

      if (pathsToDelete.includes(activePath)) {
        setActivePath("");
        setPreview((current) => {
          revokePreviewUrl(current);
          return null;
        });
      }

      toast.success(isFolder ? "文件夹已删除" : "文件已删除");
      await loadFiles();
    } catch (error) {
      toast.error(`删除失败：${error.message}`);
    }
  }

  const fileTree = useMemo(() => buildFileTree(files), [files]);
  const rootChildren = useMemo(
    () =>
      Object.values(fileTree.children).sort((a, b) => {
        if (a.type === b.type) return a.name.localeCompare(b.name);
        return a.type === "folder" ? -1 : 1;
      }),
    [fileTree],
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-base">文件树</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <label className="block">
              <input
                type="file"
                multiple
                accept=".md,.txt,.png,.jpg,.jpeg,.webp,.svg,.gif"
                className="hidden"
                onChange={handleUploadFiles}
              />
              <Button variant="outline" className="w-full justify-start rounded-lg" render={<span />}>
                <Upload className="size-4" />
                上传文件
              </Button>
            </label>

            <label className="block">
              <input
                type="file"
                multiple
                webkitdirectory=""
                className="hidden"
                onChange={handleUploadFiles}
              />
              <Button variant="outline" className="w-full justify-start rounded-lg" render={<span />}>
                <FolderOpen className="size-4" />
                上传整个文件夹
              </Button>
            </label>
          </div>

          <ScrollArea className="h-[420px] rounded-xl border border-border bg-muted p-2">
            {rootChildren.length ? (
              <div className="space-y-1">
                {rootChildren.map((child) => (
                  <FileTreeNode
                    key={child.name}
                    node={child}
                    activePath={activePath}
                    onView={handleView}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm leading-6 text-muted-foreground">
                暂无本地工作区文件。
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-base">
            {activePath || "文件预览"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isPreviewLoading ? (
            <div className="flex h-[420px] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
              <Loader2 className="mr-2 size-4 animate-spin" />
              正在读取文件内容
            </div>
          ) : preview?.type === "image" ? (
            <div className="flex h-[420px] items-center justify-center overflow-hidden rounded-xl border border-border bg-muted p-4">
              <img
                src={preview.url}
                alt={activePath}
                className="max-h-full max-w-full rounded-lg object-contain"
              />
            </div>
          ) : preview?.type === "text" ? (
            <ScrollArea className="h-[420px] rounded-xl border border-border bg-muted">
              <pre className="p-4 text-xs leading-6 whitespace-pre-wrap text-foreground">
                {preview.content}
              </pre>
            </ScrollArea>
          ) : (
            <div className="flex h-[420px] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
              选择文件后显示预览。
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Composer({ onSubmit, isAnyRunning, isSubmitting, asyncEnabled }) {
  const [query, setQuery] = useState("");
  const textareaRef = useRef(null);
  const shouldEnqueue = !asyncEnabled && isAnyRunning;

  function resizeTextarea(target) {
    target.style.height = "auto";
    target.style.height = `${Math.min(target.scrollHeight, 220)}px`;
  }

  function handleSubmit() {
    if (!query.trim() || isSubmitting) return;
    onSubmit(query.trim());
    setQuery("");

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  return (
    <Card className="border-border bg-card">
      <CardContent className="p-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <Textarea
            ref={textareaRef}
            value={query}
            rows={4}
            placeholder="输入研究主题，例如：提取本地工作区中所有研报的核心逻辑并对比差异。按 Enter 发送，Shift + Enter 换行。"
            className="min-h-[112px] resize-none border-border bg-background px-3 py-3 leading-7 shadow-none focus-visible:ring-2"
            onChange={(event) => setQuery(event.target.value)}
            onInput={(event) => resizeTextarea(event.target)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit();
              }
            }}
          />

          <Button
            className="h-auto min-w-32 rounded-xl px-4 py-3"
            disabled={isSubmitting || !query.trim()}
            onClick={handleSubmit}
          >
            {isSubmitting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : shouldEnqueue ? (
              <ListPlus className="size-4" />
            ) : (
              <Play className="size-4" />
            )}
            {shouldEnqueue ? "加入排队" : "开始分析"}
          </Button>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs leading-5 text-muted-foreground">
          <Badge variant="outline" className="rounded-md">
            RWKV Agent
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function QueuePanel({ taskQueue, isQueueOpen, onToggle, onClear, onRemove }) {
  return (
    <Card className="border-border bg-card">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-base">待处理队列</CardTitle>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="rounded-md">
            {taskQueue.length}
          </Badge>
          <Button variant="outline" size="sm" onClick={onToggle}>
            {isQueueOpen ? "收起" : "展开"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClear}>
            清空
          </Button>
        </div>
      </CardHeader>

      {isQueueOpen ? (
        <CardContent>
          <div className="space-y-2">
            {taskQueue.map((task, index) => (
              <div
                key={`${task.query}-${task.queuedAt}-${index}`}
                className="flex items-center gap-3 rounded-xl border border-border bg-muted/60 px-3 py-3"
              >
                <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-foreground text-[11px] font-medium text-background">
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{task.query}</div>
                  <div className="text-xs text-muted-foreground">{task.queuedAt}</div>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  title="移出队列"
                  onClick={() => onRemove(index)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      ) : null}
    </Card>
  );
}

function TaskTimingCard({ task }) {
  if (!task) return null;

  const runTime = parseTaskTime(task.id);
  const isDone = ["completed", "failed", "ready"].includes(task.status);

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock3 className="size-4" />
          任务时间线
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">提交排队</span>
          <span className="font-mono text-xs">{task.queued_at || "-"}</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">开始运行</span>
          <span className="font-mono text-xs">{runTime || task.updated_at || "-"}</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">报告生成</span>
          <span className="font-mono text-xs">{isDone ? task.updated_at || "-" : "正在执行..."}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function ExecutionFeed({ progress, onStop }) {
  return (
    <Card className="border-border bg-card">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Workflow className="size-4" />
            深度思考与研究执行中
          </CardTitle>
        </div>
        <Button variant="outline" size="sm" onClick={onStop}>
          <StopCircle className="size-4" />
          中止
        </Button>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[320px] rounded-xl border border-border bg-muted">
          <pre className="p-4 text-xs leading-6 whitespace-pre-wrap text-foreground/80">
            {progress || "系统正在初始化执行环境，即将启动探索..."}
          </pre>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function MetricsStrip({ report, task }) {
  const items = [
    { label: "状态", value: task?.status || "-" },
    {
      label: "章节规模",
      value: report?.nodes?.length || (report?.markdown ? 1 : 0),
      suffix: "节",
    },
    { label: "数据来源", value: report?.sources?.length || 0, suffix: "项" },
    { label: "最近更新", value: task?.updated_at || report?.updated_at || "-" },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label} className="border-border bg-card">
          <CardContent className="flex items-center justify-between px-4 py-4">
            <div>
              <div className="text-xs text-muted-foreground">{item.label}</div>
              <div className="mt-2 text-sm font-medium">
                {item.value}
                {item.suffix ? ` ${item.suffix}` : ""}
              </div>
            </div>
            {item.label === "状态" ? <TaskStatusBadge status={task?.status} /> : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function OutlinePanel({ report, markdown }) {
  const items = report?.nodes?.length
    ? report.nodes.map((node, index) => ({
        id: `node-${index}`,
        title: node.title || `章节 ${index + 1}`,
      }))
    : extractMarkdownOutline(markdown);

  return (
    <Card className="sticky top-20 hidden border-border xl:block">
      <CardHeader>
        <CardTitle className="text-base">大纲导航</CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[60vh] pr-4">
          {items.length ? (
            <div className="space-y-1">
              {items.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className="block rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  {item.title}
                </a>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">无大纲</div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function SourcesPanel({ sources = [] }) {
  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-base">溯源索引</CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[52vh] pr-4">
          {sources.length ? (
            <div className="space-y-3">
              {sources.map((source) => (
                <div
                  key={`${source.index}-${source.title}`}
                  id={`source-${source.index}`}
                  className="source-anchor rounded-xl border border-border bg-muted/60 p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <Badge variant="outline" className="rounded-md">
                      [{source.index}]
                    </Badge>
                    <Badge variant="outline" className="rounded-md text-muted-foreground">
                      {source.type === "web" ? "互联网检索" : "本地工作区文件"}
                    </Badge>
                  </div>
                  <div className="mt-3 text-sm leading-6">
                    {source.url ? (
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-foreground underline decoration-border underline-offset-4 hover:text-muted-foreground"
                      >
                        {source.title || source.url}
                      </a>
                    ) : (
                      <span>{source.title || "内部文档"}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">无引用来源</div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function ReportSurface({ report }) {
  if (!report) return null;

  return (
    <Card className="border-border bg-card">
      <CardContent className="px-6 py-6 md:px-8 md:py-8">
        {report.nodes?.length ? (
          <article className="space-y-12">
            {report.nodes.map((node, index) => (
              <section key={node.id || index} id={`node-${index}`} className="scroll-mt-24 space-y-5">
                <div className="border-b border-border pb-4">
                  <h2 className="text-2xl font-medium tracking-tight">
                    {node.title || `章节 ${index + 1}`}
                  </h2>
                </div>
                <div
                  className="report-markdown"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(node.content || "") }}
                />
              </section>
            ))}
          </article>
        ) : (
          <article className="report-markdown">
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(report.markdown || "") }} />
          </article>
        )}
      </CardContent>
    </Card>
  );
}

function LandingState() {
  return (
    <div className="space-y-6">
      <Card className="border-border bg-card">
        <CardContent className="grid gap-6 px-6 py-8 lg:grid-cols-[1.2fr_0.8fr] lg:px-8">
          <div className="space-y-4">
            <div>
              <h1 className="text-3xl font-medium tracking-tight md:text-4xl">
                开启 RWKV 长文本研究
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground md:text-base">
                上传资料并输入研究主题，即可开始分析。
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {[
              {
                title: "本地资料接入",
                desc: "支持 Markdown、文本和图片。",
              },
              {
                title: "任务编排",
                desc: "支持排队和异步并行。",
              },
              {
                title: "结构化报告",
                desc: "输出章节化结果与引用索引。",
              },
            ].map((item) => (
              <div key={item.title} className="rounded-xl border border-border bg-muted/60 p-4">
                <div className="text-sm font-medium">{item.title}</div>
                <div className="mt-2 text-sm leading-6 text-muted-foreground">{item.desc}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <ArchitectureGraph />
    </div>
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
  const [isQueueOpen, setIsQueueOpen] = useState(false);
  const asyncPreferenceLoadedRef = useRef(false);
  const prevStatusRef = useRef(null);

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
      return parsed.map((item) =>
        typeof item === "string"
          ? { query: item, queuedAt: formatCurrentTime() }
          : item,
      );
    } catch {
      return [];
    }
  });

  const markdown = useMemo(() => reportToMarkdown(report), [report]);
  const isAnyRunning = history.some((task) => task.status === "running");
  const runningTask = history.find((task) => task.status === "running");
  const activeTaskItem = history.find((task) => task.id === activeId) || null;

  const selectReport = useCallback(async (id, items = history) => {
    setActiveId(id);

    try {
      setError("");
      setReport(await getReport(id));
    } catch (reason) {
      const task = items.find((item) => item.id === id);

      if (task?.status === "running") {
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
    try {
      setHistory(await getHistory());
    } catch {}
  }, []);

  useEffect(() => {
    localStorage.setItem("rwkv_task_queue", JSON.stringify(taskQueue));
    if (!taskQueue.length) {
      setIsQueueOpen(false);
    }
  }, [taskQueue]);

  useEffect(() => {
    if (asyncPreferenceLoadedRef.current) {
      localStorage.setItem("rwkv_async_parallel_enabled", JSON.stringify(asyncEnabled));
    }
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

  function handleNewRun() {
    setActiveId(null);
    setReport(null);
    setError("");
  }

  async function handleNewTaskSubmitted(taskId) {
    await refreshHistory(false);

    if (taskId) {
      await selectReport(taskId);
    }
  }

  async function executeTask(taskObj) {
    setIsSubmitting(true);

    try {
      const response = await startAnalyze({
        query: taskObj.query,
        queued_at: taskObj.queuedAt,
        slm_async_enabled: asyncEnabled,
      });

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
    if (!window.confirm("确定彻底删除该研究记录及其所有落盘文件吗？此操作无法撤销。")) {
      return;
    }

    try {
      await deleteTask(id);
      toast.success("任务已删除");

      if (activeId === id) {
        handleNewRun();
      }

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

  const currentTitle = activeId
    ? getTaskLabel(activeTaskItem)
    : "准备新的研究任务";

  const currentSubtitle = activeId
    ? activeTaskItem?.status === "running"
      ? "任务执行中"
      : report?.kind === "markdown"
        ? "Markdown 报告"
        : "结构化报告"
    : "";

  return (
    <>
      <SidebarProvider defaultOpen style={{ "--sidebar-width": "18rem" }}>
        <AppSidebar
          history={history}
          activeId={activeId}
          keyword={keyword}
          onKeywordChange={setKeyword}
          onSelect={selectReport}
          onNewRun={handleNewRun}
          onStop={handleStopTask}
          onDelete={handleDeleteTask}
          onOpenFiles={() => setFileManagerOpen(true)}
          asyncEnabled={asyncEnabled}
          onAsyncEnabledChange={handleAsyncEnabledChange}
        />

        <SidebarInset>
          <header className="sticky top-0 z-20 border-b border-border bg-background">
            <div className="mx-auto flex h-16 w-full max-w-[1680px] items-center gap-3 px-4 md:px-6 lg:px-8">
              <SidebarTrigger />
              <Separator orientation="vertical" className="hidden h-6 md:block" />

              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{currentTitle}</div>
                {currentSubtitle ? (
                  <div className="truncate text-xs text-muted-foreground">
                    {currentSubtitle}
                  </div>
                ) : null}
              </div>

              <div className="flex items-center gap-2">
                <Button variant="outline" className="hidden rounded-lg md:inline-flex" onClick={() => setFileManagerOpen(true)}>
                  <FolderOpen className="size-4" />
                  工作区文件
                </Button>
                <Button variant="outline" className="rounded-lg" onClick={() => refreshHistory(false)}>
                  <RefreshCw className="size-4" />
                  <span className="hidden sm:inline">刷新</span>
                </Button>
                {report ? (
                  <Button className="rounded-lg" onClick={copyMarkdown}>
                    <Copy className="size-4" />
                    <span className="hidden sm:inline">复制报告</span>
                  </Button>
                ) : null}
              </div>
            </div>
          </header>

          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-6 px-4 py-6 md:px-6 lg:px-8">
              {error ? (
                <Card className="border-rose-200 bg-rose-50 text-rose-700">
                  <CardContent className="px-4 py-3 text-sm">{error}</CardContent>
                </Card>
              ) : null}

              {taskQueue.length ? (
                <QueuePanel
                  taskQueue={taskQueue}
                  isQueueOpen={isQueueOpen}
                  onToggle={() => setIsQueueOpen((value) => !value)}
                  onClear={() => setTaskQueue([])}
                  onRemove={(index) => setTaskQueue((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                />
              ) : null}

              {activeId && activeTaskItem?.status === "running" ? (
                <ExecutionFeed
                  progress={activeTaskItem.progress}
                  onStop={() => handleStopTask(activeTaskItem.id)}
                />
              ) : null}

              {!activeId && isAnyRunning && runningTask ? (
                <ExecutionFeed
                  progress={runningTask.progress}
                  onStop={() => handleStopTask(runningTask.id)}
                />
              ) : null}

              {!activeId && !isAnyRunning ? <LandingState /> : null}

              {report ? (
                <div className="space-y-6">
                  <MetricsStrip report={report} task={activeTaskItem} />

                  <div className="grid gap-6 xl:grid-cols-[240px_minmax(0,1fr)_320px]">
                    <OutlinePanel report={report} markdown={markdown} />

                    <ReportSurface report={report} />

                    <div className="space-y-6">
                      <TaskTimingCard task={activeTaskItem} />
                      <SourcesPanel sources={report?.sources || []} />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="sticky bottom-0 border-t border-border bg-background px-4 py-4 md:px-6 lg:px-8">
            <div className="mx-auto w-full max-w-5xl">
              <Composer
                onSubmit={handleQuerySubmit}
                isAnyRunning={isAnyRunning}
                isSubmitting={isSubmitting}
                asyncEnabled={asyncEnabled}
              />
            </div>
          </div>
        </SidebarInset>

        <Dialog open={fileManagerOpen} onOpenChange={setFileManagerOpen}>
          <DialogContent className="max-h-[90vh] max-w-[1200px] overflow-hidden p-0 sm:max-w-[1200px]">
            <div className="border-b border-border px-6 py-5">
              <DialogHeader>
                <DialogTitle>本地工作区文件</DialogTitle>
                <DialogDescription>`data/input`</DialogDescription>
              </DialogHeader>
            </div>
            <div className="max-h-[calc(90vh-88px)] overflow-y-auto px-6 py-6">
              <FileManager />
            </div>
          </DialogContent>
        </Dialog>
      </SidebarProvider>

      <Toaster position="top-center" richColors />
    </>
  );
}
