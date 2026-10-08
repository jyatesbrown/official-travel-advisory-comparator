from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

_WHITESPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)])")
_APOSTROPHES = re.compile(r"[\u2019\u2018'`\u00b4\u02bc]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TOKEN_REWRITES = {"st": "saint"}
_BLOCK_TAGS = frozenset(
    {"p", "li", "ul", "ol", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "table", "tr", "td"}
)


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text).replace("\u00a0", " ").replace("\u200b", "")
    return _SPACE_BEFORE_PUNCT.sub(r"\1", _WHITESPACE.sub(" ", text)).strip()


def html_to_text(fragment: str | None) -> str:
    if not fragment:
        return ""
    return element_text(BeautifulSoup(fragment, "lxml"))


def element_text(element: Tag) -> str:
    """Visible text of one block element. Inline tags are joined without extra spaces so that
    markup such as "<b>a</b>rbitrary" stays one word; block children are space-separated."""
    pieces: list[str] = []
    for node in element.descendants:
        if isinstance(node, NavigableString) and not isinstance(node, Comment):
            pieces.append(str(node))
        elif isinstance(node, Tag) and node.name in _BLOCK_TAGS:
            pieces.append(" ")
    return clean("".join(pieces))


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_key(text: str) -> str:
    """Normalise a destination name for exact dictionary lookup.

    Case, accents, apostrophes, punctuation, "&" vs "and", "St" vs "Saint" and a leading
    "the" are all ignored, so "trinidad & tobago" and "Trinidad and Tobago" share a key.
    """
    text = strip_accents(text).casefold().replace("&", " and ")
    text = _APOSTROPHES.sub("", text)
    tokens = _NON_ALNUM.sub(" ", text).split()
    tokens = [_TOKEN_REWRITES.get(token, token) for token in tokens]
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(tokens)
