import { useDeferredValue, useMemo } from "react";
import {
  FolderOpen,
  HistoryIcon,
  Search,
  Sparkles,
  SquarePen,
  StopCircle,
  Trash2,
} from "lucide-react";

import { TaskStatusBadge } from "@/components/task-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
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
        item.updated_at,
      ]
        .join(" ")
        .toLowerCase();

      return !needle || haystack.includes(needle);
    });
  }, [history, deferredKeyword]);

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader className="gap-4 border-b border-sidebar-border px-4 py-4">
        <div className="flex items-start gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-sm">
            <Sparkles className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-sidebar-foreground">
              RWKV-ECRA
            </div>
            <div className="text-xs leading-5 text-sidebar-foreground/70">
              长文本研究控制台
            </div>
          </div>
        </div>

        <div className="grid gap-2">
          <Button className="justify-start rounded-lg" onClick={onNewRun}>
            <SquarePen className="size-4" />
            新建分析任务
          </Button>
          <Button
            variant="outline"
            className="justify-start rounded-lg bg-sidebar"
            onClick={onOpenFiles}
          >
            <FolderOpen className="size-4" />
            本地工作区文件
          </Button>
        </div>

        <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/55 px-3 py-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-sidebar-foreground">
                异步并行
              </div>
              <div className="text-xs leading-5 text-sidebar-foreground/70">
                允许多个任务共享 SLM 队列并行执行
              </div>
            </div>
            <Switch checked={asyncEnabled} onCheckedChange={onAsyncEnabledChange} />
          </div>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-sidebar-foreground/50" />
          <Input
            value={keyword}
            onChange={(event) => onKeywordChange(event.target.value)}
            placeholder="搜索任务、状态或时间"
            className="rounded-lg border-sidebar-border bg-sidebar pl-9 shadow-none"
            type="search"
          />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="min-h-0 gap-3 p-0">
          <div className="flex items-center justify-between px-4 pt-4">
            <div className="flex items-center gap-2 text-sm font-medium text-sidebar-foreground">
              <HistoryIcon className="size-4 text-sidebar-foreground/70" />
              历史任务
            </div>
            <Badge variant="outline" className="rounded-md bg-sidebar text-sidebar-foreground/70">
              {filtered.length}
            </Badge>
          </div>

          <ScrollArea className="h-full px-2 pb-4">
            <div className="space-y-2 px-2">
              {filtered.length ? (
                filtered.map((item) => {
                  const isActive = item.id === activeId;
                  const label = getTaskLabel(item);

                  return (
                    <div
                      key={item.id}
                      className={cn(
                        "overflow-hidden rounded-xl border transition-colors",
                        isActive
                          ? "border-sidebar-border bg-sidebar"
                          : "border-transparent bg-transparent hover:bg-sidebar-accent/70",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => onSelect(item.id)}
                        className="flex w-full flex-col gap-3 px-3 py-3 text-left"
                      >
                        <div className="flex items-start gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium text-sidebar-foreground">
                              {label}
                            </div>
                            <div className="mt-1 text-xs leading-5 text-sidebar-foreground/70">
                              {item.id}
                            </div>
                          </div>
                          <TaskStatusBadge status={item.status} />
                        </div>
                        <div className="truncate text-xs text-sidebar-foreground/60">
                          {item.updated_at || "-"}
                        </div>
                      </button>

                      <div className="flex items-center justify-end gap-1 border-t border-sidebar-border/70 px-2 py-2">
                        {item.status === "running" ? (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            title="停止任务"
                            onClick={(event) => {
                              event.stopPropagation();
                              onStop(item.id);
                            }}
                          >
                            <StopCircle className="size-4" />
                          </Button>
                        ) : null}

                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title="删除任务"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDelete(item.id);
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="rounded-xl border border-dashed border-sidebar-border bg-sidebar px-4 py-6 text-sm leading-6 text-sidebar-foreground/65">
                  没有匹配的任务记录。
                </div>
              )}
            </div>
          </ScrollArea>
        </SidebarGroup>
      </SidebarContent>

      <SidebarRail />
    </Sidebar>
  );
}
