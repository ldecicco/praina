import type { MouseEvent, ReactNode } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

type RenderMarkdownOptions = {
  onReferenceClick?: (label: string) => void;
  onTagClick?: (tag: string) => void;
  onFileClick?: (label: string) => void;
  onNoteClick?: (label: string) => void;
  onMemberClick?: (handle: string) => void;
};

function renderMath(expression: string, displayMode: boolean, key: string): ReactNode {
  try {
    const html = katex.renderToString(expression.trim(), {
      displayMode,
      throwOnError: false,
      strict: "ignore",
    });
    return <span key={key} className={displayMode ? "markdown-math-block" : "markdown-math-inline"} dangerouslySetInnerHTML={{ __html: html }} />;
  } catch {
    return <code key={key}>{displayMode ? `\\[${expression}\\]` : `$${expression}$`}</code>;
  }
}

function renderInlineText(text: string, options?: RenderMarkdownOptions): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /((?:@|%)\[([^\]]+)\]|!\[([^\]]+)\]|\[\[([^\]]+)\]\]|(^|[\s(>])@([A-Za-z0-9][A-Za-z0-9_.-]*)|(^|[\s(>])#([A-Za-z0-9][A-Za-z0-9_/-]*))/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (match[2]) {
      if (start > cursor) {
        nodes.push(text.slice(cursor, start));
      }
      const label = match[2];
      nodes.push(
        options?.onReferenceClick ? (
          <button
            key={`markdown-inline-text-${key++}`}
            type="button"
            className="mention-chip mention-chip-button"
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              options.onReferenceClick?.(label);
            }}
          >
            {label}
          </button>
        ) : (
          <span key={`markdown-inline-text-${key++}`} className="mention-chip">{label}</span>
        )
      );
      cursor = start + match[0].length;
      continue;
    }

    if (match[3]) {
      const label = match[3];
      if (start > cursor) {
        nodes.push(text.slice(cursor, start));
      }
      nodes.push(
        options?.onFileClick ? (
          <button
            key={`markdown-inline-text-${key++}`}
            type="button"
            className="mention-chip mention-chip-button"
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              options.onFileClick?.(label);
            }}
          >
            {label}
          </button>
        ) : (
          <span key={`markdown-inline-text-${key++}`} className="mention-chip">{label}</span>
        )
      );
      cursor = start + match[0].length;
      continue;
    }

    if (match[4]) {
      const label = match[4];
      if (start > cursor) {
        nodes.push(text.slice(cursor, start));
      }
      nodes.push(
        options?.onNoteClick ? (
          <button
            key={`markdown-inline-text-${key++}`}
            type="button"
            className="mention-chip mention-chip-button"
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              options.onNoteClick?.(label);
            }}
          >
            {label}
          </button>
        ) : (
          <span key={`markdown-inline-text-${key++}`} className="mention-chip">{label}</span>
        )
      );
      cursor = start + match[0].length;
      continue;
    }

    if (match[6]) {
      const prefix = match[5] || "";
      const handle = match[6] || "";
      const tokenStart = start + prefix.length;
      if (tokenStart > cursor) {
        nodes.push(text.slice(cursor, tokenStart));
      }
      nodes.push(prefix);
      nodes.push(
        options?.onMemberClick ? (
          <button
            key={`markdown-inline-text-${key++}`}
            type="button"
            className="mention-chip mention-chip-button"
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              options.onMemberClick?.(handle);
            }}
          >
            @{handle}
          </button>
        ) : (
          <span key={`markdown-inline-text-${key++}`} className="mention-chip">@{handle}</span>
        )
      );
      cursor = start + match[0].length;
      continue;
    }

    const prefix = match[7] || "";
    const tag = match[8] || "";
    const tokenStart = start + prefix.length;
    if (tokenStart > cursor) {
      nodes.push(text.slice(cursor, tokenStart));
    }
    nodes.push(prefix);
    nodes.push(
      options?.onTagClick ? (
        <button
          key={`markdown-inline-text-${key++}`}
          type="button"
          className="tag-link-button"
          onClick={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
            options.onTagClick?.(tag);
          }}
        >
          #{tag}
        </button>
      ) : (
        <span key={`markdown-inline-text-${key++}`} className="tag-link-inline">#{tag}</span>
      )
    );
    cursor = start + match[0].length;
  }
  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

