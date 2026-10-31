import { createElement, Fragment, type ReactNode } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

function reactNode(node: Node, key: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent;
  if (!(node instanceof Element)) return null;
  const tag = node.tagName.toLowerCase();
  const children = Array.from(node.childNodes).map((child, index) => reactNode(child, `${key}-${index}`));
  const allowed = new Set(['p', 'strong', 'em', 'ul', 'ol', 'li', 'h3', 'blockquote', 'code', 'a', 'br']);
  if (!allowed.has(tag)) return createElement(Fragment, { key }, ...children);
  const props = tag === 'a' ? { key, href: node.getAttribute('href') ?? '#', rel: 'noreferrer' } : { key };
  return createElement(tag, props, ...children);
}

export function Markdown({ text }: { text: string }) {
  const fragment = DOMPurify.sanitize(marked.parse(text, { async: false, breaks: true }), {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ['img', 'iframe', 'form', 'style', 'script'],
    FORBID_ATTR: ['style'],
  });
  return (
    <div className="markdown">
      {Array.from(fragment.childNodes).map((node, index) => reactNode(node, String(index)))}
    </div>
  );
}
