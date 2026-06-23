import { useDeferredValue, useMemo } from "react";
import {
  FolderOpen,
  HistoryIcon,
  Search,
  SquarePen,
  StopCircle,
  Trash2,
} from "lucide-react";

import {
  getTaskStatusLabel,
  TaskStatusBadge,
} from "@/components/task-status-badge";
import { Badge } from "@/components/ui/badge";
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
      <SidebarHeader className="gap-2.5 border-b border-sidebar-border px-3 py-3">
        <div className="flex min-h-10 items-center gap-2.5 px-1">
          <div
            className="relative flex size-9 shrink-0 items-center justify-center rounded-lg bg-sidebar-foreground text-sidebar"
            aria-hidden="true"
          >
            <span className="text-sm font-semibold tracking-[-0.04em]">R</span>
            <span className="absolute right-1.5 bottom-1.5 size-1 rounded-full bg-sidebar" />
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold tracking-tight text-sidebar-foreground">
              RWKV-ECRA
            </div>
            <div className="mt-0.5 truncate text-[11px] text-sidebar-foreground/60">
              长文本研究控制台
            </div>
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
          <Button className="h-9 justify-start rounded-lg px-3" onClick={onNewRun}>
            <SquarePen className="size-4" />
            新建分析任务
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-9 rounded-lg bg-sidebar shadow-none"
            title="本地工作区文件"
            aria-label="打开本地工作区文件"
            onClick={onOpenFiles}
          >
            <FolderOpen className="size-4" />
          </Button>
        </div>

        <div className="flex min-h-11 items-center justify-between gap-3 px-1">
          <div className="min-w-0">
            <div className="text-xs font-medium text-sidebar-foreground">
              异步并行
            </div>
            <div className="mt-0.5 truncate text-[11px] text-sidebar-foreground/60">
              允许多个分析任务同时运行
            </div>
          </div>
          <Switch
            checked={asyncEnabled}
            onCheckedChange={onAsyncEnabledChange}
            aria-label="切换异步并行"
          />
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-sidebar-foreground/50" />
          <Input
            value={keyword}
            onChange={(event) => onKeywordChange(event.target.value)}
            placeholder="搜索标题、状态或时间"
            aria-label="搜索历史任务"
            className="h-9 rounded-lg border-sidebar-border bg-sidebar pl-9 shadow-none"
            type="search"
          />
        </div>
      </SidebarHeader>

      <SidebarContent className="overflow-y-auto">
        <SidebarGroup className="min-h-0 gap-0 p-0">
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-sidebar-border bg-sidebar/95 px-4 py-2.5 backdrop-blur-sm">
            <div className="flex items-center gap-2 text-sm font-medium text-sidebar-foreground">
              <HistoryIcon className="size-4 text-sidebar-foreground/70" />
              历史任务
            </div>
            <Badge variant="outline" className="h-5 rounded-md bg-sidebar px-1.5 text-[11px] tabular-nums text-sidebar-foreground/65">
              {filtered.length} 项
            </Badge>
          </div>

          <div className="px-2 py-2">
            {filtered.length ? (
              <div className="space-y-0.5">
                {filtered.map((item) => {
                    const isActive = item.id === activeId;
                    const label = getTaskLabel(item);

                    return (
                    <div
                      key={item.id}
                      className={cn(
                        "group/task-item relative rounded-lg transition-colors",
                        isActive
                          ? "bg-sidebar-foreground/[0.07] text-sidebar-accent-foreground ring-1 ring-inset ring-sidebar-foreground/15"
                          : "hover:bg-sidebar-accent/65",
                      )}
                    >
                      <button
                        type="button"
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => onSelect(item.id)}
                        className="w-full rounded-lg px-3 py-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <div
                            className={cn(
                              "min-w-0 flex-1 truncate text-sm text-sidebar-foreground",
                              isActive ? "font-semibold" : "font-medium",
                            )}
                          >
                            <span title={label}>{label}</span>
                          </div>
                          <TaskStatusBadge
                            status={item.status}
                            className="max-w-20 px-1.5 py-0 text-[10px]"
                          />
                        </div>
                        <div
                          className="mt-1.5 truncate font-mono text-[11px] text-sidebar-foreground/65"
                          title={`任务编号：${item.id}`}
                        >
                          {item.id}
                        </div>
                        <div
                          className="mt-1 truncate pr-7 text-[11px] tabular-nums text-sidebar-foreground/55"
                          title={`最近更新：${item.updated_at || "暂无时间"}`}
                        >
                          {item.updated_at || "-"}
                        </div>
                      </button>

                      <div className="absolute right-1.5 bottom-1.5 flex flex-col gap-0.5 opacity-0 transition-opacity group-focus-within/task-item:opacity-100 group-hover/task-item:opacity-100">
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
