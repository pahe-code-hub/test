"""
Zustände und Guards aus WORKFLOW_STATES.md, beschränkt auf die bis
Phase 4 tatsächlich erreichbaren Übergänge:

    DRAFT -> UNDERSTANDING -> WAITING_FOR_USER_CONFIRMATION -> RESEARCHING
                              \\-> WAITING_FOR_USER_CLARIFICATION -> UNDERSTANDING
                                                                  -> ESCALATION_REQUIRED(CLARIFICATION_LIMIT) -> DRAFT

    SYNTHESIZING -> WAITING_FOR_SYNTHESIS_APPROVAL -> REVIEWING
                                                    \\-> SYNTHESIZING (ÄNDERUNGSWUNSCH)

Phase 5 führt `REVIEWING` (critic_v1) und `EVALUATING` (evaluator_v1)
tatsächlich aus und schließt die interne Revisionsschleife:

    REVIEWING -> EVALUATING (automatisch, unabhängig von OK/ANMERKUNGEN)
    EVALUATING -> FINALIZING (PASS) - Zielzustand, final_builder (Phase 6)
                                       wird hier NICHT ausgeführt, dasselbe
                                       Park-Muster wie zuvor bei REVIEWING/
                                       SYNTHESIZING
    EVALUATING -> REVISION_REQUIRED -> REVISING (beide automatisch)
                                        wenn revision_count < MAX_INTERNAL_REVISIONS
    REVISING -> EVALUATING (automatisch, KEIN erneuter critic_v1-Lauf, AT-5.5)
    EVALUATING -> ESCALATION_REQUIRED(REVISION_LIMIT)
                  wenn revision_count >= MAX_INTERNAL_REVISIONS
    ESCALATION_REQUIRED(REVISION_LIMIT) -> REVISING (RETRY_REVISION, Nutzer)
                                         -> FINALIZING (ACCEPT_WITH_OPEN_POINTS, Nutzer)

Phase 6 führt `FINALIZING` (final_builder_v1) tatsächlich aus und erreicht
den Endzustand:

    FINALIZING -> COMPLETED (automatisch, final_builder_v1 abgeschlossen)

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
WAITING_FOR_SYNTHESIS_APPROVAL = "WAITING_FOR_SYNTHESIS_APPROVAL"
REVIEWING = "REVIEWING"  # Critic läuft (Phase 5)
EVALUATING = "EVALUATING"  # Evaluator läuft (Phase 5)
REVISION_REQUIRED = "REVISION_REQUIRED"  # transient, kettet sofort zu REVISING
REVISING = "REVISING"  # Revision Agent läuft (Phase 5)
FINALIZING = "FINALIZING"  # Final Builder läuft (Phase 6)
COMPLETED = "COMPLETED"  # Endzustand - Plan fertiggestellt

CLARIFICATION_LIMIT = "CLARIFICATION_LIMIT"
REVISION_LIMIT = "REVISION_LIMIT"


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
