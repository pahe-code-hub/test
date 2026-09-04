# SECURITY.md

Konsolidierte Sicherheitsanforderungen für MASTER PLAN AI V1. Basierend auf `MASTER_PLAN_v0.2.md` Abschnitt 30 und den in Review 4 gefundenen, in v0.2 bereits als Prinzip übernommenen Punkten — hier technisch konkretisiert für die Umsetzung.

## 1. Auth-Modell

**V1 ist Single-User/lokal ohne Authentifizierung** (Review 4 §4.4, `API_CONTRACT.md`). Das Backend bindet standardmäßig an `localhost`. Es gibt keinen Login, keine Sessions, keine Rollen.

**Verpflichtend vor jedem Netzwerk-Deployment** (auch nur im LAN, auch nur Docker auf einem gemeinsam genutzten Host): ein Auth-Mechanismus muss nachgerüstet werden, bevor die Anwendung außerhalb von `localhost` erreichbar ist. Dieser Punkt ist kein „nice-to-have später", sondern eine Voraussetzung — die aktuelle API-Spezifikation (`API_CONTRACT.md`) enthält keinerlei Zugriffskontrolle.

## 2. Secrets

* API-Schlüssel (Modellprovider, Tavily) ausschließlich serverseitig, über Environment-Variablen oder einen Secret-Store — niemals im Browser, niemals im Frontend-Bundle.
* Secrets erscheinen niemals in Prompts, Modell-Kontexten oder Logs. Die `agent_runs`-Tabelle (`DATA_MODEL.md`) speichert Provider/Modell/Fehlertext, aber keine Zugangsdaten — Fehlertexte von Provider-APIs sind vor dem Speichern auf enthaltene Secrets zu prüfen und zu redigieren (z. B. Autorisierungs-Header in Fehlermeldungen).
* `.env`-Dateien mit echten Schlüsseln gehören nicht ins Repository (`.gitignore`).

## 3. Prompt-Injection-Schutz (verbindlicher Mechanismus, nicht nur Prinzip)

Recherchierte Webinhalte sind die einzige Stelle im System, an der Text aus nicht kontrollierten externen Quellen in Modell-Prompts gelangt. Gegenmaßnahme, verbindlich für jede betroffene Prompt-Vorlage (Details und Wortlaut in `AGENT_PROMPTS.md`, Globale Regel 2):

