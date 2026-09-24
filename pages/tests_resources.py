"""Training entries on the public Resources page are managed (add / edit /
hide / delete) by both the Admin and the Secretariat."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pages.models import ResourceDocument


class TrainingResourcesTests(TestCase):
    def setUp(self):
        U = get_user_model()
        mk = lambda email, role, **kw: U.objects.create_user(
            email=email, password="pw12345678!", first_name=role.title(), last_name="T", role=role, **kw)
        self.admin = mk("adm@x.org", "admin", is_staff=True, is_superuser=True)
        self.sec = mk("sec@x.org", "secretariat", is_staff=True)
        self.applicant = mk("app@x.org", "applicant")
        self.public = reverse("pages:resources")
        self.admin_url = reverse("admin_dashboard:resources_library")
        self.sec_url = reverse("secretariat_dashboard:resources_library")

    def training(self):
        return ResourceDocument.objects.filter(category="training")

    def add(self, url, **over):
        data = {"action": "add", "category": "training", "title": "New Module", "description": "About it",
                "badge_label": "Online course · 4 hrs", "icon": "bi-cpu",
                "external_url": "https://example.org/course", "display_order": "5", "tab": "all"}
        data.update(over)
        return self.client.post(url, data)

    def test_seeded_modules_show_without_fake_links(self):
        self.assertEqual(self.training().count(), 4)
        html = self.client.get(self.public).content.decode()
        for title in ("Foundations of Research Ethics", "Good Clinical Practice (GCP)",
                      "AI Ethics &amp; Responsible Research", "Data Protection &amp; Confidentiality"):
            self.assertIn(title, html)
        self.assertEqual(html.count("Link coming soon"), 4)
        self.assertNotIn('class="res-training-card" href="#"', html)

    def test_admin_and_secretariat_both_manage(self):
        for user, url in ((self.admin, self.admin_url), (self.sec, self.sec_url)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.add(url, title=f"By {user.role}").status_code, 302)
            item = self.training().get(title=f"By {user.role}")
            self.assertEqual((item.badge_label, item.icon, item.external_url), ("Online course · 4 hrs", "bi-cpu", "https://example.org/course"))
        html = self.client.get(self.public).content.decode()
        self.assertIn('href="https://example.org/course"', html)
        self.assertIn("Online course · 4 hrs", html)
        self.assertIn("bi-cpu", html)
        self.assertEqual(html.count("Link coming soon"), 4)

    def test_applicant_cannot_manage(self):
        self.client.force_login(self.applicant)
        for url in (self.admin_url, self.sec_url):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.add(url, title="Sneaky")
        self.assertFalse(self.training().filter(title="Sneaky").exists())

    def test_edit_hide_delete(self):
        self.client.force_login(self.sec)
        item = self.training().get(title="Foundations of Research Ethics")
        page = self.client.get(f"{self.sec_url}?tab=training&edit={item.pk}").content.decode()
        self.assertIn('value="edit"', page)
        self.assertIn("Foundations of Research Ethics", page)
        self.assertNotIn('id="resAddOverlay" hidden', page)
        self.client.post(self.sec_url, {"action": "edit", "resource_id": item.pk, "category": "training",
                                        "title": "Foundations (updated)", "description": "d", "badge_label": "3 hrs",
                                        "icon": "bi-book", "external_url": "https://learn.example.org/f", "display_order": "1"})
        item.refresh_from_db()
        self.assertEqual((item.title, item.icon, item.external_url), ("Foundations (updated)", "bi-book", "https://learn.example.org/f"))
        html = self.client.get(self.public).content.decode()
        self.assertIn('href="https://learn.example.org/f"', html)
        self.assertEqual(html.count("Link coming soon"), 3)
        # hide, then it disappears publicly
        self.client.post(self.sec_url, {"action": "toggle", "resource_id": item.pk})
        self.assertNotIn("Foundations (updated)", self.client.get(self.public).content.decode())
        # delete
        self.client.post(self.sec_url, {"action": "delete", "resource_id": item.pk})
        self.assertFalse(ResourceDocument.objects.filter(pk=item.pk).exists())

    def test_bad_links_and_input_rejected(self):
        self.client.force_login(self.admin)
        before = self.training().count()
        for bad in ("javascript:alert(1)", "ftp://x.org/f", "not a url"):
            self.add(self.admin_url, title="Bad", external_url=bad)
        self.add(self.admin_url, title="   ")
        self.add(self.admin_url, title="Bad cat", category="nope")
        self.assertEqual(self.training().count(), before)
        item = self.training().first()
        self.client.post(self.admin_url, {"action": "edit", "resource_id": item.pk, "category": "training", "title": "X", "external_url": "javascript:alert(1)"})
        item.refresh_from_db()
        self.assertNotEqual(item.title, "X")
        # unknown icon falls back to the default
        self.add(self.admin_url, title="Odd icon", icon="bi-evil\"><script>", external_url="")
        self.assertEqual(self.training().get(title="Odd icon").icon, "bi-mortarboard-fill")

    def test_all_hidden_shows_empty_message(self):
        ResourceDocument.objects.filter(category="training").update(is_published=False)
        html = self.client.get(self.public).content.decode()
        self.assertIn("Training modules will be listed here soon.", html)
        self.assertEqual(self.client.get(self.public).status_code, 200)
