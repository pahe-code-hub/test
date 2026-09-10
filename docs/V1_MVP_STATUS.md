# V1_MVP_STATUS.md

**Status: V1-MVP = APPROVED (2026-09-10).** Phasen 1-7 vollständig
implementiert, real getestet und vom Nutzer freigegeben. Phase 8
bewusst zurückgestellt (ADR-012) — außerhalb des V1-Scopes laut
`ACCEPTANCE_TESTS.md`/`API_CONTRACT.md`, keine Abnahmekriterien offen.

## Phasenstand

| Phase | Inhalt | Freigabe | Nachweis |
|---|---|---|---|
| 1 | Workflow-Kern | ✅ APPROVED | `PHASE1_CHECKPOINT.md` |
| 2 | Research | ✅ APPROVED | `PHASE2_CHECKPOINT.md` |
| 3 | Multi-Agent Planning (Architect + Challenger) | ✅ APPROVED | `PHASE3_CHECKPOINT.md` |
| 4 | Synthese | ✅ APPROVED | `PHASE4_CHECKPOINT.md` |
| 5 | Qualität (Critic/Evaluator/Revision) | ✅ APPROVED | `PHASE5_CHECKPOINT.md` |
| 6 | Final Output | ✅ APPROVED | `PHASE6_CHECKPOINT.md` |
| 7 | UX/Betrieb (SSE, Kosten) | ✅ APPROVED | `PHASE7_CHECKPOINT.md` |
| 8 | Export/Packaging | zurückgestellt | `DECISIONS.md` ADR-012 |

## Realer Gesamtnachweis

Ein Projekt lief einmal komplett real durch die gesamte Kette:

```
DRAFT → submit → UNDERSTANDING → RESEARCHING → GENERATING_SOLUTIONS
  (Architect+Challenger parallel) → SYNTHESIZING → WAITING_FOR_SYNTHESIS_APPROVAL
  → synthesis/approve → REVIEWING (Critic: ANMERKUNGEN)
  → EVALUATING (Evaluator: REVISION_REQUIRED nach einem JSON-Glitch, per
    Retry korrekt aufgefangen) → REVISING → EVALUATING (PASS)
  → FINALIZING (Final Builder) → COMPLETED
```

10 echte Modellaufrufe über den echten OpenClaw-Gateway, Gesamtkosten
$2,89 (Understanding+Research+Architect+Challenger-Lauf separat: $2,89
weitere für Synthese/Qualität/Final Builder — siehe Checkpoints für
Einzelwerte). Export als Markdown real abgerufen und inhaltlich
geprüft.

## Neun dedizierte Gateway-Agenten im Einsatz

`mpa-understanding`, `mpa-research` (MEDIUM/`claude-sonnet-5`),
`mpa-architect`, `mpa-challenger`, `mpa-synthesizer`, `mpa-critic`,
`mpa-evaluator`, `mpa-revision`, `mpa-final-builder` (HIGH/`claude-opus-5`,
`final_builder` je nach Konfiguration auch MEDIUM möglich).

## Insgesamt fünf reale openclaw-sdk-2.1.0-Bugs gefunden und umgangen

Siehe `backend/README.md` § "Bekannte openclaw-sdk-2.1.0-Bugs" und
`app/model_provider.py`/`app/research_provider.py` für Details:
fehlendes `model`/`input`-Feld im HTTP-Bridge-Payload, falsch
ausgewerteter Antworttext, fehlende Token-Auswertung, ignorierter
Timeout, verschluckte Tavily-Fehlerdetails.

## Testsuite

74/74 Tests grün (unabhängig von Claude Code auf dem Server *und* in
einer zweiten, separaten Umgebung nachvollzogen), alle Migrationen
0001-0006 laufen sauber gegen frisches SQLite durch.

## Offen / bewusst nicht Teil von V1

* Phase 8 (PDF/DOCX/JSON-Export, Windows-Paket) — ADR-012.
* Kein Auth/Multi-User — V1 ist explizit Single-User/lokal
  (Masterplan Abschnitt 37, Nicht-Ziele).
* Kein Frontend über `ResearchPanel.tsx` hinaus (Projekt-Anlage,
  Klärungsfragen-UI etc. liefen bisher nur über direkte API-Aufrufe).
