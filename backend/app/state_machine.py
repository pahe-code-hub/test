"""
Zustände und Guards aus WORKFLOW_STATES.md, beschränkt auf die in
Phase 1 tatsächlich erreichbaren Übergänge:

    DRAFT -> UNDERSTANDING -> WAITING_FOR_USER_CONFIRMATION -> RESEARCHING
                              \\-> WAITING_FOR_USER_CLARIFICATION -> UNDERSTANDING
                                                                  -> ESCALATION_REQUIRED(CLARIFICATION_LIMIT) -> DRAFT

RESEARCHING ist in Phase 1 ein reiner Zielzustand (bestätigtes
Verständnis erreicht, siehe MASTER_PLAN_v0.2.md Abschnitt 35,
Phase-1-Abnahme: "Ein Projekt kann von DRAFT bis bestätigtem
Verständnis laufen") - der Research Agent selbst wird erst in
Phase 2 implementiert. Es findet hier bewusst KEINE Vorwegnahme
späterer States (GENERATING_SOLUTIONS, SYNTHESIZING, ...) statt.

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
