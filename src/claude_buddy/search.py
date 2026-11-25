"""Accent- and case-insensitive search ("aplicacion" matches "Aplicación")."""

import unicodedata


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def matches(query: str, haystack_folded: str) -> bool:
    """Every word of the query must appear somewhere in the (already folded) haystack."""
    return all(word in haystack_folded for word in fold(query).split())
