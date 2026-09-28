from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts import suspension
from accounts.models import AuditLog, User
from pages.models import SuspensionLetterTemplate


class SuspensionLetterTests(TestCase):
    """Suspending / banning from Accounts: the typed reason is saved, the
    account holder is emailed with the letter attached, and the letter can
    be previewed, fit-checked and downloaded again."""

    def setUp(self):
        self.admin = User.objects.create_user(
            "admin@example.com", "pw-Admin#123", first_name="Ada", last_name="Admin", role=User.Role.ADMIN,
        )
        self.secretariat = User.objects.create_user(
            "sec@example.com", "pw-Sec#123", first_name="Sam", last_name="Sec", role=User.Role.SECRETARIAT,
        )
        self.target = User.objects.create_user(
            "kofi@example.com", "pw-Kofi#123", first_name="Kofi", last_name="Mensah",
            institution="University of Ghana",
        )
        self.url = reverse("admin_dashboard:accounts")

    def _suspend(self, **extra):
        data = {"action": "suspend", "user_id": self.target.pk, "suspension_kind": "suspend",
                "reason": "Shared confidential protocol documents outside the Committee.\n\nSecond paragraph."}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_suspend_saves_reason_and_emails_letter(self):
        self.client.force_login(self.admin)
        self._suspend()
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.target.suspension_kind, "suspend")
        self.assertIn("Second paragraph.", self.target.suspension_reason)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["kofi@example.com"])
        self.assertIn("suspended", message.subject)
        self.assertIn("Shared confidential protocol documents", message.body)
        (name, content, mimetype), = message.attachments
        self.assertEqual(mimetype, "application/pdf")
        self.assertTrue(name.startswith("MSREC-Notice-of-Suspension-"))
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertTrue(AuditLog.objects.filter(action="user.suspended").exists())

    def test_accounts_pages_render_suspend_dialog(self):
        for user, url_name in ((self.admin, "admin_dashboard:accounts"),
                               (self.secretariat, "secretariat_dashboard:users_access")):
            self.client.force_login(user)
            response = self.client.get(reverse(url_name) + "?tab=all")
            self.assertContains(response, 'id="acctSuspendOverlay"')
            self.assertContains(response, "data-acct-suspend")

    def test_ban_by_secretariat(self):
        self.client.force_login(self.secretariat)
        self._suspend(suspension_kind="ban")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.target.suspension_kind, "ban")
        self.assertIn("permanently withdrawn", mail.outbox[0].subject)
        self.assertTrue(mail.outbox[0].attachments[0][0].startswith("MSREC-Notice-of-Account-Withdrawal-"))

    def test_reason_is_required(self):
        self.client.force_login(self.admin)
        self._suspend(reason="   ")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(len(mail.outbox), 0)

    def test_letter_download_for_non_member(self):
        self.client.force_login(self.admin)
        self._suspend()
        response = self.client.get(reverse("admin_dashboard:suspension_notice_download", args=[self.target.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_preview_and_fit_check(self):
        self.client.force_login(self.secretariat)
        data = {"user_id": self.target.pk, "suspension_kind": "ban", "reason": "A short reason."}
        preview = self.client.post(reverse("admin_dashboard:suspension_letter_preview"), data)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.content.startswith(b"%PDF"))
        fit = self.client.post(reverse("admin_dashboard:suspension_letter_fit"), data).json()
        self.assertEqual(fit["pages"], 1)
        self.assertEqual(fit["scale"], 1.0)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)  # previewing never suspends

    def test_long_reason_is_shrunk_onto_one_page(self):
        from pages.models import SiteSettings

        reason = "\n".join(f"- Finding {i}: protocol documents were shared outside the Committee." for i in range(19))
        content = suspension.letter_content(self.target, kind="suspend", reason=reason)
        _pdf, full_size_pages = suspension._build(self.target, content, None, None, SiteSettings.get_solo(), 1.0)
        self.assertGreater(full_size_pages, 1)  # precondition: too long at full size
        _pdf, pages, scale = suspension.render_letter(self.target, kind="suspend", reason=reason)
        self.assertEqual(pages, 1)
        self.assertLess(scale, 1.0)

    def test_reason_placed_where_template_says(self):
        content = suspension.letter_content(self.target, kind="suspend", reason="Line one\nLine two\n\nPara two")
        boxes = [item for kind, item in content["body"] if kind == "reason"]
        self.assertEqual(boxes, [[["Line one", "Line two"], ["Para two"]]])

    def test_reason_appended_when_template_omits_placeholder(self):
        template = SuspensionLetterTemplate.get_solo()
        template.suspend_body = "Your account ({email}) is suspended."
        template.save()
        content = suspension.letter_content(self.target, kind="suspend", reason="Because.")
        self.assertEqual(content["body"][0], ("text", "Your account (kofi@example.com) is suspended."))
        self.assertEqual(content["body"][-1], ("reason", [["Because."]]))


class SuspensionLetterSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin@example.com", "pw-Admin#123", role=User.Role.ADMIN)
        self.url = reverse("admin_dashboard:settings")

    def test_settings_page_renders_tab(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, 'id="suspension-letter"')
        self.assertContains(response, "{reason}")

    def test_save_wording_and_signatory(self):
        self.client.force_login(self.admin)
        data = {"action": "update_suspension_template", "tab": "suspension-letter", **SuspensionLetterTemplate.DEFAULTS}
        data["suspend_subject"] = "RE: ACCOUNT SUSPENSION"
        self.client.post(self.url, data)
        self.client.post(self.url, {"action": "update_suspension_signatory", "sign_name": "Mrs. Abena Osei",
                                    "sign_title": "Secretary to the Committee"})
        template = SuspensionLetterTemplate.get_solo()
        self.assertEqual(template.suspend_subject, "RE: ACCOUNT SUSPENSION")
        self.assertEqual(template.sign_name, "Mrs. Abena Osei")
        self.assertEqual(template.sign_title, "Secretary to the Committee")
        sign = suspension.signatory(template)
        self.assertEqual((sign["name"], sign["title"]), ("Mrs. Abena Osei", "Secretary to the Committee"))

    def test_template_preview(self):
        self.client.force_login(self.admin)
        for kind in ("suspend", "ban"):
            response = self.client.get(reverse("admin_dashboard:suspension_template_preview", args=[kind]))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b"%PDF"))