* Jeder eingebettete Recherche-Inhalt wird in einen klar markierten `<external_research_data>`-Block gepackt, mit expliziter Anweisung an das Modell, den Inhalt als Datenmaterial statt als Anweisung zu behandeln.
* Betroffene Rollen: `research_v1` (verarbeitet Rohinhalte direkt aus `extract`), `architect_v1`, `challenger_v1`, `synthesizer_v1` (erhält Research-Zusammenfassung inkl. `research_sources`), `critic_v1` (erhält relevante Research-Erkenntnisse), `final_builder_v1` (erhält die von der Synthese referenzierten `research_sources`-Einträge) — eine bereits zusammengefasste Quelle bleibt Fremddaten, die Pflicht entfällt nicht durch vorgelagerte Verdichtung (Konsistenzfund aus der Nutzerprüfung: Synthesizer und Final Builder fehlten in der Vorversion). **Nicht betroffen:** `understanding_v1`, `evaluator_v1`, `revision_v1` — erhalten keine Research-Daten direkt.
* Diese Markierung ersetzt keine Sorgfalt bei der Modellwahl — sie reduziert das Risiko, verhindert es aber nicht vollständig. Auffälligkeiten (z. B. ein Research-Finding, das offensichtlich Formulierungen wie „ignoriere alle vorherigen Anweisungen" enthält) sollten im Research-Agent-Output als potenziell unzuverlässige Quelle markierbar sein — kein Blocker für V1, aber als Erweiterung vorgemerkt.

## 4. Eingabevalidierung

* Intake-Felder (Abschnitt 3): serverseitige Längenbegrenzung und Pflichtfeld-Prüfung vor `POST /api/projects/{id}/submit` (siehe `API_CONTRACT.md`).
* Alle Body-Payloads gegen ihr erwartetes Schema validieren (z. B. `escalation/resolve`-Action gegen den aktuellen `escalation_reason`, siehe `API_CONTRACT.md`) — eine nicht passende Kombination liefert `422`, nicht eine stille Fehlausführung.

## 5. Frontend-Ausgabe (HTML-Sanitizing)

Agentenausgaben (insbesondere `research`, `synthesis`, `final`) werden im Frontend als Markdown gerendert. Verbindlich:

* Markdown-Rendering ausschließlich über eine Bibliothek mit eingebautem HTML-Sanitizing.
* Kein `dangerouslySetInnerHTML` (oder Äquivalent) mit ungefiltertem Agenten- oder Recherche-Text.
* Begründung: Research-Inhalte stammen letztlich von Drittseiten und könnten über mehrere Verarbeitungsstufen (Research → Synthese → Final Builder) bis ins UI gelangen.

## 6. Sensible Nutzereingaben (Secrets/PII in Freitextfeldern)

Abschnitt 3.5 („Einschränkungen") ist Freitext und könnte versehentlich interne Hostnamen, Zugangsdaten oder personenbezogene Daten enthalten, die dann an externe Modell- und Research-Provider gesendet werden.

* **Dokumentiertes Restrisiko für V1** — keine automatische Erkennung/Blockierung.
* UI-Hinweis am Intake-Formular: „Bitte keine Zugangsdaten, Passwörter oder vertrauliche Interna in die Felder eintragen — der Text wird an externe KI- und Recherche-Dienste übermittelt."
* Automatischer Secret-Scan vor dem Absenden ist eine sinnvolle spätere Erweiterung (nicht V1).

## 7. Datenfluss zu externen Anbietern (Transparenz)

Zur Einordnung, was an wen geht:

| Ziel | Erhält |
|---|---|
| Modellprovider (Understanding, Architect, Challenger, Synthesizer, Critic, Evaluator, Revision, Final Builder) | Intake-Text, Research-Zusammenfassung, Zwischenergebnisse je nach Kontextgrenzen aus `MASTER_PLAN_v0.2.md` Abschnitt 23 |
| Tavily (Research Agent, ADR-003) | Suchanfragen abgeleitet aus Intake/Verständnis, sowie URLs zur Extraktion |

Es gibt keine Stelle, an der die vollständige Rohhistorie aller Nutzereingaben an einen einzelnen externen Dienst geht — die Kontextgrenzen aus Abschnitt 23 wirken auch als Datensparsamkeits-Maßnahme.

## 8. Kosten-/Aufruf-Notbremse als Abuse-Schutz

Der harte Kostendeckel aus `API_CONTRACT.md` (`MAX_MODEL_CALLS_PER_PROJECT`, unabhängig von `revision_count`) ist zugleich eine Sicherheitsmaßnahme: verhindert, dass ein Fehler in der Zählerlogik oder ein wiederholt fehlschlagender Workflow-Schritt zu unbegrenzten, kostenpflichtigen Aufrufen an externe Provider führt (Review 4 §4.2).

## 9. Backup

Die SQLite-Datei ist der einzige Ort mit dem vollständigen, auditierbaren Projektverlauf (`DATA_MODEL.md`, `agent_runs`). Für V1 genügt: Speicherort dokumentieren und dem Nutzer empfehlen, die Datei in eine vorhandene Backup-Routine einzubeziehen. Kein eigenes Backup-Feature in V1.

## 10. Audit statt separatem Logging

Auditierbarkeit (Abschnitt 31) läuft über `agent_runs` und `research_sources` in derselben Datenbank wie der Projekt-State (ADR-010) — keine separate Logging-Infrastruktur, die zusätzlich abgesichert werden müsste. Reduziert die Angriffsfläche gegenüber einer zusätzlichen Log-Pipeline.

## Nicht Teil von V1

Mehrbenutzer-Berechtigungssystem, Verschlüsselung der SQLite-Datei at-rest, automatisierter Secret-Scan, Rate-Limiting pro Nutzer (nur pro Projekt über die Kosten-Notbremse) — siehe Abschnitt 37 (Nicht-Ziele).
