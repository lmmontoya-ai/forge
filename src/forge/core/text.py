"""Token counting for the message cap and the render budget tests.

tiktoken (o200k_base) when available; a whitespace approximation otherwise,
in which case the token-bound golden tests skip (the LEDGER fallback rule).
"""
from __future__ import annotations

_enc = None
_tried = False


def _encoder():
    global _enc, _tried
    if not _tried:
        _tried = True
        try:
            import tiktoken
            _enc = tiktoken.get_encoding("o200k_base")
        except Exception:
            _enc = None
    return _enc


def token_len(text: str) -> int:
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text))
    return len(text.split())


def truncate_tokens(text: str, cap: int) -> tuple[str, bool]:
    enc = _encoder()
    if enc is not None:
        toks = enc.encode(text)
        if len(toks) <= cap:
            return text, False
        return enc.decode(toks[:cap]), True
    words = text.split()
    if len(words) <= cap:
        return text, False
    return " ".join(words[:cap]), True
