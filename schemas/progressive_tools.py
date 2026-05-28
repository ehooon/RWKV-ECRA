# RWKV-ECRA/schemas/progressive_tools.py

# 阶段 1：探索发现 (找文件、读前言)
DISCOVERY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_local_file",
            "description": "基于关键词搜索沙盒文件。如果用户没提具体名字，可传空字符串全量查询。",
            "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_document_content",
            "description": "静态提取文件的前800字预览，不消耗大模型算力，用于快速确认文件内容。",
            "parameters": {"type": "object", "properties": {"file_ids": {"type": "array", "items": {"type": "string"}}}}
        }
    }
]

# 阶段 2：提取与记忆 (提炼、问答)
EXTRACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to_small_models",
            "description": "调用底层SLM对长文本进行MapReduce全文提炼，并写入工作记忆区。",
            "parameters": {"type": "object", "properties": {"file_ids": {"type": "array", "items": {"type": "string"}}}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_checkpoint_via_slm",
            "description": "在已提炼的工作记忆或缓存中进行捞针问答。",
            "parameters": {"type": "object", "properties": {"file_ids": {"type": "array", "items": {"type": "string"}}, "query_instruction": {"type": "string", "description": "捞针问题"}}}
        }
    }
]

# 阶段 3：聚合与输出 (写报告、结束)
SYNTHESIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "batch_process_individual_reports",
            "description": "基于已有的记忆提取结果，生成单篇标准化分类报告。",
            "parameters": {"type": "object", "properties": {"file_ids": {"type": "array", "items": {"type": "string"}}}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_final_aggregate_reports",
            "description": "当有多篇报告存在时，进行跨域聚合分析。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "认为用户所有的目标已经完全达成，退出系统。",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

TOOL_GROUPS = {
    "DISCOVERY": DISCOVERY_TOOLS,
    "EXTRACTION": EXTRACTION_TOOLS,
    "SYNTHESIS": SYNTHESIS_TOOLS
}