"""
Zentrale Konfiguration für MASTER PLAN AI (Phase 1).

Modellklassen-Mapping, Limits und Pfade sind hier gebündelt, damit
sie nicht über den Code verstreut sind (Abschnitt 20: "Konkrete
Provider und Modelle werden per Konfiguration zugeordnet").
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Persistenz (DATA_MODEL.md) -------------------------------------------
DATABASE_PATH = os.environ.get("MPA_DATABASE_PATH", str(BASE_DIR / "masterplan.db"))
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# --- Modellprovider (Abschnitt 20, AGENT_PROMPTS.md) -----------------------
# LOW ist für V1 ungenutzt, aber reserviert (ADR-006) - hier trotzdem
# konfigurierbar, damit ein künftiger Einsatz keine Code-Änderung braucht.
MODEL_CLASS_MAP = {
    "LOW": os.environ.get("MPA_MODEL_LOW", "claude-haiku-4-5"),
    "MEDIUM": os.environ.get("MPA_MODEL_MEDIUM", "claude-sonnet-5"),
    "HIGH": os.environ.get("MPA_MODEL_HIGH", "claude-opus-5"),
}

# Anthropic bleibt für V1 der einzige tatsächliche Modellanbieter hinter
# OpenClaw (llm_provider auf jedem AgentConfig) - austauschbar über diese
# eine Konstante, ohne model_provider.py anzufassen (Abschnitt 20).
MODEL_PROVIDER = os.environ.get("MPA_MODEL_PROVIDER", "anthropic")

# --- OpenClaw Gateway (ADR-011) ---------------------------------------------
# Verbindliche Laufzeitkomponente - call_model() geht ausschließlich über
# openclaw-sdk, nie direkt gegen einen Modellanbieter-Client.
# None = openclaw-sdk versucht Auto-Erkennung (siehe OpenClawClient.connect):
# gateway_ws_url -> openai_base_url -> lokaler Gateway unter ws://127.0.0.1:18789.
OPENCLAW_GATEWAY_WS_URL = os.environ.get("MPA_OPENCLAW_GATEWAY_WS_URL") or None
OPENCLAW_OPENAI_BASE_URL = os.environ.get("MPA_OPENCLAW_OPENAI_BASE_URL") or None
OPENCLAW_API_KEY = os.environ.get("MPA_OPENCLAW_API_KEY") or None

# Rollenbezogene IDs bereits im Gateway konfigurierter, dedizierter Agenten
# werden erst beim jeweiligen Aufruf aus MPA_OPENCLAW_AGENT_ID_<ROLLE> gelesen.
# Es gibt bewusst keinen globalen/default Agenten: Ein stiller Rückfall auf
# einen persönlichen Gateway-Agenten würde Routing, Audit und Kosten verfälschen.

# Grobe, konservative Kostenschätzung für die Kostenanzeige (Abschnitt 32).
# Kein Anspruch auf Abrechnungsgenauigkeit - nur Größenordnung für die UI.
MODEL_PRICING_USD_PER_MTOK = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
}

# 60s war der ursprüngliche Phase-1/2-Default; der reale Phase-5/6-E2E-Lauf
# (2026-09-10) zeigte, dass HIGH-Klasse-Rollen mit großem Kontext
# (synthesizer_v1, kompletter Research+Architect+Challenger-Kontext) real
# zwischen ~130s und >150s brauchen können - ein Lauf schlug bei genau 150s
# fehl (echter Timeout, kein Payload-/Routing-Fehler, per Retry mit 240s
# erfolgreich wiederholt). Default entsprechend angehoben, überschreibbar.
MODEL_CALL_TIMEOUT_SECONDS = float(os.environ.get("MPA_MODEL_TIMEOUT_SECONDS", "180"))
MODEL_CALL_MAX_PROVIDER_RETRIES = int(os.environ.get("MPA_MODEL_MAX_PROVIDER_RETRIES", "2"))

# --- Workflow-Limits (WORKFLOW_STATES.md) ----------------------------------
MAX_CLARIFICATION_ROUNDS = int(os.environ.get("MPA_MAX_CLARIFICATION_ROUNDS", "3"))
# Abschnitt 16: nach MAX_INTERNAL_REVISIONS erfolglosen Revisionen ->
# ESCALATION_REQUIRED(REVISION_LIMIT). Ein manuelles RETRY_REVISION des
# Nutzers (escalation/resolve) ist davon unabhängig und nicht selbst
# gedeckelt - jede weitere Runde geht wieder über dasselbe Nutzer-Gate,
# keine Endlosschleife ohne Nutzeraktion (Leitprinzip 8).
MAX_INTERNAL_REVISIONS = int(os.environ.get("MPA_MAX_INTERNAL_REVISIONS", "2"))

# --- Final Builder (Phase 6, AGENT_PROMPTS.md § final_builder_v1) ----------
# Laut Masterplan "MITTEL oder HOCH (konfigurierbar)" - anders als die
# übrigen Rollen hier bewusst konfigurierbar statt im Router hart codiert.
FINAL_BUILDER_MODEL_CLASS = os.environ.get("MPA_FINAL_BUILDER_MODEL_CLASS", "HIGH")

# --- Kosten-Notbremse (API_CONTRACT.md, Review 4 §4.2) ---------------------
# Unabhängig von jeder Workflow-Zählvariable (revision_count etc.).
MAX_MODEL_CALLS_PER_PROJECT = int(os.environ.get("MPA_MAX_MODEL_CALLS_PER_PROJECT", "50"))
MAX_ESTIMATED_COST_PER_PROJECT_USD = float(
    os.environ.get("MPA_MAX_ESTIMATED_COST_PER_PROJECT_USD", "5.00")
)

# --- Prompt-Versionierung (ADR-009) ----------------------------------------
PROMPTS_DIR = BASE_DIR / "prompts"

# --- Research Provider (ADR-003, Phase 2) ---------------------------------
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") or None
TAVILY_BASE_URL = os.environ.get("MPA_TAVILY_BASE_URL", "https://api.tavily.com")
RESEARCH_TIMEOUT_SECONDS = float(os.environ.get("MPA_RESEARCH_TIMEOUT_SECONDS", "30"))
RESEARCH_MAX_SOURCES = int(os.environ.get("MPA_RESEARCH_MAX_SOURCES", "8"))
