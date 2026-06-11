// RWKV-ECRA/frontend/src/markdown.js
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function renderMarkdown(markdown) {
  let text = String(markdown || "");
  
  // 🔴 核心修复：强制处理 Markdown 粗体与中文全角标点连用时不渲染的问题
  // 例如：将 **“资本层面的控制关系”** 提前转换为 <strong>“资本层面的控制关系”</strong>
  text = text.replace(/\*\*([^\n]+?)\*\*/g, '<strong>$1</strong>');
  
  // 预处理角标，将其转换为漂亮的、可点击跳转的 HTML
  // 处理网络事实角标 ^[1]^
  text = text.replace(/\^\[(\d+)\]\^/g, '<a href="#source-$1" class="citation-badge web" title="跳转至网络引用来源"><span>[$1]</span></a>');
  
  // 处理本地文档角标 ^{1}^
  text = text.replace(/\^\{(\d+)\}\^/g, '<a href="#source-$1" class="citation-badge local" title="跳转至本地文档来源"><span>[$1]</span></a>');

  const html = marked.parse(text);
  // DOMPurify 默认允许 <a> 和 <strong> 等安全标签属性
  return DOMPurify.sanitize(html);
}

export function reportToMarkdown(report) {
  if (!report) return "";
  if (report.nodes?.length) {
    return report.nodes.map((node) => `## ${node.title}\n\n${node.content}`).join("\n\n");
  }
  return report.markdown || "";
}

export function extractMarkdownOutline(markdown) {
  return String(markdown || "")
    .split("\n")
    .map((line) => /^(#{1,3})\s+(.+)$/.exec(line.trim()))
    .filter(Boolean)
    .slice(0, 30)
    .map((match, index) => ({ id: `md-heading-${index}`, title: match[2] }));
}