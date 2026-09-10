import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

/**
 * Alle Agentenausgaben sind Modelltext, kein vertrauenswürdiges HTML
 * (SECURITY.md: "HTML-Ausgabe sanitizen") - jede Textausgabe läuft
 * durch diese eine sanitizte Markdown-Komponente statt durch
 * dangerouslySetInnerHTML o.ä.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown skipHtml rehypePlugins={[rehypeSanitize]}>
      {children}
    </ReactMarkdown>
  );
}

export const safeUrl = (url: string) => (/^https?:\/\//i.test(url) ? url : undefined);
