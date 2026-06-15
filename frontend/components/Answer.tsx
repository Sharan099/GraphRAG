import React from "react";

/**
 * Minimal, dependency-free markdown renderer tuned for the answer format the
 * backend returns (headings, bold, inline code, ordered/unordered lists).
 */

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // Split on **bold** and `code` while keeping the delimiters.
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  tokens.forEach((tok, i) => {
    if (!tok) return;
    if (tok.startsWith("**") && tok.endsWith("**")) {
      nodes.push(<strong key={`${keyBase}-b-${i}`}>{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("`") && tok.endsWith("`")) {
      nodes.push(<code key={`${keyBase}-c-${i}`}>{tok.slice(1, -1)}</code>);
    } else {
      nodes.push(<React.Fragment key={`${keyBase}-t-${i}`}>{tok}</React.Fragment>);
    }
  });
  return nodes;
}

export default function Answer({ text }: { text: string }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];

  let list: { ordered: boolean; items: string[] } | null = null;

  const flushList = (key: string) => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={key}>
        {list.items.map((it, i) => (
          <li key={`${key}-li-${i}`}>{renderInline(it, `${key}-${i}`)}</li>
        ))}
      </Tag>
    );
    list = null;
  };

  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    const key = `b-${idx}`;

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);

    if (heading) {
      flushList(`${key}-fl`);
      const level = Math.min(heading[1].length + 1, 4);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      blocks.push(<Tag key={key}>{renderInline(heading[2], key)}</Tag>);
      return;
    }

    if (ul) {
      if (!list || list.ordered) {
        flushList(`${key}-fl`);
        list = { ordered: false, items: [] };
      }
      list.items.push(ul[1]);
      return;
    }

    if (ol) {
      if (!list || !list.ordered) {
        flushList(`${key}-fl`);
        list = { ordered: true, items: [] };
      }
      list.items.push(ol[1]);
      return;
    }

    flushList(`${key}-fl`);

    if (line.trim() === "") {
      return;
    }

    blocks.push(<p key={key}>{renderInline(line, key)}</p>);
  });

  flushList("b-final");

  return <div className="answer text-[0.92rem] text-frost/90">{blocks}</div>;
}
