# ADR-003 — Vorbereitung: Research-/Retrieval-Provider für V1

**Status dieses Dokuments:** Entscheidungsgrundlage, KEINE Entscheidung. `DECISIONS.md` ADR-003 bleibt `OPEN`, bis ihr gemeinsam entscheidet. Keine Änderung an `MASTER_PLAN_v0.2.md`, `WORKFLOW_STATES.md` oder `DECISIONS.md` in diesem Schritt.

## Architektur-Rahmen (bestätigt eure eigene Skizze)

Die im Chat skizzierte Trennung deckt sich mit der bereits in `MASTER_PLAN_v0.2.md` Abschnitt 21 festgelegten Abstraktion (`research(query, requirements, source_policy)`):

```
Research Agent
      │
      ▼
Research Provider Interface  (bereits spezifiziert, Abschnitt 21)
      │
 ┌────┼──────────┐
 ▼    ▼          ▼
Web   Search     Repository/
Fetch Provider   Docs Sources
```

ADR-003 entscheidet **nur**, welcher konkrete Provider (bzw. welche Kombination) für V1 hinter dieser Schnittstelle steckt — nicht die Schnittstelle selbst. Ein Providerwechsel später darf laut Abschnitt 21 keine Änderung am Research Agent oder an nachgelagerten Agenten erfordern.

## Zentrale Vorfrage: Search und Fetch getrennt oder gebündelt?

Zwei Architekturmuster stehen zur Wahl:

* **Gebündelt:** Ein Anbieter liefert in einem API-Call bereits Suchergebnis **und** aufbereiteten Volltext (z. B. Tavily, Exa). Weniger Integrationsaufwand, aber der Anbieter entscheidet, wie der Seiteninhalt aufbereitet wird.
* **Getrennt:** Ein Suchindex-Anbieter liefert nur URLs/Snippets, ein zweiter, unabhängiger Fetch-Dienst holt und bereinigt den Volltext (z. B. Brave Search + Jina Reader/Firecrawl). Mehr Integrationsaufwand, aber beide Bausteine sind unabhängig austauschbar — passt am ehesten zu Leitprinzip „Provider austauschbar" (Abschnitt 20/21) und reduziert Lock-in auf zwei kleinere statt einer großen Abhängigkeit.

Das ist keine reine Geschmacksfrage — sie bestimmt, wie viele der Kriterien unten pro Kandidat überhaupt gemeinsam optimiert werden können.

## Kandidaten

### 1. Tavily (Search + Extract, LLM-nativ)

Speziell für LLM-Agenten und RAG-Pipelines gebaut. Liefert bereits aufbereitete, strukturierte Snippets statt Roh-HTML; „Search" und „Extract" (Content-Fetch) sind zwei Endpunkte derselben API, aber unabhängig aufrufbar.

* Preis: Free Tier 1.000 Credits/Monat; danach ab 30 $/Monat (4.000 Credits) bzw. Pay-as-you-go 0,008 $/Credit; Volumenrabatt bei 100.000 Credits/Monat auf 0,005 $/Credit. Eine einfache Suche kostet 1 Credit, eine erweiterte 2 Credits.
* Referenzintegration in Agenten-Frameworks (u. a. LangChain) — spricht für unkomplizierte Anbindung.

### 2. Exa (Neural Search + Contents API)

Semantische und Keyword-Suche, explizit für LLM-/Agenten-Konsum optimiert, mit eigener „Code"-Suchvertikale für GitHub/Repositories. Liefert Relevanz-Scores, Autoren, Veröffentlichungsdatum; Contents-Endpunkt trennbar von der Suche.

* Preis: Search+Contents 7 $/1.000 Requests (10 Ergebnisse inkl. Text/Highlights); zusätzliche Ergebnisse 1 $/1.000; reiner Contents-Abruf 1 $/1.000 Seiten je Content-Typ. Free Tier 1.000 Requests/Monat, danach nutzungsbasiert.
* Stärke laut eigener Positionierung: technische/Code-/Repository-Recherche — passt gut zum Bedarf aus Abschnitt 8 („offizielle Repositories", „Open-Source-Potenzial").

### 3. Brave Search API (unabhängiger Index) + Jina Reader (Content-Fetch)

Zwei getrennte, unabhängig ersetzbare Bausteine. Brave betreibt einen der drei global-skalierten, von Google/Bing unabhängigen Web-Indizes — relevant für „aktuelle Informationen" ohne Umweg über einen fremden Suchindex. Jina Reader (`r.jina.ai`) wandelt beliebige URLs in sauberes Markdown um, nutzbar ohne API-Key im Low-Rate-Modus oder mit Key für Produktivbetrieb.

* Preis Brave: Search-Plan 5 $/1.000 Requests, 50 QPS Rate Limit auf dem Such-Endpunkt; Free-Plan 2.000 Anfragen/Monat bei 1 QPS.
* Preis Jina Reader: tokenbasiert (0,045–0,050 $ pro 1 Mio. Tokens), 10 Mio. Freitokens je neuem API-Key.
* Trade-off: zwei Anbieter, zwei Rechnungen, zwei Ausfallpunkte — dafür geringster Lock-in pro einzelnem Baustein und freie Kombinierbarkeit (z. B. Brave für Suche + Firecrawl statt Jina für Fetch, ohne die Suchseite anzufassen).