function renderInlineMarkdown(text: string, options?: RenderMarkdownOptions): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /((?:@|%)\[([^\]]+)\]|!\[([^\]]+)\]|\[\[([^\]]+)\]\]|(^|[\s(>])@([A-Za-z0-9][A-Za-z0-9_.-]*)|\[([^\]]+)\]\(((?:https?:\/\/|#)[^\s)]+)\)|\[(\d+)\]|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\$([^$\n]+?)\$)/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(...renderInlineText(text.slice(cursor, start), options));
    }
    if (match[2]) {
      const label = match[2];
      nodes.push(options?.onReferenceClick ? (
        <button
          key={`markdown-inline-${key++}`}
          type="button"
          className="mention-chip mention-chip-button"
          onClick={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
            options.onReferenceClick?.(label);
          }}
        >
          {label}
        </button>
      ) : (
        <span key={`markdown-inline-${key++}`} className="mention-chip">{label}</span>
      ));
    } else if (match[3]) {
      const label = match[3];
      nodes.push(options?.onFileClick ? (
        <button
          key={`markdown-inline-${key++}`}
          type="button"
          className="mention-chip mention-chip-button"
          onClick={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
            options.onFileClick?.(label);
          }}
        >
          {label}
        </button>
      ) : (
        <span key={`markdown-inline-${key++}`} className="mention-chip">{label}</span>
      ));
    } else if (match[4]) {
      const label = match[4];
      nodes.push(options?.onNoteClick ? (
        <button
          key={`markdown-inline-${key++}`}
          type="button"
          className="mention-chip mention-chip-button"
          onClick={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
            options.onNoteClick?.(label);
          }}
        >
          {label}
        </button>
      ) : (
        <span key={`markdown-inline-${key++}`} className="mention-chip">{label}</span>
      ));
    } else if (match[6]) {
      const prefix = match[5] || "";
      const handle = match[6];
      nodes.push(prefix);
      nodes.push(options?.onMemberClick ? (
        <button
          key={`markdown-inline-${key++}`}
          type="button"
          className="mention-chip mention-chip-button"
          onClick={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
            options.onMemberClick?.(handle);
          }}
        >
          @{handle}
        </button>
      ) : (
        <span key={`markdown-inline-${key++}`} className="mention-chip">@{handle}</span>
      ));
    } else if (match[7] && match[8]) {
      const href = match[8];
      const external = /^https?:\/\//.test(href);
      nodes.push(
        <a
          key={`markdown-inline-${key++}`}
          href={href}
          target={external ? "_blank" : undefined}
          rel={external ? "noreferrer" : undefined}
        >
          {match[7]}
        </a>
      );
    } else if (match[9]) {
      nodes.push(
        <a key={`markdown-inline-${key++}`} href={`#call-citation-${match[9]}`}>
          [{match[9]}]
        </a>
      );
    } else if (match[10]) {
      nodes.push(<strong key={`markdown-inline-${key++}`}>{match[10]}</strong>);
    } else if (match[11]) {
      nodes.push(<em key={`markdown-inline-${key++}`}>{match[11]}</em>);
    } else if (match[12]) {
      nodes.push(<code key={`markdown-inline-${key++}`}>{match[12]}</code>);
    } else if (match[13]) {
      nodes.push(renderMath(match[13], false, `markdown-inline-${key++}`));
    }
    cursor = start + match[0].length;
  }
  if (cursor < text.length) {
    nodes.push(...renderInlineText(text.slice(cursor), options));
  }
  return nodes;
}

function isTableDivider(line: string): boolean {
  return /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(line);
}

function parseTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

export function renderMarkdown(content: string, options?: RenderMarkdownOptions): ReactNode[] {
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

    if (
      line.includes("|") &&
      i + 1 < lines.length &&
      isTableDivider(lines[i + 1])
    ) {
      const headers = parseTableRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        rows.push(parseTableRow(lines[i]));
        i += 1;
      }
      output.push(
        <div key={`markdown-block-${key++}`} className="markdown-table-wrap">
          <table className="markdown-table">
            <thead>
              <tr>
                {headers.map((header, index) => (
                  <th key={`markdown-th-${index}`}>{renderInlineMarkdown(header, options)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`markdown-row-${rowIndex}`}>
                  {headers.map((_, colIndex) => (
                    <td key={`markdown-cell-${rowIndex}-${colIndex}`}>
                      {renderInlineMarkdown(row[colIndex] || "", options)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (line.trim().startsWith("\\[")) {
      const mathLines: string[] = [line.trim().replace(/^\\\[\s*/, "")];
      i += 1;
      while (i < lines.length && !lines[i].trim().endsWith("\\]")) {
        mathLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) {
        mathLines.push(lines[i].trim().replace(/\s*\\\]$/, ""));
        i += 1;
      }
      output.push(renderMath(mathLines.join("\n"), true, `markdown-block-${key++}`));
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
      if (level === 1) output.push(<h1 key={`markdown-block-${key++}`}>{renderInlineMarkdown(text, options)}</h1>);
      else if (level === 2) output.push(<h2 key={`markdown-block-${key++}`}>{renderInlineMarkdown(text, options)}</h2>);
      else output.push(<h3 key={`markdown-block-${key++}`}>{renderInlineMarkdown(text, options)}</h3>);
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(<li key={`markdown-li-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^[-*]\s+/, ""), options)}</li>);
        i += 1;
      }
      output.push(<ul key={`markdown-block-${key++}`}>{items}</ul>);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(<li key={`markdown-oli-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^\d+\.\s+/, ""), options)}</li>);
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
    output.push(<p key={`markdown-block-${key++}`}>{renderInlineMarkdown(paragraphText, options)}</p>);
  }

  return output;
}
