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
        # [[word]] becomes a bword:// link when the word exists in the
        # known-words set. The Cyrillic word is embedded literally - KOReader
        # treats the bword:// target as a lookup string, not a URL, so we
        # must NOT percent-encode it.
        raw = "Виж [[абсолют]]."
        expected = 'Виж <a href="bword://абсолют">абсолют</a>.'
        self.assertEqual(format_meaning(raw, {"абсолют"}), expected)

    def test_xref_missing_word(self):
        # When the xref target isn't in the dictionary, emit plain text -
        # no link, no broken anchor.
        raw = "Виж [[несъществуваща]]."
        expected = "Виж несъществуваща."
        self.assertEqual(format_meaning(raw, set()), expected)

    def test_xref_with_accent_stripped_for_lookup(self):
        # In the raw DB markup, accents are written as backticks (`). They
        # get converted to &#768; by the strtr pass. The cross-reference
        # resolver runs AFTER that and strips &#768; both for the lookup
        # key AND for the rendered link text.
        raw = "Виж [[а`з]]."
        expected = 'Виж <a href="bword://аз">аз</a>.'
        self.assertEqual(format_meaning(raw, {"аз"}), expected)

    def test_xref_multiword_with_space(self):
        # Bulgarian reflexive verbs include a space (e.g. "боричкам се").
        # Spaces inside an HTML attribute value are valid as-is when the
        # value is quoted; we must not URL-encode them.
        raw = "Виж [[боричкам се]]."
        expected = 'Виж <a href="bword://боричкам се">боричкам се</a>.'
        self.assertEqual(format_meaning(raw, {"боричкам се"}), expected)

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
