TOOL_SCHEMAS_POOL = [
    {
        "type": "function",
        "function": {
            "name": "search_local_file",
            "description": "获取工作区资产。调用前必须先完成用户意图拆解。返回文件列表与规模估算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "检索关键词。若是泛指则传入空字符串 \"\"。"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_document_content",
            "description": "构建文件画像。对目标文件进行抽样试读，探测主题和体裁，为后续 MapReduce 策略提供情报依据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "需要试读的文件绝对路径。"}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_small_models",
            "description": "【核心执行器】将指定文件委托给多节点协同 MapReduce 引擎。该工具会自动完成双轨提取（逻辑总结 + 事实提炼），并返回给你最高1500字的详尽素材摘要。你需要记住这些内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "需要分析的文件绝对路径。"},
                    "doc_topology": {"type": "string", "enum": ["logic_tree", "time_sequence"], "description": "文档的结构特征。"},
                    "map_focus": {"type": "string", "description": "【必须项】量身定制的侧重点。"},
                    "reduce_rule": {"type": "string", "description": "【必须项】合并与去重准则。"},
                    "detail_level": {"type": "string", "description": "【必须项】目标总结字数与详细程度。"},
                    "slm_reduce_steps": {"type": "integer", "description": "小模型合并的最大步数（建议 1~5）。"},
                    "target_token_limit": {"type": "integer", "description": "后台深压的目标 Token 数（所有文件总和不超过32000）。"}
                },
                "required": ["file_path", "doc_topology", "map_focus", "reduce_rule", "detail_level", "slm_reduce_steps", "target_token_limit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_report_to_md",
            "description": "终局生成工具。底层工具不再自动拼接数据，你需要基于之前获取的所有文件素材，亲自撰写完整的最终 Markdown 报告传入此工具以保存。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string", 
                        "description": "输出的 Markdown 文件名，如 final_analysis.md"
                    },
                    "full_report_content": {
                        "description": "由你亲自撰写的【完整且详尽的最终报告】。必须包含跨文件总结与单文件核心提炼。🚨绝对红线：纯干货输出，禁止在文中添加“报告生成时间”、“免责声明”、“前言语”、“总结语”等任何边角料元数据，直接输出报告正文内容。"
                    }
                },
                "required": ["file_name", "full_report_content"]
            }
        }
    }
]