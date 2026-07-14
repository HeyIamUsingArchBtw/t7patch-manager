"""Minimal Valve KeyValues (VDF) parser & serialiser.

Enough to safely round-trip Steam's ``localconfig.vdf`` — nested dicts of
quoted string leaves. Preserves ordering (uses plain ``dict`` — Python 3.7+).

We deliberately do NOT depend on the third-party ``vdf`` package: this app
runs inside a pipx venv with system-site-packages, and every extra pip dep
is one more thing that can break on an odd distro.

Supported syntax (subset that covers every real ``localconfig.vdf`` we've
seen in the wild):

    "key"
    {
        "leaf"   "value with \\"escaped\\" quotes"
        "nested"
        {
            ...
        }
    }

Unsupported / ignored:
    * ``#include`` / ``#base`` preprocessor directives (localconfig doesn't use them)
    * conditionals like ``[$WIN32]``  (localconfig doesn't use them)
    * unquoted tokens                 (localconfig always quotes)

Comments (``// …`` to end of line) ARE handled — Steam sometimes writes them.
"""
from __future__ import annotations

from typing import Any


class VDFError(ValueError):
    """Raised on malformed VDF input."""


# ── loader ──────────────────────────────────────────────────────────
def loads(text: str) -> dict[str, Any]:
    """Parse a VDF string into a nested ``dict``."""
    parser = _Parser(text)
    root: dict[str, Any] = {}
    while True:
        parser.skip_ws()
        if parser.eof():
            break
        key = parser.read_string()
        parser.skip_ws()
        if parser.peek() != "{":
            raise VDFError(
                f"top-level key {key!r} must be followed by '{{' at pos {parser.pos}"
            )
        parser.advance()  # consume '{'
        root[key] = parser.read_block()
    return root


class _Parser:
    __slots__ = ("text", "pos")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def eof(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self) -> str:
        return "" if self.eof() else self.text[self.pos]

    def advance(self, n: int = 1) -> None:
        self.pos += n

    def skip_ws(self) -> None:
        # Skips whitespace + ``// line comments``.
        while not self.eof():
            c = self.text[self.pos]
            if c in " \t\r\n":
                self.pos += 1
                continue
            # comment?
            if c == "/" and self.pos + 1 < len(self.text) and self.text[self.pos + 1] == "/":
                nl = self.text.find("\n", self.pos)
                self.pos = len(self.text) if nl == -1 else nl + 1
                continue
            return

    def read_string(self) -> str:
        if self.peek() != '"':
            raise VDFError(f"expected '\"' at pos {self.pos}, got {self.peek()!r}")
        self.advance()
        out: list[str] = []
        while not self.eof():
            c = self.text[self.pos]
            if c == "\\" and self.pos + 1 < len(self.text):
                nxt = self.text[self.pos + 1]
                out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(nxt, nxt))
                self.pos += 2
                continue
            if c == '"':
                self.advance()
                return "".join(out)
            out.append(c)
            self.pos += 1
        raise VDFError("unterminated string")

    def read_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {}
        while True:
            self.skip_ws()
            if self.eof():
                raise VDFError("unexpected EOF inside block")
            if self.peek() == "}":
                self.advance()
                return block
            key = self.read_string()
            self.skip_ws()
            if self.peek() == "{":
                self.advance()
                block[key] = self.read_block()
            else:
                block[key] = self.read_string()


# ── writer ──────────────────────────────────────────────────────────
def dumps(data: dict[str, Any], *, indent: str = "\t") -> str:
    """Serialise a nested ``dict`` back into VDF text (Steam-compatible)."""
    lines: list[str] = []
    _emit(data, lines, depth=0, indent=indent)
    return "\n".join(lines) + "\n"


def _emit(node: dict[str, Any], lines: list[str], depth: int, indent: str) -> None:
    pad = indent * depth
    for key, value in node.items():
        if isinstance(value, dict):
            lines.append(f'{pad}"{_escape(key)}"')
            lines.append(f"{pad}{{")
            _emit(value, lines, depth + 1, indent)
            lines.append(f"{pad}}}")
        else:
            # Steam typically separates key & value with two tabs.
            lines.append(f'{pad}"{_escape(key)}"\t\t"{_escape(str(value))}"')


def _escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
         .replace("\n", "\\n")
         .replace("\t", "\\t")
    )
