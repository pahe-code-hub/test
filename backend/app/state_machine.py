"""
Zustände und Guards aus WORKFLOW_STATES.md, beschränkt auf die bis
Phase 3 tatsächlich erreichbaren Übergänge:

    DRAFT -> UNDERSTANDING -> WAITING_FOR_USER_CONFIRMATION -> RESEARCHING
                              \\-> WAITING_FOR_USER_CLARIFICATION -> UNDERSTANDING
                                                                  -> ESCALATION_REQUIRED(CLARIFICATION_LIMIT) -> DRAFT

Phase 3 führt `GENERATING_SOLUTIONS` aus und setzt nach zwei erfolgreichen
Zweigen ausschließlich den Grenz-State `SYNTHESIZING`. Der Synthesizer selbst
bleibt Phase 4 und wird hier nicht ausgeführt.

Kein Router darf einen Übergang ausführen, ohne vorher hier zu
prüfen, ob er zulässig ist - "Kein Agent darf eigenständig
Workflow-Schritte überspringen" (Masterplan Abschnitt 5).
"""
from __future__ import annotations

from app.config import MAX_CLARIFICATION_ROUNDS

# Zustandsnamen als Strings geführt (nicht als Python-Enum), weil sie 1:1
# in die `workflow_state`-Spalte (TEXT) aus DATA_MODEL.md geschrieben werden
# und WORKFLOW_STATES.md dieselben String-Bezeichner verwendet.
DRAFT = "DRAFT"
UNDERSTANDING = "UNDERSTANDING"
WAITING_FOR_USER_CLARIFICATION = "WAITING_FOR_USER_CLARIFICATION"
WAITING_FOR_USER_CONFIRMATION = "WAITING_FOR_USER_CONFIRMATION"
ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
RESEARCHING = "RESEARCHING"  # Zielzustand nach Bestätigung, in Phase 1 nicht weiter bearbeitet
RESEARCH_READY = "RESEARCH_READY"
WAITING_FOR_RESEARCH_APPROVAL = "WAITING_FOR_RESEARCH_APPROVAL"
GENERATING_SOLUTIONS = "GENERATING_SOLUTIONS"
SYNTHESIZING = "SYNTHESIZING"

CLARIFICATION_LIMIT = "CLARIFICATION_LIMIT"


class InvalidTransitionError(Exception):
    """Der angeforderte Übergang ist im aktuellen workflow_state nicht
    zulässig. Router übersetzen das nach HTTP 409 (API_CONTRACT.md)."""


def require_state(project, *allowed_states: str) -> None:
    if project.workflow_state not in allowed_states:
        raise InvalidTransitionError(
            f"Aktion in Zustand {project.workflow_state!r} nicht zulässig "
            f"(erwartet: {', '.join(allowed_states)})"
        )


def require_escalation_reason(project, expected_reason: str) -> None:
    require_state(project, ESCALATION_REQUIRED)
    if project.escalation_reason != expected_reason:
        raise InvalidTransitionError(
            f"Aktion passt nicht zu escalation_reason={project.escalation_reason!r} "
            f"(erwartet: {expected_reason})"
        )


def clarification_limit_reached(project) -> bool:
    return project.clarification_round_count >= MAX_CLARIFICATION_ROUNDS
