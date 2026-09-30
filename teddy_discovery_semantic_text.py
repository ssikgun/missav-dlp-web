"""Derived semantic text only; authoritative subtitle evidence is never edited."""


def project_semantic_text(value: str | None) -> str | None:
    """Project source line breaks only at the semantic model-input boundary.

    Each CRLF pair or standalone CR/LF becomes one ASCII space. Consecutive
    breaks retain one space per logical break; ordinary spaces are untouched.
    Authoritative documents, alignment evidence, identities and timing stay
    unchanged. Other controls pass through to the existing Hermes validator.
    """
    if type(value) is not str:
        return value
    return value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


