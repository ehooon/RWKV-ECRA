from tools.local_data_processor import (
    search_local_file, 
    delegate_to_small_models, 
    preview_document_content, 
    export_report_to_md
)

TOOL_REGISTRY = {
    "search_local_file": search_local_file,
    "preview_document_content": preview_document_content,
    "delegate_to_small_models": delegate_to_small_models,
    "export_report_to_md": export_report_to_md
}