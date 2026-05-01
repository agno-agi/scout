"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

// Wrap tables in a horizontally-scrollable container so wide markdown
// tables (e.g. Gmail digests) don't blow out the chat panel.
const components: Components = {
  table: ({ children, ...rest }) => (
    <div className="my-2 -mx-1 overflow-x-auto">
      <table {...rest} className="min-w-full">
        {children}
      </table>
    </div>
  ),
};

const PROSE_CLS = cn(
  "prose-sm max-w-none text-foreground",
  // Links
  "[&_a]:text-foreground [&_a]:underline [&_a]:decoration-foreground/30 [&_a]:underline-offset-2 hover:[&_a]:decoration-foreground",
  // Paragraphs / lists
  "[&_p]:my-1.5 [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5",
  "[&_li]:my-0.5",
  // Blockquote
  "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:not-italic [&_blockquote]:text-muted-foreground",
  // Inline code
  "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em]",
  // Code blocks
  "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0",
  // Headings
  "[&_h1]:mb-2 [&_h1]:mt-3 [&_h1]:text-base [&_h1]:font-semibold",
  "[&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-sm [&_h2]:font-semibold",
  "[&_h3]:mb-1 [&_h3]:mt-2 [&_h3]:text-sm [&_h3]:font-semibold",
  // Tables
  "[&_table]:w-full [&_table]:border-collapse [&_table]:text-xs",
  "[&_thead_th]:border-b [&_thead_th]:border-border [&_thead_th]:px-2 [&_thead_th]:py-1.5 [&_thead_th]:text-left [&_thead_th]:font-medium [&_thead_th]:text-muted-foreground",
  "[&_tbody_td]:border-b [&_tbody_td]:border-border/50 [&_tbody_td]:px-2 [&_tbody_td]:py-1.5",
  "[&_tbody_tr:last-child_td]:border-b-0",
  // Strong
  "[&_strong]:font-semibold [&_strong]:text-foreground",
);

export function Markdown({ children }: { children: string }) {
  return (
    <div className={PROSE_CLS}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
