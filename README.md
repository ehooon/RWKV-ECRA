# RWKV-ECRA

语言：中文 | [English](README.en.md)

示例输出：参考 data/output

RWKV-ECRA 是一个端云协同的长文档分析 Agent：
- 通过端云协同的方法，估算每小时可以分析千万 token 级的文本，同时可以节省 80% 以上的 token

- 由大模型负责理解任务、规划步骤、调用工具和撰写最终报告

- 使用可以在单张 5090 上达到 10000+ token/s 速度的 RWKV-7 7.2B 最新版本负责对长文档进行分块阅读、事实提取、摘要压缩和中间材料生产

- 项目目标不是让单个模型一次性吞下全部上下文，而是把长文档分析拆成可追踪、可恢复、可扩展的协作节点，最终生成跨文件的深度分析报告

当前版本的核心能力：

- 扫描 `data/input` 下的本地文档，目前支持 `.txt` 和 `.md`
- 对文档进行抽样试读，先判断主题、体裁和分析策略
- 将长文档切分为语义片段，交给小模型批量并行处理
- 采用 Summary + Facts 双轨提取：一条轨道负责逻辑摘要，一条轨道负责关键事实保真
- 使用 Reduce 步骤逐层压缩和合并片段材料
- 由大模型融合所有中间材料，亲自写出最终 Markdown 报告
- 支持中间结果 checkpoint、运行日志和小模型调用日志，便于恢复与排查

## 项目用法

### 1. 准备环境

建议使用 Python 3.10 或更新版本。

安装当前代码需要的基础依赖：

```bash
pip install openai requests tiktoken
```

项目默认使用：

- 小模型：本地 RWKV 模型，配置和使用方法参考 [RWKV 中文官网高并发推理教程](https://www.rwkv.cn/tutorials/intermediate/rwkv_lightning)，配置在 `config.py` 的 `SLM_CONFIG`。
- 大模型：百度 AI Studio 兼容 OpenAI SDK 的接口，配置在 `clients/llm_client.py` 和 `config.py`，使用需要到[飞桨星河平台](https://aistudio.baidu.com/account/accessToken)获取key。

（为什么在这里用文心？因为我没配置 web_search，所以找了一个内嵌 web_search 的文心5.1，便于测试后续加入 deepresearch 等协作）

运行前请确认：

1. `config.py` 中的 `API_KEYS["baidu"]` 已替换为可用 key。
2. 本地小模型服务已经启动，并且接口、密码与 `SLM_CONFIG` 一致。
3. 待分析文件已放入 `data/input` 目录。

### 2. 放入输入文件

把需要分析的 `.md` 或 `.txt` 文件放到：

```text
data/input/
```

如果要分析多个文件，Agent 会先扫描文件列表，再逐个试读和委托分析，最后在总报告里做跨文件关联分析。

### 3. 修改任务指令

当前入口在 `main.py`。可以修改其中的 `query` 来改变任务目标，例如：

```python
query = "帮我深度分析 tilelang 这篇文章，并给出跨文件关联分析。"
```

### 4. 运行项目

```bash
python main.py
```

运行后，项目会自动创建输入、输出等目录，并执行完整分析流程。

最终报告会写入：

```text
data/output/
```

运行过程日志会写入：

```text
logs/
```

中间 checkpoint 会写入：

```text
data/checkpoints/
```

任务完成后，当前实现会清理 checkpoint。若任务中断，下次启动时会检测 checkpoint 并尝试复用已有中间结果。

## 项目设计逻辑

这个项目的设计逻辑是：保持当前主流程稳定，在主流程的每个节点上增删协作机制，用协作优化当前节点的效果。后续可以继续添加循环 check、质量评估、反思修正等机制，但当前版本先专注核心结构。

主流程可以理解为：

```text
理解用户意图
  -> 盘点本地文件
  -> 抽样试读并构建文件画像
  -> 制定分析策略
  -> 委托小模型执行 MapReduce
  -> 大模型融合材料并撰写最终报告
  -> 导出 Markdown
```

### 1. 大模型负责主线编排

`agent/orchestrator.py` 中的 `Orchestrator` 是主控入口。不直接读取和总结所有文档，而是通过工具调用推进任务：

- `search_local_file`：扫描输入目录，获取可处理文件列表
- `preview_document_content`：对单个文件抽样试读，帮助判断文档结构和重点
- `delegate_to_small_models`：把长文档处理任务下发给小模型协作引擎
- `export_report_to_md`：保存大模型亲自撰写的最终报告

大模型在这里承担“规划”任务：理解需求、选择工具、决定每个文件的处理策略，并在最后把分散材料重新组织成一份连贯报告。

### 2. 小模型负责局部高并发处理

`tools/local_data_processor.py` 中的 `delegate_to_small_models` 是当前协作结构的核心。它会把长文档切分成多个 chunk，然后对每个 chunk 同时发起两类任务：

- Summary 轨道：提炼片段的逻辑、结构和主题
- Facts 轨道：提取关键事实、数据、术语和明确结论

在保持事实提取精度的同时进行高质量总结。

### 3. Reduce 负责压缩和合并

当 chunk 数量较多时，片段摘要会继续进入 Reduce 阶段。Reduce 会按 token 数量分组，把多个局部摘要逐层合并为更短、更集中的材料。

这个阶段的目标不是生成最终文章，而是把“小模型局部阅读结果”压缩成“大模型可吸收的中间材料”。最终表达权仍然交给大模型。

### 4. Checkpoint 和日志保证过程可追踪

项目内置了两类辅助机制：

- `utils/checkpoint.py`：缓存已经完成的文件级分析结果，减少中断后重复计算
- `utils/tracker.py`：记录大模型决策、小模型输入输出和工具执行结果，便于调试和复盘

这些机制不是主流程本身，但它们让协作过程更稳：失败可以恢复，效果可以观察，问题可以定位。

### 5. 后续优化计划

- 做一个能用的前端，现在直接在代码里改提示词太简陋了
- 在试读后加入策略 check，判断是否需要重新选择分析重点
- 在 MapReduce 后加入质量 check，发现空摘要、幻觉或事实不足时重跑局部节点
- 在最终报告前加入 cross-file check，专门检查跨文件关联是否充分
- 引入 PaddleOCR-VL 或其他以视觉语言OCR模型来处理“任意文件”
- 在节点上增加更多协作角色，保持主流程稳定的同时，逐节点优化
