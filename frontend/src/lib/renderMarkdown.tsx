import type { ReactNode } from "react";

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\[([^\]]+)\]\(((?:https?:\/\/|#)[^\s)]+)\)|\[(\d+)\]|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(text.slice(cursor, start));
    }
    if (match[2] && match[3]) {
      const href = match[3];
      const external = /^https?:\/\//.test(href);
      nodes.push(
        <a
          key={`markdown-inline-${key++}`}
          href={href}
          target={external ? "_blank" : undefined}
          rel={external ? "noreferrer" : undefined}
        >
          {match[2]}
        </a>
      );
    } else if (match[4]) {
      nodes.push(
        <a key={`markdown-inline-${key++}`} href={`#call-citation-${match[4]}`}>
          [{match[4]}]
        </a>
      );
    } else if (match[5]) {
      nodes.push(<strong key={`markdown-inline-${key++}`}>{match[5]}</strong>);
    } else if (match[6]) {
      nodes.push(<em key={`markdown-inline-${key++}`}>{match[6]}</em>);
    } else if (match[7]) {
      nodes.push(<code key={`markdown-inline-${key++}`}>{match[7]}</code>);
    }
    cursor = start + match[0].length;
  }
  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

export function renderMarkdown(content: string): ReactNode[] {
  const normalizedContent = content
    .replace(/\r\n/g, "\n")
    .replace(/&nbsp;/gi, " ")
    .replace(/\u00a0/g, " ");
  const lines = normalizedContent.split("\n");
  const output: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (line.trim().startsWith("```")) {
      i += 1;
      const codeLines: string[] = [];
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      output.push(
        <pre key={`markdown-block-${key++}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      if (level === 1) output.push(<h1 key={`markdown-block-${key++}`}>{renderInlineMarkdown(text)}</h1>);
      else if (level === 2) output.push(<h2 key={`markdown-block-${key++}`}>{renderInlineMarkdown(text)}</h2>);
      else output.push(<h3 key={`markdown-block-${key++}`}>{renderInlineMarkdown(text)}</h3>);
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(<li key={`markdown-li-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^[-*]\s+/, ""))}</li>);
        i += 1;
      }
      output.push(<ul key={`markdown-block-${key++}`}>{items}</ul>);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(<li key={`markdown-oli-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^\d+\.\s+/, ""))}</li>);
        i += 1;
      }
      output.push(<ol key={`markdown-block-${key++}`}>{items}</ol>);
      continue;
    }

    const paragraphLines: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith("```")
    ) {
      paragraphLines.push(lines[i]);
      i += 1;
    }
    const paragraphText = paragraphLines.join(" ").trim();
    if (!paragraphText) {
      continue;
    }
    output.push(<p key={`markdown-block-${key++}`}>{renderInlineMarkdown(paragraphText)}</p>);
  }

  return output;
}
