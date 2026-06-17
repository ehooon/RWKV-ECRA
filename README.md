# RWKV-ECRA

语言：中文 | [English](README.en.md)

## 功能介绍和效果展示

本工具专注长文本精炼分析，对多元信息做分维度分析，进行「信息减法」帮助用户快速定位核心价值。
与 DeepResearch 的深度扩散式调研不同，它不会造成可能的信息冗余，也不会替你做决定，而是呈现一份精炼的定性分析报告。

启用前端后，可以逐个输入研究内容进行排队；
![](./Imgs/example.png)

最终的报告会呈现对于已有内容的分析并标注来源，更多示例可以在 data/output 目录下查看，为了避免版权问题，input目录下仅存放了在arxiv上开放获取的论文。
![](./Imgs/example1.png)


## 使用方法

### 1. 准备环境

建议使用 Python 3.10 或更新版本。

安装当前代码需要的基础依赖（建议用 uv pip，自动处理冲突更快）：

```bash
pip install fastapi uvicorn python-multipart openai requests tavily-python
```

> 项目默认使用 RWKV 最新版本模型，已配置好 7.2B 适用的提示词和适用参数，使用更大模型可以不更改参数，使用更小模型建议缩小输入长度，其他参数仍是较优参数；

> 配置了基于火山引擎和飞桨星河的大模型调用，其中飞桨配置的大模型调用内嵌搜索引擎，已设置强制引用，针对火山引擎配置了`tavily`，后续会增加搜索更全面的其他引擎。

### rwkv_lightning 配置说明

