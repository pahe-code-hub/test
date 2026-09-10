# FRONTEND_CHECKPOINT.md

**Status: Implementiert, automatisiert getestet (27/27), real gegen den
laufenden Backend-Server geprüft.** Freigabe (APPROVED) liegt beim
Nutzer.

Nachweis für das **Frontend für Phasen 1-7** (Auftrag vom Nutzer,
2026-09-10), umgesetzt nach `PLAN → IMPLEMENT → TEST → REVIEW →
CHECKPOINT` entsprechend der bisherigen Phasen-Disziplin dieses Projekts.

## PLAN

Referenzen gelesen vor der Implementierung: `docs/API_CONTRACT.md`
(alle Endpunkte inkl. Fehlerformat und SSE-Event-Tabelle),
`docs/MASTER_PLAN_v0.2.md` Abschnitt 2 (UX-Grundkonzept: "Idee →
Verständnis → Recherche → Lösungsentwürfe → Synthese → Prüfung →
Abnahme → Ergebnis"), Abschnitt 25 (User Interface je Schritt) und 26
(Live-Status/SSE), `docs/WORKFLOW_STATES.md` (Guards je Nutzeraktion),
sowie das bestehende `frontend/src/ResearchPanel.tsx` (Phase-2-Ansicht,
wiederverwendet statt neu geschrieben).

**Architekturentscheidungen:**

* **Ein Prozess, ein Port (ADR-004):** `frontend/dist/` wird über
  `StaticFiles` im selben FastAPI-Prozess ausgeliefert, kein separater
  Vite-Dev-Server im Normalbetrieb. `StaticFiles` wird NACH dem
  API-Router gemountet, damit `/api/*` und `/health` Vorrang haben.
* **Keine Router-Bibliothek:** die App navigiert ausschließlich über den
  Query-Parameter `?project=<id>` (per `history.pushState`, Browser-
  Zurück funktioniert über `popstate`) statt über Pfad-Routen - dadurch
  braucht `StaticFiles(html=True)` keinen Wildcard-SPA-Fallback, ein
  einfacher Mount an `/` genügt (kein zusätzlicher Router-Abhängigkeit
  wie react-router, passt zum bereits minimalen bestehenden Setup).
* **State-Strategie:** JEDES SSE-Event (`state_changed`, `agent_run_*`,
  `cost_updated`) löst einen vollständigen `GET /api/projects/{id}`-
  Refetch aus, statt Teilzustände client-seitig nachzubilden - das
  Backend bleibt die einzige Quelle der Wahrheit (Abschnitt 26 verlangt
  nur, dass nicht gepollt werden muss, kein Client-State-Merge).
  `agent_run_started`/`_completed`/`_failed` halten zusätzlich eine
  transiente "läuft gerade"-Anzeige.
* **Panel-Zuordnung 1:1 zu `workflow_state`:** ein zentraler
  `Panel`-Switch in `ProjectDetailView.tsx` entscheidet anhand von
  `project.workflow_state`/`escalation_reason`, welche Ansicht gezeigt
  wird - jeder Zustand aus `WORKFLOW_STATES.md` hat eine definierte
  Darstellung (Formular, Freigabe-Gate oder Lade-Anzeige).
* **Retry ist state-unabhängig:** `last_run_status = FAILED` kann laut
  `WORKFLOW_STATES.md` bei jedem laufenden State auftreten - ein
  zentrales Retry-Banner in `ProjectDetailView.tsx` statt es in jedem
  Panel einzeln nachzubilden.

## IMPLEMENT

* `frontend/src/api.ts`: typisierter Fetch-Client, TypeScript-Typen
  spiegeln exakt `backend/app/schemas.py` (`ProjectDetail` und alle
  Unterobjekte), Fehlerbehandlung für das `{"error":{"code","message"}}`-
  Format aus `API_CONTRACT.md` inkl. Fallback für reine FastAPI-
  Validierungsfehler (422 ohne eigenes Envelope) und für Antworten ganz
  ohne JSON-Body.
* `frontend/src/useProjectEvents.ts`: SSE-Hook über `EventSource`,
  bildet die Event-Tabelle aus `API_CONTRACT.md` § Fortschritt ab.
* `frontend/src/Markdown.tsx`: gemeinsame, sanitizte Markdown-Komponente
  (`react-markdown` + `rehype-sanitize`, `skipHtml`) - jede Agenten-
  Textausgabe läuft hier durch, nirgends `dangerouslySetInnerHTML`
  (SECURITY.md: "HTML-Ausgabe sanitizen").
* `frontend/src/StepNav.tsx`: 8-Schritt-Navigation aus Abschnitt 2,
  bildet `workflow_state`/`escalation_reason` auf den aktiven Schritt ab.
* `frontend/src/CostBadge.tsx`: Gesamtsumme immer sichtbar (kommt schon
  mit `ProjectDetail`, kein Extra-Request), Aufschlüsselung je Rolle
  on-demand über `GET /cost`.
* `frontend/src/IntakeForm.tsx`: sechs Pflichtfelder, PATCH-Autosave bei
  `onBlur` (nicht bei jedem Tastendruck), "IDEE PRÜFEN" erst aktiv, wenn
  alle sechs Felder lokal befüllt sind (serverseitige Prüfung bleibt
  zusätzlich maßgeblich, Fehlermeldung wird angezeigt statt verschluckt).
* `frontend/src/UnderstandingGate.tsx`: `WAITING_FOR_USER_CONFIRMATION`
  (RICHTIG VERSTANDEN/KORRIGIEREN), `WAITING_FOR_USER_CLARIFICATION`
  (inkl. `contradiction_note`-Hinweis, Review 1 §1.3), sowie
  `ESCALATION_REQUIRED(CLARIFICATION_LIMIT)` (AT-1.4: einziger Ausgang
  REWORK_INTAKE).
* `frontend/src/ResearchPanel.tsx`: bestehende Phase-2-Ansicht integriert
  (erhält Daten jetzt vom Orchestrator statt selbst zu fetchen, vermeidet
  einen doppelten `GET`), ergänzt um das konfigurierbare Recherche-Gate
  (RECHERCHE FREIGEBEN / NEU RECHERCHIEREN / ANMERKUNG), nur sichtbar bei
  `WAITING_FOR_RESEARCH_APPROVAL`.
* `frontend/src/SolutionsPanel.tsx`: Architect/Challenger nebeneinander
  (Abschnitt 25), reine Anzeige ohne Gate.
* `frontend/src/SynthesisPanel.tsx`: Zielkonzept, ZIELKONZEPT FREIGEBEN /
  ÄNDERUNGSWUNSCH, `hint`-Feld (nur in der change-request-Antwort
  enthalten, wird hier aus dem zuletzt empfangenen `ProjectDetail`
  übernommen statt erneut geholt).
* `frontend/src/QualityPanel.tsx`: Critic-Findings + Evaluator-Durchläufe,
  rein informativ (Prüfung läuft laut `WORKFLOW_STATES.md` vollautomatisch,
  kein Nutzer-Gate).
* `frontend/src/EscalationPanel.tsx`: `ESCALATION_REQUIRED(REVISION_LIMIT)`
  (AT-5.4: RETRY_REVISION / ACCEPT_WITH_OPEN_POINTS).
* `frontend/src/FinalPanel.tsx`: finaler Plan (alle 10 Abschnitte +
  Präsentationsstruktur), Markdown-Export-Button (`GET /export`). PDF/
  DOCX/JSON bewusst nicht vorgesehen (ADR-012: Phase 8 explizit
  zurückgestellt).
* `frontend/src/ProjectDetailView.tsx`: Orchestrator - lädt das Projekt,
  hängt `useProjectEvents` ein, zeigt Toolbar (Zurück, Live-Punkt,
  Kostenanzeige), `StepNav`, Retry-Banner, transiente Aktivitätsanzeige
  und schaltet zwischen den Panels.
* `frontend/src/ProjectListView.tsx`: Projektübersicht (`GET /api/projects`),
  "Neues Projekt" legt einen leeren Entwurf an (`IntakeIn` erlaubt das
  laut `schemas.py`-Docstring explizit) und wählt ihn aus.
* `frontend/src/App.tsx`: Root - Liste vs. Detail anhand `?project=`,
  `history.pushState`/`popstate` für Browser-Zurück.
* `backend/app/main.py`: **einzige Backend-Änderung**, wie vom Nutzer
  vorgegeben - `StaticFiles`-Mount für `frontend/dist/`, übersprungen
  (kein Fehler), falls `dist/` nicht existiert (noch nicht gebaut).

## TEST

Neu in `frontend/src/test/` (27 Tests, Vitest + Testing Library, neu als
Dev-Dependency ergänzt - bislang gab es keine Frontend-Testinfrastruktur):

| Datei | Nachweis |
|---|---|
| `api.test.ts` | Fehler-Envelope-Extraktion (`{error:{code,message}}`), 422-Fallback auf `detail`, Fallback ganz ohne JSON-Body, korrekte Request-Konstruktion, `exportMarkdownUrl` |
| `StepNav.test.tsx` | Abbildung aller relevanten `workflow_state`-Werte auf den richtigen Schritt, inkl. `ESCALATION_REQUIRED`-Verzweigung nach `escalation_reason`, alle 8 Schritte in korrekter Reihenfolge |
| `IntakeForm.test.tsx` | "IDEE PRÜFEN" bleibt deaktiviert bis alle 6 Felder befüllt sind; PATCH-Autosave nur bei `onBlur`, nicht bei jedem Tastendruck; erfolgreicher Submit reicht das Ergebnis weiter; Fehler (`INCOMPLETE_INTAKE`) wird angezeigt |
| `ProjectListView.test.tsx` | Leer-Zustand, Liste mit Status-Label, Zeilenklick wählt aus, "Neues Projekt" legt an und wählt aus |
| `useProjectEvents.test.tsx` | `state_changed`/`cost_updated` lösen Refetch aus; `agent_run_started` hält nur transiente Activity (kein Refetch); `agent_run_completed` aktualisiert Activity UND refetcht; `connected` erst nach `onopen`; keine Verbindung ohne `projectId` |

Bewusste Scope-Grenze: `tsconfig.json` schließt `src/test` explizit aus
(`exclude`) - der Produktions-Build (`tsc -b && vite build`) muss nicht
gegen Vitest-/Jest-DOM-Ambient-Typen prüfen (dort trat ein Typkonflikt
zwischen `@testing-library/jest-dom`s Vitest-Erweiterung und Vitests
eigenen Typen auf - "All declarations of 'Assertion' must have identical
type parameters"); Testdateien werden von Vitest selbst über esbuild
transpiliert und laufen unabhängig davon korrekt (27/27 grün), tragen
aber keinen eigenen `tsc`-Lauf. Kein Blocker, da Testcode nie
ausgeliefert wird.

Ausführungsstand (echte Laufzeitumgebung):

* `npm run build` (`tsc -b && vite build`): **bestanden**, `dist/`
  enthält `index.html` + gehashte `assets/`.
* `npm run test` (`vitest run`): **27 von 27 bestanden**, ~6s Laufzeit.
* Server real neu gestartet (`app/main.py`-Änderung erfordert das) und
  geprüft: `GET /health` → 200, `GET /` → 200 (liefert `index.html` mit
  den aktuellen gehashten Asset-Pfaden), `GET /?project=<id>` → 200
  (derselbe `index.html`, Query-String beeinflusst `StaticFiles(html=True)`
  nicht), `GET /assets/*.js`/`*.css` → 200, `GET /api/projects` → 200
  (API weiterhin unter demselben Port erreichbar). Ein Testprojekt real
  über die API angelegt und die komplette `ProjectDetail`-JSON-Struktur
  gegen die TypeScript-Typen in `api.ts` abgeglichen - keine Abweichung.

## REVIEW

* **Sicherheit:** alle Agentenausgaben laufen durch die eine sanitizte
  `Markdown`-Komponente (`rehypeSanitize`, `skipHtml`), keine
  `dangerouslySetInnerHTML`-Stelle im gesamten Frontend. Keine Secrets
  im Frontend-Code (SECURITY.md §1) - der Client kennt ausschließlich
  Same-Origin-`/api/*`-Pfade. Externe Links (`ResearchPanel`) mit
  `target="_blank" rel="noreferrer"` gegen Reverse-Tabnabbing.
* **Barrierefreiheit:** Formularfelder über `<label>` assoziiert (nicht
  nur `placeholder`), Fehler/Rückfragen mit `role="alert"`, Zeilen der
  Projektliste zusätzlich per Tastatur bedienbar (`role="button"`,
  `tabIndex`, `onKeyDown` für Enter/Leertaste) - beim ersten Durchgang
  nur maus-klickbar, im Review nachgebessert.
* **Konsistenz mit `WORKFLOW_STATES.md`:** jeder in der Übergangstabelle
  genannte State hat eine Entsprechung im `Panel`-Switch; States ohne
  Nutzeraktion (`REVIEWING`/`EVALUATING`/`REVISION_REQUIRED`/`REVISING`,
  alle Such-/Lauf-States) zeigen bewusst keine Buttons.
* Keine Backend-Logik verändert außer der einen angeforderten
  `StaticFiles`-Ergänzung in `main.py` - `git diff` gegen `backend/app/`
  bestätigt das (nur `main.py` geändert, restliches Backend unberührt).

## CHECKPOINT

Das Frontend deckt den kompletten Workflow aus Phasen 1-7 ab (Intake,
Verständnis inkl. Rückfragen/Eskalation, Recherche inkl. optionalem Gate,
Lösungsentwürfe, Synthese inkl. Freigabe, automatische Qualitätsprüfung,
Eskalation bei Revisionslimit, finaler Plan inkl. Markdown-Export),
live aktualisiert über SSE ohne Polling, mit Kostenanzeige und
zentralem Retry. 27/27 automatisierte Tests grün, Produktionsbuild und
realer Serverstart verifiziert. Die endgültige Freigabe liegt beim
Nutzer.

## So erreichst du es im Browser

Der Server läuft bereits auf **`http://127.0.0.1:8000/`** (derselbe
Prozess wie die API). Falls er neu gestartet werden muss:

```
cd /root/test/frontend && npm run build   # nur nötig nach Frontend-Änderungen
cd /root/test/backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Auf dem Server selbst (oder per SSH-Portweiterleitung `ssh -L 8000:localhost:8000 …`
von deinem Rechner aus) einfach `http://127.0.0.1:8000/` im Browser öffnen.
