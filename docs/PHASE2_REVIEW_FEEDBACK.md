Review-Rückmeldung zu Commit `f87b517` (Phase 2). Die 24 Tests laufen in einer funktionierenden Umgebung durchgängig grün, Migration wurde verifiziert — dein `pytest`-Sandbox-Problem war ein reines Toolchain-Problem, der Code selbst ist an dieser Stelle korrekt. Ein echter Fund bleibt aber offen, bitte gezielt beheben, nichts anderes anfassen:

## Fund: unsicherer Agent-Fallback in `app/model_provider.py` / `app/config.py`

```python
# config.py
OPENCLAW_AGENT_ID = os.environ.get("MPA_OPENCLAW_AGENT_ID", "main")

# model_provider.py, _get_agent()
agent_id = os.environ.get(env_name, OPENCLAW_AGENT_ID)
```

Ohne explizit gesetztes `MPA_OPENCLAW_AGENT_ID_<ROLLE>` fällt das Backend auf den Agenten `"main"` zurück. In der tatsächlichen Betriebsumgebung ist `main` der persönliche, mit Telegram verbundene Assistenzagent des Nutzers (`openclaw agents list`: `Model: openai/gpt-5.6-sol`, `Routing: Telegram default`) — nicht ein für MASTER PLAN AI vorgesehener Agent.

Zwei konkrete Folgen:

1. **Betriebsrisiko**: automatisierte Research-/Understanding-Läufe würden ohne explizite Konfiguration den persönlichen Telegram-Bot-Agenten des Nutzers mitbenutzen.
2. **Falsche Audit-/Kostendaten**: `agent_runs.model` und `estimated_cost_usd` werden aus `MODEL_CLASS_MAP[model_class]` (z. B. `"claude-sonnet-5"`) berechnet — das ist aber nur die *beabsichtigte* Modellklasse, keine vom SDK bestätigte Tatsache (`ExecutionResult` hat kein `model`-Feld). Läuft durch den `"main"`-Fallback tatsächlich ein GPT-Modell, werden trotzdem Claude-Preise ausgewiesen. Das verletzt Abschnitt 31 (Auditierbarkeit muss korrektes Modell/Provider dokumentieren) und untergräbt die Kosten-Notbremse aus Abschnitt 32/Review 4 §4.2, deren Schwellenwerte auf plausiblen Kostendaten beruhen.

## Erforderliche Korrektur

* Kein stiller Fallback auf `"main"` oder irgendeinen anderen bereits existierenden Agenten mehr. Fehlt `MPA_OPENCLAW_AGENT_ID_<ROLLE>` für eine Rolle, die tatsächlich aufgerufen wird, soll `call_model` einen klaren `ModelProviderError`/Konfigurationsfehler werfen (analog zum bestehenden „Unbekannte Modellklasse"-Guard) statt automatisch auf einen bestehenden Agenten auszuweichen.
* Ergänze in `backend/README.md` (und falls sinnvoll `docs/PHASE2_CHECKPOINT.md`) einen expliziten Einrichtungsschritt: für jede in Phase 1/2 genutzte Rolle (aktuell `understanding`, `research`) muss der Nutzer per `openclaw agents add` einen dedizierten Agenten anlegen, dessen Gateway-Modell tatsächlich zu `MODEL_CLASS_MAP` passt (z. B. Rolle `understanding`/`research` = Modellklasse MEDIUM = `claude-sonnet-5`), und dessen Agent-ID über `MPA_OPENCLAW_AGENT_ID_UNDERSTANDING`/`MPA_OPENCLAW_AGENT_ID_RESEARCH` eintragen — nicht den vorhandenen `main`/`masterplan`/`aktien`-Agenten wiederverwenden.
* Optional, falls einfach umsetzbar: `agent_runs` um ein Feld ergänzen, das den tatsächlich verwendeten `agent_id`-String festhält (nicht nur `model`/`model_class`), damit bei einer künftigen Abweichung wenigstens nachvollziehbar ist, welcher Gateway-Agent geantwortet hat. Nur umsetzen, wenn das ohne Migration-Chaos machbar ist — kein Muss für diesen Fix.

Bitte ausschließlich diesen einen Punkt beheben, nichts an Scope oder bereits getroffenen Entscheidungen (ADR-003, ADR-011, Tavily-Anbindung, Frontend) ändern. Danach kurz in `docs/PHASE2_CHECKPOINT.md` nachtragen, was korrigiert wurde, committen und pushen.