本项目需要调用 [rwkv_lightning](https://github.com/RWKV-Vibe/rwkv_lightning) 启动的模型，后续会增加[Albatross](https://github.com/BlinkDL/Albatross) 推理引擎的调用方法；

详细的配置和使用教程参考 [rwkv_lightning 批量推理教程](https://www.rwkv.cn/tutorials/intermediate/rwkv_lightning)

### 3. 参数配置说明

此处为 config.json 中的参数说明

> 运行前需要配置的部分

| 参数名 | 参数功能 | 可选项 |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | 模型来源，目前可选火山引擎和飞桨星河 | `baidu` `volcengine` |
| `API_KEYS.baidu` | 飞桨星河的 API_Key | `任意合法 Key`（不用可以不配置） |
| `API_KEYS.volcengine` | 火山引擎的 API_Key | `任意合法 Key`（不用可以不配置） |
| `API_KEYS.tavily` | tavily 搜索引擎的 API_Key | `任意合法 Key` |

其他已预制可修改的参数请查看附录

### 4. 纯命令行启动

```bash
cd RWKV-ECRA
python main.py
```

启动可以在命令行输入指令：
```
帮我看看基于RWKV的研究的动态，并看看有什么目前和RWKV无直接关系，但是有可能后续能支持RWKV研究或被RWKV支撑进行研究的，注意不要只看本地的文件，还要搜一下
```

### 5. 可视化启动

```bash
python api.py
```
启动后，服务默认在 http://0.0.0.0:8787 运行，前端已适配此端口；

然后启动另一个终端，进入 `RWKV-ECRA/frontend`

```bash
npm install
npm run dev
```
> 此处需要提前配置 Node.js，配置方法请查看 Node.js 官网；

启动后，默认运行在 `http://127.0.0.1:5177`

## 后续优化计划

- 内置 [Albatross](https://github.com/BlinkDL/Albatross) 推理引擎，保留目前的在[rwkv_lightning](https://github.com/RWKV-Vibe/rwkv_lightning)起的服务上运行的方法；
- 优化效果和执行路径
- 美化前端和细化日志，目前前端不够漂亮，逻辑也不够优美
- 支持更多来源的大模型和搜索引擎
- 目前还存在一些引用解析和传递问题，近期会修复

## 附录
### 1. 其他可修改参数
> 已设置了默认参数，可更改的部分

| 参数名 | 参数功能 | 可选项 |
| :--- | :--- | :--- |
| `LLM_ENDPOINTS.volcengine.base_url` | 火山引擎的模型调用链接 | `https://ark.cn-beijing.volces.com/api/v3` |
| `LLM_ENDPOINTS.volcengine.model` | 火山引擎的模型名，详情查询火山引擎文档 | `doubao-seed-2-0-lite-260428` |
| `LLM_ENDPOINTS.volcengine.reasoning_effort` | 火山引擎模型的思考级别，详情查看火山引擎文档 | `medium` |
| `LLM_ENDPOINTS.baidu.base_url` | 飞桨星河的模型调用链接 | `"https://aistudio.baidu.com/llm/lmapi/v3"` |
| `LLM_ENDPOINTS.baidu.model` | 飞桨星河的模型名 | `ernie-5.1` |
| `LLM_ENDPOINTS.baidu.max_completion_tokens` | 飞桨星河的最大输出 token 限制 | 需要小于`65536` |
| `LLM_ENDPOINTS.baidu.enable_web_search` | 是否开启文心模型的内嵌网页搜索功能 | `true` |
| `SEARCH_CONFIG.search_depth` | tavily 搜索引擎的搜索级别参数 | `advanced` |
| `SEARCH_CONFIG.max_results` | tavily 搜索引擎的最大返回网页数 | `10` |
| `SEARCH_CONFIG.time_range` | tavily 搜索引擎的时间范围 | `year` `month` `week` `day` `none`|
| `SEARCH_CONFIG.chunks_per_source` | 每个回复的分块数 | `5` |
| `DATA_PIPELINE.input_directory` | 工作区输入路径 | `./data/input` |
| `DATA_PIPELINE.output_directory` | 工作区的结果输出路径| `./data/output` |
| `DATA_PIPELINE.checkpoint_directory` | 暂存点路径 | `"./data/checkpoints"` |
| `DATA_PIPELINE.debug_directory` | RWKV 模型的 debug 日志输出路径| `./data/debug_slm` |
| `DATA_PIPELINE.enable_debug_slm` | 是否开启 RWKV 模型的 debug 日志输出| `false` `true`|
| `DATA_PIPELINE.allowed_extensions` | 允许的输入文件类型，本项目未适配 pdf 或其他解析，建议先转换为当前可选项 | `[".txt", ".md"]` |
| `DATA_PIPELINE.max_chunk_tokens` | RWKV 模型最大输入 token 数| 任意整数（建议在 1600~2400） |
| `DATA_PIPELINE.overlap_ratio` | RWKV 模型处理时的上下文交叉比例 | 任意小数（建议 0，05） |
| `DATA_PIPELINE.reduce_group_size` | RWKV 模型二次总结合并时的批大小 | 任意整数（建议小于 4） |
| `DATA_PIPELINE.reduce_target_chunks` | | `1` |
| `DATA_PIPELINE.reduce_max_tokens` | 在 RWKV 总结/压缩次数达到上限后，由 LLM 进行总结的最大输入 | 任意整数，建议取值为 min(32k,模型最大上下文/2) |
| `DATA_PIPELINE.slm_reduce_steps` | RWKV 的最多压缩步数 | 任意整数，建议为 2 |
| `DATA_PIPELINE.llm_safe_window_tokens` | 输入给大模型的最大输入 | `60000` |
| `DATA_PIPELINE.map_focus` | 分片总结的指令 | `"保持原意压缩，提取核心逻辑，严格保留所有事实性内容"` |
| `DATA_PIPELINE.reduce_rule` | 合并总结的指令 | `"保持原意压缩，去重并合并同类逻辑，绝对保留事实性数据和原始结论"` |
| `DATA_PIPELINE.map_focus_en` | 分片总结的指令英文版 | `"Compress while maintaining original meaning, extract core logic, strictly preserve all factual content"` |
| `DATA_PIPELINE.reduce_rule_en` | 合并总结的指令英文版| `"Compress while maintaining original meaning, deduplicate and merge similar logic, absolutely preserve factual data and original conclusions"` |
| `DATA_PIPELINE.english_ratio_threshold` | 英文比例占比数大于此数字时判断为英文文档，否则为中文 | `0.5` |
| `DATA_PIPELINE.reduce_max_tokens_internal` | 合并时的最大输入数 | `3500` |
| `DATA_PIPELINE.slm_repeat_threshold` | | `5` |
| `AGENT_CONFIG.max_files_per_batch` | 每轮处理的最大文件数 | `10` |
| `AGENT_CONFIG.max_error_retries` | | `3` |
| `AGENT_CONFIG.memory_truncate_length` | | `60000` |
| `SLM_CONFIG.endpoint` | RWKV 的调用端点 | `"http://192.168.0.82:8080/v1/chat/completions"` |
| `SLM_CONFIG.password` | RWKV 的调用密码（无密码可置空） | `"rwkv7_7.2b"` |
| `SLM_CONFIG.concurrency` | RWKV 的最大并发数 | 整数，7.2B 时，24G 显存设置为 16G 为较优 |
| `TRACKING.enable` | 是否追踪日志 | `true` |
| `TRACKING.enable_slm_log` | 是否追踪 RWKV 的处理日志| `false` |
| `TRACKING.log_dir` | 日志存放路径 | `"./logs"` |
