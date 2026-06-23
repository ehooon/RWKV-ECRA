import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  Files,
  FolderOpen,
  Gauge,
  Search,
  SquarePen,
  StopCircle,
  Trash2,
} from "lucide-react";

import {
  getTaskStatusLabel,
  TaskStatusIndicator,
} from "@/components/task-status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

function getTaskLabel(item) {
  if (item.query?.trim()) {
    return item.query.trim();
  }

  return item.title || item.id;
}

function parseDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;

  const normalized = String(value).trim().replace(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/,
    "$1-$2-$3T$4:$5:$6",
  );
  const date = new Date(normalized);

  return Number.isNaN(date.getTime()) ? null : date;
}

function formatRelativeTime(value, now) {
  const date = parseDate(value);
  if (!date) return "-";

  const seconds = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 1000));
  if (seconds < 60) return "0m";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;

  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;

  return `${Math.floor(months / 12)}y`;
}

export function AppSidebar({
  history,
  activeId,
  keyword,
  onKeywordChange,
  onSelect,
  onNewRun,
  onStop,
  onDelete,
  onOpenFiles,
  asyncEnabled,
  onAsyncEnabledChange,
  ...props
}) {
  const deferredKeyword = useDeferredValue(keyword);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const filtered = useMemo(() => {
    const needle = deferredKeyword.trim().toLowerCase();

    return history.filter((item) => {
      const haystack = [
        item.id,
        item.title,
        item.query,
        item.status,
        getTaskStatusLabel(item.status),
        item.updated_at,
      ]
        .join(" ")
        .toLowerCase();

      return !needle || haystack.includes(needle);
    });
  }, [history, deferredKeyword]);

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader className="gap-2 border-b border-sidebar-border px-2.5 py-2">
        <div className="flex h-8 items-center gap-2 px-0.5">
          <div
            className="flex size-7 shrink-0 items-center justify-center rounded-md bg-sidebar-foreground text-sidebar"
            aria-hidden="true"
          >
            <span className="text-xs font-semibold tracking-[-0.03em]">R·</span>
          </div>
          <div className="min-w-0 truncate text-[13px] font-semibold tracking-tight text-sidebar-foreground">
            RWKV-ECRA
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button className="h-8 min-w-0 flex-1 justify-start rounded-md px-2.5" onClick={onNewRun}>
            <SquarePen className="size-3.5" />
            新建任务
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-8 rounded-md"
            title="本地工作区文件"
            aria-label="打开本地工作区文件"
            onClick={onOpenFiles}
          >
            <FolderOpen className="size-3.5" />
          </Button>
          <div
            className="flex h-8 items-center gap-1.5 rounded-md px-1.5 text-sidebar-foreground/65"
            title="异步并行"
          >
            <Gauge className="size-3.5" aria-hidden="true" />
            <Switch
              checked={asyncEnabled}
              onCheckedChange={onAsyncEnabledChange}
              aria-label="切换异步并行"
              className="scale-90"
            />
          </div>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-sidebar-foreground/45" />
          <Input
            value={keyword}
            onChange={(event) => onKeywordChange(event.target.value)}
            placeholder="搜索任务"
            aria-label="搜索历史任务"
            className="h-8 rounded-md border-sidebar-border bg-sidebar pl-8 text-xs shadow-none"
            type="search"
          />
        </div>
      </SidebarHeader>

      <SidebarContent className="overflow-y-auto">
        <SidebarGroup className="min-h-0 gap-0 p-0">
          <div className="sticky top-0 z-10 flex h-8 items-center justify-between border-b border-sidebar-border bg-sidebar px-3">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-sidebar-foreground/60">
              <Files className="size-3.5" aria-hidden="true" />
              任务
            </div>
            <span className="text-[11px] tabular-nums text-sidebar-foreground/45">
              {filtered.length}
            </span>
          </div>

          <div className="px-1.5 py-1.5">
            {filtered.length ? (
              <div>
                {filtered.map((item) => {
                    const isActive = item.id === activeId;
                    const label = getTaskLabel(item);
                    const relativeTime = formatRelativeTime(item.updated_at, now);

                    return (
                    <div
                      key={item.id}
                      className={cn(
                        "group/task-item relative rounded-md transition-colors duration-150",
                        isActive
                          ? "bg-sidebar-foreground/[0.08] text-sidebar-accent-foreground"
                          : "hover:bg-sidebar-foreground/[0.045]",
                      )}
                    >
                      <button
                        type="button"
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => onSelect(item.id)}
                        className="flex h-9 w-full items-center gap-1.5 rounded-md px-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
                      >
                        <div
                          className={cn(
                            "min-w-0 flex-1 truncate text-[13px] text-sidebar-foreground",
                            isActive ? "font-semibold" : "font-normal",
                          )}
                          title={label}
                        >
                          {label}
                        </div>
                        <div className="flex shrink-0 items-center gap-1 transition-opacity group-focus-within/task-item:opacity-0 group-hover/task-item:opacity-0">
                          <TaskStatusIndicator status={item.status} />
                          <span
                            className="text-right font-mono text-[9px] tabular-nums text-sidebar-foreground/45"
                            title={item.updated_at || "暂无时间"}
                          >
                            {relativeTime}
                          </span>
                        </div>
                      </button>

                      <div className="pointer-events-none absolute inset-y-0 right-1 flex items-center gap-0.5 bg-inherit pl-2 opacity-0 transition-opacity group-focus-within/task-item:pointer-events-auto group-focus-within/task-item:opacity-100 group-hover/task-item:pointer-events-auto group-hover/task-item:opacity-100">
                        {item.status === "running" ? (
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              title="停止任务"
                              aria-label={`停止任务 ${label}`}
                              onClick={(event) => {
                                event.stopPropagation();
                                onStop(item.id);
                              }}
                            >
                              <StopCircle className="size-3.5" />
                            </Button>
                          ) : null}
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          title="删除任务"
                          aria-label={`删除任务 ${label}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            onDelete(item.id);
                          }}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="px-3 py-8 text-center text-sm leading-6 text-sidebar-foreground/60">
                <div className="font-medium text-sidebar-foreground/75">
                  {keyword.trim() ? "没有找到匹配的任务" : "还没有历史任务"}
                </div>
                <div className="mt-1 text-xs">
                  {keyword.trim() ? "尝试修改搜索词" : "新建任务后会显示在这里"}
                </div>
              </div>
            )}
          </div>
        </SidebarGroup>
      </SidebarContent>

      <SidebarRail />
    </Sidebar>
  );
}
