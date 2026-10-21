"""Terms of Service / Privacy Policy: the safe markup, the public pages,
the footer's Help & Legal column, and editing them from Site Settings."""
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from pages import legal_markup
from pages.models import LegalPage, SiteSettings


class MarkupTests(TestCase):
    def test_html_is_escaped_never_run(self):
        html = legal_markup.render("<script>alert(1)</script> **bold**")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_blocks(self):
        html = legal_markup.render(
            "Intro line one\nline two\n\n### Sub\n- a\n- b\n\n1. first\n2. second\n\n> Careful\n\n| H1 | H2 |\n| x | y |"
        )
        self.assertIn("<p>Intro line one line two</p>", html)
        self.assertIn("<h4>Sub</h4>", html)
        self.assertIn("<ul><li>a</li><li>b</li></ul>", html)
        self.assertIn("<ol><li>first</li><li>second</li></ol>", html)
        self.assertIn('class="legal-note"', html)
        self.assertIn("<th>H1</th>", html)
        self.assertIn("<td>y</td>", html)

    def test_links(self):
        html = legal_markup.render(
            "[Contact](page:contact) [Policies](page:governance#gov-policies) [Ext](https://example.org) "
            "[Bad](javascript:alert(1)) [Nope](page:does_not_exist) write to a@b.org"
        )
        self.assertIn(f'<a href="{reverse("pages:contact")}">Contact</a>', html)
        self.assertIn(f'href="{reverse("pages:governance")}#gov-policies"', html)
        self.assertIn('href="https://example.org" target="_blank" rel="noopener"', html)
        self.assertNotIn("javascript:", html)
        self.assertIn("Bad", html)
        self.assertIn("Nope", html)
        self.assertIn('<a href="mailto:a@b.org">a@b.org</a>', html)

    def test_placeholders(self):
        html = legal_markup.render("Write to {email} at {site_name}.", {"email": "x@y.org", "site_name": "MSREC"})
        self.assertIn('<a href="mailto:x@y.org">x@y.org</a>', html)
        self.assertIn("MSREC", html)


class PublicPageTests(TestCase):
    def test_both_pages_render_their_default_content(self):
        terms = self.client.get(reverse("pages:terms"))
        self.assertContains(terms, "Terms of Service")
        self.assertContains(terms, "Workshops, training &amp; certificates")
        self.assertContains(terms, 'id="workshops-training-certificates"')
        privacy = self.client.get(reverse("pages:privacy"))
        self.assertContains(privacy, "Privacy Policy")
        self.assertContains(privacy, "Act 843")
        self.assertContains(privacy, "BMS / mNotify")
        # {email} filled from Site Settings.
        self.assertContains(privacy, SiteSettings.get_solo().contact_secretariat_email)

    def test_old_addresses_redirect(self):
        self.assertRedirects(self.client.get("/terms-of-use/"), reverse("pages:terms"), status_code=301)
        self.assertRedirects(self.client.get("/privacy-notice/"), reverse("pages:privacy"), status_code=301)

    def test_footer_has_help_and_legal_column(self):
        resp = self.client.get(reverse("pages:index"))
        self.assertContains(resp, "<h4>Help &amp; Legal</h4>", html=False)
        self.assertContains(resp, f'<a href="{reverse("pages:terms")}">Terms of Service</a>', html=True)
        self.assertContains(resp, f'<a href="{reverse("pages:privacy")}">Privacy Policy</a>', html=True)


class SettingsEditorTests(TestCase):
    def setUp(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123", first_name="Ada", last_name="Admin")
        self.client.force_login(admin)
        self.url = reverse("admin_dashboard:settings")

    def _save(self, **extra):
        data = {
            "action": "update_legal_page", "tab": "legal-pages", "slug": "terms",
            "nav_label": "Terms & Conditions", "eyebrow": "Legal", "headline": "Our terms, plainly.",
            "intro": "Hello.", "side_note": "", "version": "3.0", "meta_note": "Ghana",
            "last_updated": "2026-11-01", "cta_heading": "Questions?", "cta_text": "Ask us.",
            "sec_heading": ["Second thing", "First thing"],
            "sec_summary": ["", "**Short**"],
            "sec_body": ["- one\n- two", "Plain text."],
            "sec_note": ["", ""],
        }
        data.update(extra)
        return self.client.post(self.url, data, follow=True)

    def test_settings_page_shows_the_editor(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, 'data-target="legal-pages"')
        self.assertContains(resp, 'name="sec_heading"')
        self.assertContains(resp, "Acceptance of these Terms")

    def test_save_changes_every_part_of_the_page(self):
        self._save()
        page = LegalPage.objects.get(slug="terms")
        self.assertEqual([s["heading"] for s in page.sections], ["Second thing", "First thing"])
        self.assertEqual(str(page.last_updated), "2026-11-01")

        public = self.client.get(reverse("pages:terms"))
        self.assertContains(public, "Our terms, plainly.")
        self.assertContains(public, "1 November 2026")
        self.assertContains(public, "<li>one</li>", html=False)
        self.assertContains(public, "<strong>Short</strong>", html=False)
        body = public.content.decode()
        self.assertLess(body.index("Second thing"), body.index("First thing"))
        # The footer link follows the new page name.
        self.assertContains(self.client.get(reverse("pages:index")), "Terms &amp; Conditions")

    def test_section_without_heading_is_refused(self):
        self._save(sec_heading=["", "First"], sec_body=["Some text", "x"], sec_summary=["", ""], sec_note=["", ""])
        self.assertNotEqual(LegalPage.get("terms").headline, "Our terms, plainly.")

    def test_reset_restores_the_original_wording(self):
        self._save()
        self.client.post(self.url, {"action": "reset_legal_page", "tab": "legal-pages", "slug": "terms"})
        page = LegalPage.objects.get(slug="terms")
        self.assertEqual(page.nav_label, "Terms of Service")
        self.assertEqual(page.sections[0]["heading"], "Acceptance of these Terms")

    def test_footer_heading_is_editable(self):
        self.client.post(self.url, {"action": "update_legal_footer", "tab": "legal-pages", "footer_legal_heading": "Policies"})
        self.assertContains(self.client.get(reverse("pages:index")), "<h4>Policies</h4>", html=False)
