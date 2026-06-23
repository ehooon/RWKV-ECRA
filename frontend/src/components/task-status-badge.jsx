import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STATUS_STYLES = {
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  ready: "border-emerald-200 bg-emerald-50 text-emerald-700",
  running: "border-amber-200 bg-amber-50 text-amber-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  queued: "border-stone-200 bg-stone-100 text-stone-700",
};

export function TaskStatusBadge({ status, className }) {
  const normalized = String(status || "ready").toLowerCase();

  return (
    <Badge
      variant="outline"
      className={cn(
        "shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium capitalize",
        STATUS_STYLES[normalized] || "border-border bg-muted text-muted-foreground",
        className,
      )}
    >
      {normalized}
    </Badge>
  );
}
