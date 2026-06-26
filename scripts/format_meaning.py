"""
Python port of yanosh-k/bulgarian_dictionary's format_meaning() PHP function.

The upstream function lives in convertors/db_to_jsonl.php and transforms the
raw `meaning` markup stored in the Речко MySQL database into HTML fit for a
Kindle / KOReader / GoldenDict dictionary entry.

Source markup conventions in the database:

    #N           -> sense number (rendered as bold "N.")
    __text__     -> bold
    _text_       -> italic
    +abbr.       -> known abbreviation expanded into an <abbr title="..."> tag
                    (a handful of recognized prefixes; see ABBREVIATIONS below)
    +other.      -> any other "+xxx." token becomes italic xxx.
    `            -> combining acute accent (renders as &#768;)
    \n           -> line break (<br>)
    ----\n       -> horizontal rule (<hr>)
    *            -> bullet (•)
    [[w:Foo]]    -> link to Bulgarian Wikipedia article "Foo"
    [[Foo]]      -> cross-reference to dictionary entry "Foo" (or plain text
                    if no such entry exists)

A NOTE ON FIDELITY:

We replicate PHP's `strtr` semantics (simultaneous longest-match-first
replacement) using a single regex pass instead of Python's str.replace
chain, which would otherwise produce nested-replacement bugs (e.g. a
substitution introducing a `+` that the next pass mis-interprets).

The cross-reference resolver requires a map of {headword -> id}. Callers
build this once from the SQLite `word` table and pass it in.

Credits: see vendor/README.md and the project README.md.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Mapping


# Abbreviation map: source token -> rendered <abbr> tag.
ABBREVIATIONS: dict[str, str] = {
    "+мн.": '<abbr title="множествено число">мн.</abbr>',
    "+ед.": '<abbr title="единствено число">ед.</abbr>',
    "+м.": '<abbr title="мъжки род">м.</abbr>',
    "+ж.": '<abbr title="женски род">ж.</abbr>',
    "+ср.": '<abbr title="среден род">ср.</abbr>',
    "+мин. несв.": '<abbr title="минало несвършено време">мин. несв.</abbr>',
    "+мин. св.": '<abbr title="минало свършено време">мин. св.</abbr>',
    "+мин. прич.": '<abbr title="минало причастие">мин. прич.</abbr>',
    "+несв.": '<abbr title="несвършен вид">несв.</abbr>',
    "+св.": '<abbr title="свършен вид">св.</abbr>',
    "+същ.": '<abbr title="съществително име">същ.</abbr>',
    "+прил.": '<abbr title="прилагателно име">прил.</abbr>',
    "+Прен.": '<abbr title="В преносен смисъл">Прен.</abbr>',
    "+Пренебр.": '<abbr title="Пренебрежително">Пренебр.</abbr>',
    "+Разг.": '<abbr title="Разговорно">Разг.</abbr>',
    "+Спец.": '<abbr title="Специализирано">Спец.</abbr>',
    "+вж.": '<abbr title="виж">вж.</abbr>',
    "+мат.": '<abbr title="В математиката">мат.</abbr>',
    "+Филос.": '<abbr title="Във философията">Филос.</abbr>',
}

# Single-character substitutions performed in the same simultaneous pass as
# the abbreviations (so that, for example, `----\n` is recognized BEFORE
# `\n` alone, replicating PHP strtr's longest-key-first behavior).
SINGLE_CHAR_MAP: dict[str, str] = {
    "----\n": "<hr>",
    "\n": "<br>",
    "`": "&#768;",
    "*": "•",
}

# Combined map for the simultaneous pass. We build a regex whose alternatives
# are sorted longest-first so the regex engine commits to the longest possible
# match at each position - same semantic as PHP strtr.
_STRTR_MAP: dict[str, str] = {**ABBREVIATIONS, **SINGLE_CHAR_MAP}
_STRTR_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(_STRTR_MAP.keys(), key=len, reverse=True))
)


def _strtr(s: str) -> str:
    return _STRTR_RE.sub(lambda m: _STRTR_MAP[m.group(0)], s)


# --- Cross-reference / wiki link handling -----------------------------------

_WIKI_RE = re.compile(r"\[\[w:([^\]]+)\]\]")
_XREF_RE = re.compile(r"\[\[([^\]]+?)\]\]")


def _wiki_sub(m: "re.Match[str]") -> str:
    title = m.group(1)
    url = "https://bg.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    return f'<a href="{url}"><i>{title}</i> в Уикипедия</a>'


def _xref_sub_factory(word_id_map: Mapping[str, int]):
    def sub(m: "re.Match[str]") -> str:
        word_text = m.group(1).replace("&#768;", "")
        wid = word_id_map.get(word_text)
        if wid is not None:
            return f'<a href="#{wid}">{word_text}</a>'
        # PHP fallback: emit the original captured text (with accents stripped
        # is NOT what PHP does - it emits matches[1] verbatim, including any
        # accents). Match that exactly.
        return m.group(1)
    return sub


# --- Main entry point -------------------------------------------------------

def format_meaning(raw: str, word_id_map: Mapping[str, int] | None = None) -> str:
    """Render Речко raw meaning markup as HTML.

    If `word_id_map` is None, cross-references that resolve to a known word
    fall through to plain text (same as PHP when the word is unknown).
    """
    if raw is None:
        return ""
    s = raw

    # 1. Sense numbers: "#1" -> "<b>1.</b>"
    s = re.sub(r"#(\d+)", r"<b>\1.</b>", s)

    # 2. Bold markup: "__foo__" -> "<b>foo</b>"  (non-greedy via [^_]+)
    s = re.sub(r"__([^_]+)__", r"<b>\1</b>", s)

    # 3. Italic markup: "_foo_" -> "<i>foo</i>"
    s = re.sub(r"_([^_]+)_", r"<i>\1</i>", s)

    # 4. Simultaneous longest-match-first replacement of abbreviation tokens,
    #    line breaks, the acute accent and the bullet.
    s = _strtr(s)

    # 5. Italicize any leftover "+xxx." abbreviation that wasn't in the
    #    known list. PHP's /U makes the inner pattern non-greedy.
    s = re.sub(r"\+(\S[^.]+?\.)", r"<i>\1</i>", s)

    # 6. Wikipedia links: "[[w:Title]]"
    s = _WIKI_RE.sub(_wiki_sub, s)

    # 7. Cross-references: "[[word]]". Done LAST so wiki links (which also
    #    match this pattern) don't get clobbered.
    if word_id_map is not None:
        s = _XREF_RE.sub(_xref_sub_factory(word_id_map), s)
    else:
        # Strip the [[ ]] but keep the text inside (matches PHP behavior when
        # the word isn't in the map).
        s = _XREF_RE.sub(lambda m: m.group(1), s)

    return s