### 4. Anthropics natives Web-Search-Server-Tool (`web_search`)

Ein von Anthropic gehosteter Such- und Fetch-Mechanismus, der direkt als Tool in einem Claude-Modellaufruf deklariert wird (kein separater API-Key/Provider-Vertrag nötig, sofern OpenClaw ohnehin Claude-Modelle für die Agenten aufruft).

* Vorteil: null zusätzlicher Integrationsaufwand, keine weitere Rechnung, keine weitere Rate-Limit-Quelle zu verwalten.
* **Entscheidender Nachteil für diese Rolle:** Das Tool ist an den Modellanbieter gekoppelt, der den jeweiligen Agentenaufruf ausführt. Abschnitt 21 des Plans verlangt aber ausdrücklich eine von Modell-/Provider-Wahl unabhängige `research()`-Schnittstelle (Abschnitt 20: „Agenten dürfen nicht hart an einen einzigen Modellanbieter gekoppelt werden"). Dieses Tool direkt als `research()`-Implementierung zu verwenden, würde genau diese Trennung aufheben — der Research Agent wäre nicht mehr unabhängig vom für ihn gewählten `call_model`-Provider austauschbar.
* Realistische Rolle daher eher: eine mögliche **Implementierung eines Adapters** hinter der Schnittstelle (falls OpenClaw sowieso Claude aufruft), nicht die Schnittstelle selbst — sollte nicht ADR-003 als alleinige Lösung entscheiden, sondern höchstens als zusätzliche Option neben einem swap-baren Adapter stehen.

## Kriterienvergleich

| Kriterium (Gewicht) | Tavily | Exa | Brave + Jina | Anthropic web_search |
|---|---|---|---|---|
| Websuche-Qualität (sehr hoch) | Gut, LLM-optimiert aufbereitet | Sehr gut für semantisch/technisch, weniger breite Web-Abdeckung als klassischer Index | Gut, echter unabhängiger Web-Index | Gut (Anbieter des zugrunde liegenden Index nicht dokumentiert offengelegt) |
| Quellen/zitierbare URLs (sehr hoch) | Ja, URLs im Ergebnis | Ja, plus Autor/Datum/Relevanz-Score | Ja, klassisches Suchergebnisformat | Ja, Ergebnisse enthalten URLs |
| Aktuelle Informationen (sehr hoch) | Laufender Such-Crawl | Laufender Such-Crawl | Eigener Index, >100 Mio. Seiten-Updates/Tag | Laufender Such-Crawl |
| Technische Doku/GitHub auffindbar (hoch) | Allgemein gut | **Eigene Code-/Repository-Suchvertikale** — stärkster Kandidat hier | Gut über allgemeinen Index, kein Spezialfokus | Gut über allgemeinen Index, kein Spezialfokus |
| API-Einfachheit (hoch) | Sehr hoch, ein Endpunkt für Search+Extract | Hoch, SDKs für Python/JS, MCP-Server vorhanden | Mittel — zwei Anbieter zu integrieren statt einem | Sehr hoch, wenn OpenClaw ohnehin Claude aufruft — sonst nicht anwendbar |
| Kosten (hoch) | Günstig im Einstieg (0,005–0,008 $/Credit), gut planbar | Vergleichbar bis etwas teurer bei vollem Contents-Abruf (7 $/1.000) | Günstig (5 $/1.000 Brave + geringe Jina-Tokenkosten), aber zwei Rechnungen | Bisher keine gesondert dokumentierte Zusatzgebühr recherchiert — Kostenmodell unklar, vor Entscheidung verifizieren |
| Rate Limits (mittel) | Nutzungsbasiert, kein hartes QPS-Limit dokumentiert | Nutzungsbasiert | Brave: 50 QPS (bezahlt) / 1 QPS (Free) — dokumentiert und vorhersehbar | Modellanbieter-seitig, nicht separat dokumentiert |
| Strukturierte Ergebnisse (hoch) | Ja, explizit für Agenten designt | Ja, inkl. Relevanz-Score/Metadaten | Teilweise — Brave strukturiert, Jina liefert Markdown (weniger strukturiert) | Ja, als Tool-Result-Block |
| OpenClaw-Integration (hoch) | Einfach: ein REST-Call | Einfach: ein REST-Call, zusätzlich offizieller MCP-Server vorhanden | Mittel: zwei REST-Calls zu orchestrieren | Am einfachsten, aber siehe Lock-in-Einwand oben |
| Provider-Lock-in (mittel) | Ein Anbieter für Search+Fetch | Ein Anbieter für Search+Fetch | Geringer — zwei kleine, unabhängig ersetzbare Bausteine | **Hoch** — an den Modellanbieter des jeweiligen Agentenaufrufs gekoppelt, widerspricht Abschnitt 20/21 |
| Eigener Content-Fetch möglich (hoch) | Ja, „Extract"-Endpunkt separat aufrufbar | Ja, „Contents"-Endpunkt separat aufrufbar | Ja — das ist hier explizit der zweite, unabhängige Baustein | Nein, an den Suchaufruf gebunden |

*(Quellen unten. Wo eine Zelle als „nicht dokumentiert" markiert ist, wurde bewusst keine Zahl erfunden — Vorgabe aus Abschnitt 8 des Plans selbst: keine unbelegten Aussagen.)*

## Bewertung der Kernfrage „getrennt oder gebündelt"

Für MASTER PLAN AI spricht mehr für **getrennt** als für gebündelt, aus zwei Gründen, die direkt aus dem bereits reviewten Plan folgen:

1. Abschnitt 21 fordert ohnehin eine austauschbare Schnittstelle — ein Anbieter, der Search und Fetch fest bündelt, macht diese Austauschbarkeit nur pauschal (ganz oder gar nicht), während eine Trennung erlaubt, z. B. nur den Such-Layer zu wechseln, ohne den Fetch-Layer anzufassen.
2. Abschnitt 8 verlangt Lizenz-/Aktualitäts-/Eignungsprüfung bei Open-Source-Funden — das ist eher eine Fetch-seitige Aufgabe (Repository-Metadaten lesen) als eine Such-Aufgabe, was ebenfalls für unabhängig austauschbare Bausteine spricht.

Das schließt Tavily/Exa nicht aus — beide erlauben, ihre Search- und Contents-Endpunkte auch unabhängig voneinander aufzurufen, könnten also intern „getrennt" genutzt werden, obwohl sie organisatorisch ein Anbieter sind.

## Empfehlung (keine Entscheidung)

Meine Einschätzung, zur gemeinsamen Diskussion, nicht als Festlegung:

* **Tavily** für V1 am naheliegendsten: geringster Integrationsaufwand, LLM-natives Format passt direkt auf den in Abschnitt 24 geforderten Structured-Output-Bedarf, Kosten für ein Planungswerkzeug mit überschaubarem Aufrufvolumen gut kalkulierbar, Search und Extract intern bereits trennbar (deckt die Empfehlung aus dem Abschnitt oben ab, ohne zwei Verträge zu benötigen).
* **Exa** als Alternative oder Ergänzung, falls sich in der Praxis zeigt, dass Open-Source-/Repository-Recherche (Abschnitt 8, Punkt 6–8) einen großen Anteil der Research-Aufrufe ausmacht — dafür ist die Code-Suchvertikale ein echter Unterschied.
* **Brave + Jina/Firecrawl** als Kandidat, falls Provider-Lock-in oder Kosten bei höherem Volumen stärker wiegen als Integrationsaufwand — architektonisch der „sauberste" Fit zu Abschnitt 21, aber der einzige mit zwei Verträgen/Ausfallpunkten.
* **Anthropic natives `web_search`** nicht als alleinige ADR-003-Lösung — würde die in Abschnitt 20/21 geforderte Provider-Unabhängigkeit der Research-Schnittstelle unterlaufen. Käme höchstens als einer von mehreren austauschbaren Adaptern hinter der Schnittstelle infrage, nicht als deren einzige Implementierung.

## Offene Punkte vor der endgültigen Entscheidung

* Kostenmodell des Anthropic-`web_search`-Tools wurde nicht belastbar verifiziert (siehe Tabelle) — vor einer Einbeziehung als Option nachprüfen.
* Keiner der Kandidaten wurde gegen ein reales Beispiel aus Abschnitt 8 (z. B. „vergleichbares Open-Source-Projekt mit Lizenzprüfung") getestet — vor endgültiger ADR-003-Festlegung ein kurzer Praxistest mit 2–3 echten Rechercheanfragen aus eurem tatsächlichen Anwendungsfall empfehlenswert.

## Quellen

- [Tavily Pricing 2026](https://coldiq.com/blog/tavily-pricing)
- [AI Search API Pricing (Juli 2026) — Tavily, Exa, Serper, SerpAPI, DataForSEO](https://www.buildmvpfast.com/api-costs/ai-search)
- [Exa API Pricing](https://exa.ai/pricing)
- [Exa AI Pricing Explained (2026)](https://fastcrw.com/blog/exa-pricing-explained)
- [Exa AI — GitHub-Repository/Übersicht](https://github.com/api-evangelist/exa-ai)
- [Brave Search API Pricing 2026](https://costbench.com/software/ai-search-apis/brave-search-api/)
- [Brave Search API: Pricing, Capabilities & Alternatives](https://apio.sh/apis/brave-search)
- [Firecrawl vs Jina AI](https://www.firecrawl.dev/alternatives/firecrawl-vs-jina-ai)
- [Jina AI vs. Firecrawl für Web-LLM-Extraktion](https://blog.apify.com/jina-ai-vs-firecrawl/)
- [Jina Reader Review 2026](https://makerstack.co/reviews/jina-reader-review/)
