import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

type Solution = {name:string; interesting:string; reusable:string; fit:string; constraint:string; source_urls:string[]};
type Source = {id:string; url:string; title:string; finding:string; relevance:number|null; confidence:number|null; license_info:string|null; retrieved_at:string; provider:string};
type Research = {solutions:Solution[]; best_practices:string[]; open_source_potential:string; conclusion:string; sources:Source[]};

const Markdown = ({children}:{children:string}) => <ReactMarkdown skipHtml rehypePlugins={[rehypeSanitize]}>{children}</ReactMarkdown>;
const safeUrl = (url:string) => /^https?:\/\//i.test(url) ? url : undefined;

export function ResearchPanel({projectId}:{projectId:string}) {
  const [research, setResearch] = useState<Research|null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch(`/api/projects/${encodeURIComponent(projectId)}`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(data => setResearch(data.research))
      .catch(e => setError(String(e)));
  }, [projectId]);
  if (error) return <p role="alert">Recherche konnte nicht geladen werden: {error}</p>;
  if (!research) return <p>Recherche läuft oder liegt noch nicht vor.</p>;
  return <main>
    <h1>Recherche</h1>
    <section className="cards">{research.solutions.map(s => <article key={s.name}>
      <h2>{s.name} <small>{s.fit}</small></h2>
      <Markdown>{s.interesting}</Markdown><strong>Wiederverwendbar</strong><Markdown>{s.reusable}</Markdown>
      <strong>Einschränkung</strong><Markdown>{s.constraint}</Markdown>
    </article>)}</section>
    <h2>Best Practices</h2><ul>{research.best_practices.map(x => <li key={x}><Markdown>{x}</Markdown></li>)}</ul>
    <h2>Open-Source-Potenzial</h2><Markdown>{research.open_source_potential}</Markdown>
    <h2>Fazit</h2><Markdown>{research.conclusion}</Markdown>
    <h2>Quellen</h2><ol>{research.sources.map(s => <li key={s.id}>
      <a href={safeUrl(s.url)} target="_blank" rel="noreferrer">{s.title}</a>
      {s.license_info && <> · Lizenz: {s.license_info}</>}
      <Markdown>{s.finding}</Markdown><small>Abruf: {new Date(s.retrieved_at).toLocaleString()} · {s.provider}</small>
    </li>)}</ol>
  </main>;
}
