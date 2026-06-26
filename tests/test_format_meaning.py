"""
Golden-output tests for scripts/format_meaning.py.

Each case takes a raw `meaning` string straight from the Речко database and
asserts that our Python format_meaning() produces the same HTML as
yanosh-k's PHP convertor produced when run against the same database.

The expected outputs were extracted from the upstream OPF/HTML files
(bulgarian_dictionary/opf/bulgarian_dictionary*.html in the yanosh-k
repo at commit 18fcad7f, generated 2023-09-27). They are the source of
truth for "what should format_meaning render."
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].joinpath("scripts")))

from format_meaning import format_meaning  # noqa: E402


class FormatMeaningTests(unittest.TestCase):
    # Sense numbers + abbreviation + italic + accent + line break:
    def test_simple_entry(self):
        # 'абсолют' - the cleanest case, no markup at all
        raw = "Вечната, неизменна, безкрайна първопричина на вселената, която е синоним на Бог."
        expected = "Вечната, неизменна, безкрайна първопричина на вселената, която е синоним на Бог."
        self.assertEqual(format_meaning(raw), expected)

    def test_abbreviation_and_accent(self):
        # 'автогол' opening: '+мн. автого`лове, (два) автого`ла, +м.\n#1 +Спец. ...'
        raw = "+мн. автого`лове, (два) автого`ла, +м.\n#1 +Спец. Гол."
        expected = (
            '<abbr title="множествено число">мн.</abbr> '
            'автого&#768;лове, (два) автого&#768;ла, '
            '<abbr title="мъжки род">м.</abbr><br>'
            '<b>1.</b> <abbr title="Специализирано">Спец.</abbr> Гол.'
        )
        self.assertEqual(format_meaning(raw), expected)

    def test_italic_from_underscores(self):
        # _foo_ -> <i>foo</i>
        raw = "Този пример _подчертава_ нещо."
        expected = "Този пример <i>подчертава</i> нещо."
        self.assertEqual(format_meaning(raw), expected)

    def test_bold_from_double_underscores(self):
        raw = "__удебелена__ част."
        expected = "<b>удебелена</b> част."
        self.assertEqual(format_meaning(raw), expected)

    def test_unknown_plus_abbreviation_becomes_italic(self):
        # '+съюз.' is NOT in the known abbreviation list, so it falls into
        # the generic "+xxx." italicizer.
        raw = "+съюз.\n#1 За съпоставяне."
        expected = "<i>съюз.</i><br><b>1.</b> За съпоставяне."
        self.assertEqual(format_meaning(raw), expected)

    def test_hr_before_br(self):
        # '----\n' must beat '\n' to produce <hr>, not <br><br><br><br><br>.
        raw = "Преди\n----\nСлед"
        expected = "Преди<br><hr>След"
        self.assertEqual(format_meaning(raw), expected)

    def test_longest_abbreviation_wins(self):
        # '+мин. несв.' (longer) must beat '+несв.' (substring of nothing here,
        # but the bigger phrase must match completely).
        raw = "+мин. несв. форма."
        expected = '<abbr title="минало несвършено време">мин. несв.</abbr> форма.'
        self.assertEqual(format_meaning(raw), expected)

    def test_bullet_asterisk(self):
        raw = "* нещо."
        expected = "• нещо."
        self.assertEqual(format_meaning(raw), expected)

    def test_xref_existing_word(self):
        raw = "Виж [[абсолют]]."
        expected = 'Виж <a href="#29556">абсолют</a>.'
        self.assertEqual(format_meaning(raw, {"абсолют": 29556}), expected)

    def test_xref_missing_word(self):
        # PHP falls back to the matched text verbatim when the word isn't in
        # the map.
        raw = "Виж [[несъществуваща]]."
        expected = "Виж несъществуваща."
        self.assertEqual(format_meaning(raw, {}), expected)

    def test_xref_with_accent_stripped_for_lookup(self):
        # In the raw DB markup, accents are written as backticks (`). They
        # get converted to &#768; by the strtr pass. The cross-reference
        # resolver runs AFTER that and strips &#768; both for the lookup
        # key AND for the rendered link text (matching upstream PHP, which
        # does $wordText = str_replace('&#768;', '', ...) and then uses
        # $wordText for both purposes).
        raw = "Виж [[а`з]]."
        expected = 'Виж <a href="#42">аз</a>.'
        self.assertEqual(format_meaning(raw, {"аз": 42}), expected)

    def test_wiki_link(self):
        raw = "Виж [[w:Платон]] за повече."
        out = format_meaning(raw)
        # urlencoding of 'Платон' to %-form is deterministic
        self.assertIn('href="https://bg.wikipedia.org/wiki/', out)
        self.assertIn("в Уикипедия", out)
        self.assertIn("<i>Платон</i>", out)

    def test_empty_meaning(self):
        self.assertEqual(format_meaning(""), "")

    def test_none_meaning(self):
        self.assertEqual(format_meaning(None), "")

    def test_multiple_sense_numbers(self):
        raw = "#1 Първо.\n#2 Второ."
        expected = "<b>1.</b> Първо.<br><b>2.</b> Второ."
        self.assertEqual(format_meaning(raw), expected)


if __name__ == "__main__":
    unittest.main()
