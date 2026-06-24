import {
  ArrowDown,
  BrainCircuit,
  Database,
  FileStack,
  Globe,
  PanelsTopLeft,
  Workflow,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const LAYERS = [
  {
    step: "01",
    title: "前端交互层",
    description: "任务创建、文件管理、报告预览和运行状态反馈都从这里进入系统。",
    icon: PanelsTopLeft,
    items: ["研究指令输入", "文件上传与删除", "状态轮询与报告读取"],
  },
  {
    step: "02",
    title: "智能体控制环",
    description: "调度器、分析器和规划器围绕当前任务状态持续迭代，决定下一步动作。",
    icon: BrainCircuit,
    items: ["任务理解", "信息缺口识别", "工具调用编排"],
  },
  {
    step: "03",
    title: "执行工具与工作流",
    description: "系统会根据计划调用长文本工作流、本地检索和外部搜索模块。",
    icon: Workflow,
    items: ["MapReduce 压缩", "局部捞针检索", "研报生成与排版"],
  },
  {
    step: "04",
    title: "模型与存储基座",
    description: "RWKV、外部 LLM、工作区文件和最终产出构成任务执行的底层依赖。",
    icon: Database,
    items: ["云端大模型", "端侧 RWKV", "本地工作区与输出目录"],
  },
];

const DEPENDENCIES = [
  { label: "本地文件", icon: FileStack },
  { label: "外部网络", icon: Globe },
  { label: "任务状态流", icon: Workflow },
];

export default function ArchitectureGraph() {
  return (
    <Card className="border-border bg-card">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="rounded-md text-muted-foreground">
            Agent Workflow
          </Badge>
        </div>
        <div>
          <CardTitle className="text-xl">RWKV-ECRA 控制架构</CardTitle>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="grid gap-3 lg:grid-cols-4">
          {LAYERS.map((layer, index) => {
            const Icon = layer.icon;

            return (
              <div key={layer.step} className="space-y-3">
                <div className="rounded-xl border border-border bg-background p-4">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs text-muted-foreground">{layer.step}</div>
                      <h3 className="mt-1 text-sm font-medium">{layer.title}</h3>
                    </div>
                    <div className="flex size-9 items-center justify-center rounded-xl bg-muted text-foreground">
                      <Icon className="size-4" />
                    </div>
                  </div>

                  <p className="text-sm leading-6 text-muted-foreground">
                    {layer.description}
                  </p>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {layer.items.map((item) => (
                      <Badge key={item} variant="outline" className="rounded-md bg-muted/50">
                        {item}
                      </Badge>
                    ))}
                  </div>
                </div>

                {index < LAYERS.length - 1 ? (
                  <div className="hidden items-center justify-center lg:flex">
                    <ArrowDown className="size-4 text-muted-foreground" />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-4">
          <div className="text-sm font-medium">关键依赖</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {DEPENDENCIES.map(({ label, icon: Icon }) => (
              <Badge key={label} variant="outline" className="rounded-md bg-background">
                <Icon className="size-3.5" />
                {label}
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
