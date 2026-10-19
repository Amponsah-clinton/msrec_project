"""Tests for institution naming and list upkeep (pages/institutions.py) --
the "Other (not listed)" box on every Institution dropdown."""
from django.test import TestCase

from pages import institutions
from pages.models import Institution


class TitleCaseTests(TestCase):
    def test_capitalizes_each_word(self):
        self.assertEqual(institutions.title_case("university of ghana"), "University Of Ghana")

    def test_collapses_whitespace(self):
        self.assertEqual(institutions.title_case("  komfo   anokye  "), "Komfo Anokye")

    def test_caps_lock_is_title_cased(self):
        self.assertEqual(institutions.title_case("UNIVERSITY OF GHANA"), "University Of Ghana")

    def test_lone_acronym_is_left_alone(self):
        self.assertEqual(institutions.title_case("KNUST"), "KNUST")

    def test_acronyms_and_mixed_case_words_are_left_alone(self):
        self.assertEqual(
            institutions.title_case("University of Ghana, KNUST"), "University Of Ghana, KNUST"
        )
        self.assertEqual(institutions.title_case("McDonald clinic"), "McDonald Clinic")

    def test_a_word_shouted_in_full_is_not_an_acronym(self):
        self.assertEqual(
            institutions.title_case("korle bu TEACHING hospital"),
            "Korle Bu Teaching Hospital",
        )

    def test_hyphens_and_apostrophes(self):
        self.assertEqual(
            institutions.title_case("kwame-nkrumah university"), "Kwame-Nkrumah University"
        )
        self.assertEqual(institutions.title_case("o'brien institute"), "O'Brien Institute")
        # A possessive is not a new word: "Mary's", never "Mary'S".
        self.assertEqual(institutions.title_case("st mary's hospital"), "St Mary's Hospital")

    def test_blank(self):
        self.assertEqual(institutions.title_case("   "), "")
        self.assertEqual(institutions.title_case(None), "")


class CanonicalNameTests(TestCase):
    def setUp(self):
        Institution.objects.create(name="University of Ghana", is_active=True)

    def test_existing_institution_keeps_the_lists_spelling(self):
        self.assertEqual(
            institutions.canonical_name("  university   of ghana "), "University of Ghana"
        )

    def test_new_institution_is_title_cased(self):
        self.assertEqual(
            institutions.canonical_name("korle bu teaching hospital"),
            "Korle Bu Teaching Hospital",
        )

    def test_clipped_to_the_column_width(self):
        self.assertEqual(
            len(institutions.canonical_name("a" * 400)), institutions.MAX_NAME_LENGTH
        )


class ResolveChoiceTests(TestCase):
    def test_other_takes_the_typed_value(self):
        self.assertEqual(
            institutions.resolve_choice(institutions.OTHER_VALUE, "ho teaching hospital"),
            "Ho Teaching Hospital",
        )

    def test_a_value_promoted_into_the_dropdown_still_resolves(self):
        # The page's own script Title-Cases what was typed, adds it to the
        # dropdown and selects it -- so the select, not the box, carries it.
        self.assertEqual(
            institutions.resolve_choice("Ho Teaching Hospital", ""), "Ho Teaching Hospital"
        )

    def test_nothing_chosen(self):
        self.assertEqual(institutions.resolve_choice("", ""), "")
        self.assertEqual(institutions.resolve_choice(institutions.OTHER_VALUE, "  "), "")


class RegisterTests(TestCase):
    def test_adds_a_new_institution_in_title_case(self):
        institutions.register(["ho teaching hospital"])
        self.assertTrue(Institution.objects.filter(name="Ho Teaching Hospital", is_active=True).exists())

    def test_never_duplicates_an_existing_name(self):
        Institution.objects.create(name="University of Ghana", is_active=True)
        institutions.register(["UNIVERSITY OF GHANA", "university of ghana", ""])
        self.assertEqual(Institution.objects.filter(name__icontains="ghana").count(), 1)

    def test_blank_names_are_ignored(self):
        institutions.register(["", "   ", None])
        self.assertEqual(Institution.objects.count(), 0)

    def test_registered_names_are_offered_by_the_dropdown(self):
        institutions.register(["ho teaching hospital"])
        self.assertIn("Ho Teaching Hospital", [i.name for i in institutions.active()])
