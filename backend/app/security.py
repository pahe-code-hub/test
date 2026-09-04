"""
Hilfsfunktionen aus SECURITY.md, die für Phase 1 bereits greifen
(die restlichen Punkte - Prompt-Injection-Wrapper, HTML-Sanitizing -
betreffen erst Research/Synthese/Frontend und sind hier nicht
implementiert, da Phase 1 keinen dieser Agenten enthält).
"""
import re

# Deckt gängige Secret-Formen ab, die versehentlich in einer
# Provider-Fehlermeldung landen könnten (SECURITY.md §2: "Fehlertexte
# von Provider-APIs sind vor dem Speichern auf enthaltene Secrets zu
# prüfen und zu redigieren"). Kein Anspruch auf Vollständigkeit - eine
# gezielte, aber bewusst simple Phase-1-Maßnahme.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9\-_.]{10,}"),
    re.compile(r"(?i)x-api-key:\s*[A-Za-z0-9\-_]{10,}"),
]


def redact_secrets(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
