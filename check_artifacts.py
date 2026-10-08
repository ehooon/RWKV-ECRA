# RWKV-ECRA/check_artifacts.py
# 产物客观属性检查:对 data/output/TASK_* 的三件套做程序化校验,不依赖模型判断。
# 用法: .venv/bin/python check_artifacts.py [task_dir ...]   (缺省检查所有 TASK_*)
import json
import os
import re
import sys

TERMINAL_PUNCT = tuple("。！？!?.…”\"」』)】]|")
GHOST_PATTERNS = {
    "论文内部编号^{[N]}": re.compile(r"\^?\{\[[^\}]*\}\^?"),
    "裸[N]引用": re.compile(r"(?<![!\[\]\^])\[\d{1,3}(?:\]\s*\[\d{1,3})*\](?![\]\(\]\^])"),
    "哈希残码$^{hash}$": re.compile(r"\$\^\{[0-9a-zA-Z]{4,8}\}\$"),
    "角标粘连^][^": re.compile(r"\]\s*\[\^"),
}
CITE_RE = re.compile(r"\^[\{\[]?(\d{1,3})[\}\]]?\^")


def check_task(task_dir: str) -> dict:
    tid = os.path.basename(task_dir.rstrip("/"))
    files = {f: os.path.join(task_dir, f) for f in os.listdir(task_dir)}
    f01 = next((p for k, p in files.items() if k.endswith("_01_原生初稿版.md")), None)
    f02 = next((p for k, p in files.items() if k.endswith("_02_深度排版溯源版.md")), None)
    f03 = next((p for k, p in files.items() if k.endswith("_03_结构化溯源数据.jsonl")), None)

    r = {"task": tid, "errors": [], "warns": []}
    for label, p in [("_01", f01), ("_02", f02), ("_03", f03)]:
        if not p:
            r["errors"].append(f"缺少 {label} 文件")
        elif os.path.getsize(p) == 0:
            r["errors"].append(f"{label} 文件为 0 字节")
    if r["errors"]:
        return r

    md = open(f02, encoding="utf-8").read()
    draft = open(f01, encoding="utf-8").read()
    r["len_01_chars"] = len(draft)
    r["len_02_chars"] = len(md)
    r["sections"] = len(re.findall(r"^## ", md, flags=re.M))

    # ---- jsonl 解析 ----
    nodes, cmap = [], []
    for line in open(f03, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            r["errors"].append("jsonl 存在无法解析的行")
            continue
        if rec.get("record_type") == "report_node":
            nodes.append(rec)
        elif rec.get("record_type") == "global_citation_map":
            cmap = rec.get("data", [])
    r["nodes"] = len(nodes)
    r["nodes_failed"] = sum(1 for n in nodes if n.get("failed"))
    r["map_entries"] = len(cmap)

    # ---- 截断检测:剥掉结尾的角标后,节点内容须以终止标点收尾 ----
    trailing_cites = re.compile(r"(\s*\^[\{\[]?\d{1,3}[\}\]]?\^)+\s*$")
    truncated = []
    for n in nodes:
        tail = trailing_cites.sub("", (n.get("content") or "").rstrip())
        if tail and not tail.endswith(TERMINAL_PUNCT):
            truncated.append((n.get("node_id"), tail[-12:]))
    r["truncated_nodes"] = truncated

    # ---- 角标闭环:正文角标 ⊆ 索引 ----
    valid_idx = {x.get("index") for x in cmap}
    cited = {int(m) for m in CITE_RE.findall(md)}
    r["cited_indices"] = sorted(cited)
    r["cited_not_in_map"] = sorted(cited - valid_idx)
    r["map_never_cited"] = sorted(valid_idx - cited)

    # ---- 幽灵角标/格式残留 ----
    r["ghosts"] = {name: len(p.findall(md)) for name, p in GHOST_PATTERNS.items()}
    r["ghosts"] = {k: v for k, v in r["ghosts"].items() if v}

    # ---- 来源去重与类型(同一 URL 被多条索引正确引用不算缺陷,仅统计) ----
    urls = [x.get("url") for x in cmap]
    r["dup_urls"] = len(urls) - len(set(urls))
    r["src_types"] = {t: sum(1 for x in cmap if x.get("type") == t) for t in {x.get("type") for x in cmap}}

    # ---- 节点 sources 与正文引用一致性 ----
    mismatch = []
    for n in nodes:
        body = n.get("content") or ""
        ncites = {int(m) for m in CITE_RE.findall(body)}
        nsrcs = {s.get("index") for s in (n.get("matched_sources") or n.get("sources") or [])}
        if ncites - nsrcs:
            mismatch.append((n.get("node_id"), sorted(ncites - nsrcs)))
    r["node_cite_not_in_sources"] = mismatch

    # ---- LLM 元回复残留 ----
    r["meta_reply"] = bool(re.search(r"好的[,,，][^。\n]{0,30}(要求|您)|作为AI|作为一个人工智能", md))

    return r


def render(r: dict) -> str:
    lines = [f"\n=== {r['task']} ==="]
    if r["errors"]:
        return lines[0] + "\n  ❌ " + "; ".join(r["errors"])
    lines.append(f"  长度: _01={r['len_01_chars']} 字符, _02={r['len_02_chars']} 字符, 分节={r['sections']}, 节点={r['nodes']} (failed={r['nodes_failed']})")
    lines.append(f"  索引: {r['map_entries']} 条 {r['src_types']}, 重复URL={r['dup_urls']}")
    lines.append(f"  角标: 引用{r['cited_indices']}, 不在索引={r['cited_not_in_map'] or '无'}, 索引未引用={r['map_never_cited'] or '无'}")
    lines.append(f"  截断节点: {r['truncated_nodes'] or '无'}")
    lines.append(f"  幽灵角标: {r['ghosts'] or '无'}")
    lines.append(f"  节点sources缺引用: {r['node_cite_not_in_sources'] or '无'}")
    lines.append(f"  元回复残留: {'有' if r['meta_reply'] else '无'}")

    verdict = "✅ PASS"
    if r["cited_not_in_map"] or r["truncated_nodes"] or r["nodes_failed"] or r["meta_reply"]:
        verdict = "❌ FAIL"
    elif r["ghosts"] or r["node_cite_not_in_sources"]:
        verdict = "⚠️ PASS(有瑕疵)"
    lines.append(f"  判定: {verdict}")
    return "\n".join(lines)


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "data/output")
    dirs = sys.argv[1:] or sorted(
        (os.path.join(out_dir, d) for d in os.listdir(out_dir) if d.startswith("TASK_")),
        key=os.path.getmtime,
    )
    for d in dirs:
        print(render(check_task(d)))
