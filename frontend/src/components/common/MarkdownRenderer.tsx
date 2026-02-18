import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  securityLevel: 'strict',
  fontFamily: 'inherit',
});

let mermaidCounter = 0;

function MermaidBlock({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${++mermaidCounter}`;
    mermaid
      .render(id, chart)
      .then(({ svg: rendered }) => {
        if (!cancelled) setSvg(rendered);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (error) {
    return (
      <pre className="p-4 bg-red-50 text-red-700 rounded-lg text-sm overflow-x-auto">
        {error}
      </pre>
    );
  }

  return (
    <div
      ref={ref}
      className="my-4 flex justify-center overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

/** Parse bm:// links and return { type, id } or null for regular links. */
function parseBmLink(href: string | undefined): { type: 'node' | 'task'; id: string } | null {
  if (!href) return null;
  const match = href.match(/^bm:\/\/(node|task)\/([a-f0-9-]+)$/i);
  if (!match) return null;
  return { type: match[1] as 'node' | 'task', id: match[2] };
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold text-text mt-8 mb-4 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-semibold text-text mt-8 mb-3 pb-2 border-b border-border">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-semibold text-text mt-6 mb-2">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-base font-semibold text-text mt-4 mb-2">{children}</h4>
  ),
  p: ({ children }) => <p className="text-sm text-text-secondary leading-relaxed mb-4">{children}</p>,
  a: ({ href, children }) => {
    const bm = parseBmLink(href);
    if (bm) {
      return (
        <button
          type="button"
          data-bm-type={bm.type}
          data-bm-id={bm.id}
          className="text-primary-600 hover:text-primary-700 underline cursor-pointer inline font-medium"
        >
          {children}
        </button>
      );
    }
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary-600 hover:text-primary-700 underline"
      >
        {children}
      </a>
    );
  },
  ul: ({ children }) => <ul className="list-disc list-inside mb-4 space-y-1 text-sm text-text-secondary">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside mb-4 space-y-1 text-sm text-text-secondary">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-primary-300 pl-4 my-4 text-sm text-text-secondary italic">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-4">
      <table className="min-w-full text-sm border border-border rounded-lg">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
  th: ({ children }) => (
    <th className="px-3 py-2 text-left text-xs font-semibold text-text border-b border-border">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 text-sm text-text-secondary border-b border-border">{children}</td>
  ),
  code: ({ className, children, ...props }) => {
    const match = /language-(\w+)/.exec(className || '');
    const language = match?.[1];

    if (language === 'mermaid') {
      return <MermaidBlock chart={String(children).trim()} />;
    }

    // Inline code vs block code
    const isInline = !className;
    if (isInline) {
      return (
        <code className="px-1.5 py-0.5 bg-gray-100 text-primary-700 rounded text-xs font-mono" {...props}>
          {children}
        </code>
      );
    }

    return (
      <code className={`block text-xs font-mono ${className || ''}`} {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => {
    // Check if the child is a MermaidBlock — if so don't wrap in <pre>
    const child = children as ReactNode;
    if (
      child &&
      typeof child === 'object' &&
      'type' in (child as unknown as Record<string, unknown>) &&
      (child as unknown as { type: unknown }).type === MermaidBlock
    ) {
      return <>{children}</>;
    }
    return (
      <pre className="p-4 bg-gray-50 rounded-lg overflow-x-auto mb-4 border border-border">
        {children}
      </pre>
    );
  },
  hr: () => <hr className="my-6 border-border" />,
  strong: ({ children }) => <strong className="font-semibold text-text">{children}</strong>,
};

interface MarkdownRendererProps {
  content: string;
  onBmLink?: (type: 'node' | 'task', id: string) => void;
}

export function MarkdownRenderer({ content, onBmLink }: MarkdownRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!onBmLink) return;
      const target = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-bm-type]');
      if (!target) return;
      const type = target.dataset.bmType as 'node' | 'task';
      const id = target.dataset.bmId;
      if (type && id) {
        e.preventDefault();
        onBmLink(type, id);
      }
    },
    [onBmLink],
  );

  return (
    <div ref={containerRef} onClick={handleClick}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
