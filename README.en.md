# RWKV-ECRA

Language: [中文](README.md) | English

Example output: [TileLang Deep Technical Analysis Report](data/output/TileLang_Deep_Analysis.md)

RWKV-ECRA is an edge-cloud collaborative long-document analysis agent:

- With an edge-cloud collaboration approach, it is estimated to analyze tens of millions of tokens per hour while saving more than 80% of tokens.

- A large model is responsible for understanding the task, planning steps, calling tools, and writing the final report.

- The latest RWKV-7 7.2B model, which can reach 10,000+ tokens/s on a single RTX 5090, is used to read long documents in chunks, extract facts, compress summaries, and generate intermediate materials.

- The goal of this project is not to make a single model swallow the entire context at once. Instead, it decomposes long-document analysis into traceable, recoverable, and scalable collaboration nodes, then generates an in-depth cross-file analysis report.

Core capabilities in the current version:

- Scan local documents under `data/input`; `.txt` and `.md` files are currently supported.
- Sample and preview documents to first determine their topic, genre, and analysis strategy.
- Split long documents into semantic chunks and delegate them to small models for batch parallel processing.
- Use a dual-track Summary + Facts extraction flow: one track handles logical summarization, while the other preserves key facts.
- Use a Reduce step to progressively compress and merge chunk materials.
- Let the large model fuse all intermediate materials and write the final Markdown report itself.
- Support intermediate-result checkpoints, runtime logs, and small-model call logs for recovery and troubleshooting.

## Usage

### 1. Prepare the Environment

Python 3.10 or newer is recommended.

Install the basic dependencies required by the current code:

```bash
pip install openai requests tiktoken
```

The project uses the following by default:

- Small model: a local RWKV model. For configuration and usage, see the [RWKV Chinese official high-concurrency inference tutorial](https://www.rwkv.cn/tutorials/intermediate/rwkv_lightning). Configuration lives in `SLM_CONFIG` in `config.py`.
- Large model: a Baidu AI Studio endpoint compatible with the OpenAI SDK. Configuration is in `clients/llm_client.py` and `config.py`. To use it, obtain a key from the [PaddlePaddle AI Studio platform](https://aistudio.baidu.com/account/accessToken).

Why use ERNIE here? Because web search is not configured in this setup, so a Wenxin 5.1 model with built-in web search was used to make it easier to test future collaboration features such as deep research.

Before running, confirm that:

1. `API_KEYS["baidu"]` in `config.py` has been replaced with a usable key.
2. The local small-model service has started, and its endpoint and password match `SLM_CONFIG`.
3. The files to be analyzed have been placed in the `data/input` directory.

### 2. Add Input Files

Place the `.md` or `.txt` files to be analyzed in:

```text
data/input/
```

If multiple files need to be analyzed, the agent first scans the file list, then previews and delegates analysis file by file. Finally, it performs cross-file relational analysis in the overall report.

### 3. Modify the Task Instruction

The current entry point is `main.py`. You can modify the `query` inside it to change the task goal, for example:

```python
query = "帮我深度分析 tilelang 这篇文章，并给出跨文件关联分析。"
```

### 4. Run the Project

```bash
python main.py
```

After running, the project automatically creates input, output, and related directories, then executes the full analysis workflow.

The final report is written to:

```text
data/output/
```

Runtime logs are written to:

```text
logs/
```

Intermediate checkpoints are written to:

```text
data/checkpoints/
```

After the task is complete, the current implementation clears checkpoints. If a task is interrupted, the next startup detects checkpoints and attempts to reuse existing intermediate results.

## Project Design Logic

The design logic of this project is to keep the main workflow stable while adding or adjusting collaboration mechanisms at each node, using collaboration to improve the effect of the current node. Future versions can add iterative checks, quality evaluation, reflection, correction, and similar mechanisms, but the current version focuses on the core structure first.

The main workflow can be understood as:

```text
Understand user intent
  -> Inventory local files
  -> Sample-preview files and build file profiles
  -> Develop an analysis strategy
  -> Delegate MapReduce processing to small models
  -> Fuse materials with the large model and write the final report
  -> Export Markdown
```

### 1. The Large Model Orchestrates the Main Flow

`Orchestrator` in `agent/orchestrator.py` is the main control entry point. It does not directly read and summarize all documents. Instead, it advances the task through tool calls:

- `search_local_file`: scans the input directory and obtains the list of processable files.
- `preview_document_content`: samples and previews a single file to help judge document structure and priorities.
- `delegate_to_small_models`: delegates long-document processing tasks to the small-model collaboration engine.
- `export_report_to_md`: saves the final report written by the large model itself.

The large model handles "planning" here: understanding the requirement, selecting tools, deciding the processing strategy for each file, and finally reorganizing scattered materials into a coherent report.

### 2. Small Models Handle Local High-Concurrency Processing

`delegate_to_small_models` in `tools/local_data_processor.py` is the core of the current collaboration structure. It splits long documents into multiple chunks, then launches two types of tasks for each chunk at the same time:

- Summary track: extracts the logic, structure, and topic of the chunk.
- Facts track: extracts key facts, data, terms, and explicit conclusions.

This enables high-quality summarization while preserving the precision of fact extraction.

### 3. Reduce Handles Compression and Merging

When there are many chunks, chunk summaries continue into the Reduce stage. Reduce groups materials by token count and progressively merges multiple local summaries into shorter, more focused materials.

The goal of this stage is not to generate the final article. Instead, it compresses "small-model local reading results" into "intermediate materials that the large model can absorb." The final expression is still left to the large model.

### 4. Checkpoints and Logs Make the Process Traceable

The project includes two types of auxiliary mechanisms:

- `utils/checkpoint.py`: caches completed file-level analysis results to reduce repeated computation after interruptions.
- `utils/tracker.py`: records large-model decisions, small-model inputs and outputs, and tool execution results for debugging and review.

These mechanisms are not the main workflow itself, but they make the collaboration process more robust: failures can be recovered, results can be observed, and problems can be located.

### 5. Future Extension Directions

For now, the core structure is kept simple. Future work can continue extending the system without breaking the main workflow:

- Build a usable frontend, since changing prompts directly in code is too crude.
- Add a strategy check after previewing to determine whether the analysis focus needs to be selected again.
- Add a quality check after MapReduce to rerun local nodes when empty summaries, hallucinations, or insufficient facts are detected.
- Add a cross-file check before the final report to specifically verify whether cross-file associations are sufficient.
- Introduce PaddleOCR-VL or other vision-language OCR models to handle "arbitrary files."
- Add more collaboration roles at individual nodes, keeping the main workflow stable while optimizing each node step by step.
