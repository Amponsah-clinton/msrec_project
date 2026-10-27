"""Professional Service Agreements: staff prepare, sign and send; the client
completes their part and signs through a private link."""
import base64
from decimal import Decimal
from io import BytesIO

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import User
from notifications.models import Notification

from .models import ServiceAgreement

Status = ServiceAgreement.Status


def _drawn_signature():
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(40, 150), (200, 60), (360, 140), (560, 50)], fill=(27, 42, 92, 255), width=6)
    out = BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def _form(**overrides):
    today = timezone.localdate()
    data = {
        "agreement_date": today.isoformat(),
        "client_name": "Kwame Mensah",
        "client_email": "kwame@example.com",
        "client_phone": "0241234567",
        "client_address": "",
        "start_date": today.isoformat(),
        "completion_date": (today + timezone.timedelta(days=30)).isoformat(),
        "service_title": "Systematic review support",
        "deliverables": ["Search strategy", "", "Screening of records", "  "],
        "currency": "GHS",
        "fee": "2,500",
        "payment_basis": "milestone",
        "payment_basis_other": "",
        "deposit": "1000",
        "payment_schedule": "Deposit on signing; balance on delivery.",
        "company_signature_kind": "typed",
        "company_signature_typed": "Ada Admin",
        "company_signature_drawn": "",
        "action": "send",
    }
    data.update(overrides)
    return data


def _client_form(**overrides):
    data = {
        "client_name": "Kwame Mensah", "client_email": "kwame@example.com",
        "client_phone": "+233 24 123 4567", "client_address": "Accra",
        "accept": "yes", "client_signature_kind": "typed", "client_signature_typed": "Kwame Mensah",
        "client_signature_drawn": "",
    }
    data.update(overrides)
    return data


class StaffTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123", first_name="Ada", last_name="Admin",
        )
        self.client.force_login(self.admin)

    def _sent(self, **overrides):
        self.client.post(reverse("psa_admin:psa_new"), _form(**overrides))
        return ServiceAgreement.objects.latest("pk")


class AccessTests(TestCase):
    def test_only_admin_and_secretariat(self):
        url = reverse("psa_admin:psa_list")
        self.assertEqual(self.client.get(url).status_code, 302)

        applicant = User.objects.create_user(email="app@example.com", password="pw-12345678",
                                             first_name="A", last_name="P", role=User.Role.APPLICANT)
        self.client.force_login(applicant)
        self.assertEqual(self.client.get(url).status_code, 302)

        sec = User.objects.create_user(email="sec@example.com", password="pw-12345678",
                                       first_name="Sam", last_name="Sec", role=User.Role.SECRETARIAT)
        self.client.force_login(sec)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["dashboard"], "secretariat")
        # The Secretariat sidebar's PSA entry is the highlighted one.
        self.assertContains(resp, f'href="{url}" class="nav-item active"')

    def test_admin_sidebar_has_psa(self):
        admin = User.objects.create_superuser(email="a@example.com", password="pw-12345678", first_name="A", last_name="B")
        self.client.force_login(admin)
        resp = self.client.get(reverse("admin_dashboard:home"))
        self.assertContains(resp, reverse("psa_admin:psa_list"))


class CreateAndSendTests(StaffTestCase):
    def test_draft_needs_only_a_client_name(self):
        resp = self.client.post(reverse("psa_admin:psa_new"), {"client_name": "Draft Client", "action": "draft"})
        a = ServiceAgreement.objects.get()
        self.assertRedirects(resp, reverse("psa_admin:psa_detail", args=[a.pk]))
        self.assertEqual(a.status, Status.DRAFT)
        self.assertRegex(a.reference, rf"^PSA-{timezone.localdate().year}-0*{a.pk}$")
        self.assertEqual(len(mail.outbox), 0)

    def test_each_agreement_gets_its_own_reference_and_link(self):
        for name in ("One", "Two"):
            self.client.post(reverse("psa_admin:psa_new"), {"client_name": name, "action": "draft"})
        a, b = ServiceAgreement.objects.order_by("pk")
        self.assertNotEqual(a.reference, b.reference)
        self.assertNotEqual(a.token, b.token)
        self.assertGreaterEqual(len(a.token), 40)

    def test_sign_and_send(self):
        a = self._sent()
        self.assertEqual(a.status, Status.SENT)
        self.assertEqual(a.deliverables, ["Search strategy", "Screening of records"])
        self.assertEqual(a.fee, Decimal("2500.00"))
        self.assertEqual(a.balance, Decimal("1500.00"))
        # The company's side is filled in automatically.
        self.assertEqual(a.company_signature_kind, "typed")
        self.assertEqual(a.company_signatory_name, "Ada Admin")
        self.assertEqual(a.company_signatory_role, "Administrator")
        self.assertIsNotNone(a.company_signed_at)
        self.assertEqual(a.send_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["kwame@example.com"])
        self.assertIn(a.reference, mail.outbox[0].subject)
        self.assertIn(reverse("psa:client", args=[a.token]), mail.outbox[0].body)

    def test_drawn_signature_is_stored_as_png(self):
        a = self._sent(company_signature_kind="drawn", company_signature_typed="",
                       company_signature_drawn=_drawn_signature())
        self.assertEqual(a.company_signature_kind, "drawn")
        self.assertTrue(a.company_signature.startswith("data:image/png;base64,"))

    def test_sending_needs_everything(self):
        cases = {
            "email": {"client_email": ""},
            "title": {"service_title": ""},
            "deliverables": {"deliverables": ["", " "]},
            "fee": {"fee": ""},
            "basis": {"payment_basis": ""},
            "other basis": {"payment_basis": "other", "payment_basis_other": ""},
            "schedule": {"payment_schedule": ""},
            "start": {"start_date": ""},
            "dates order": {"completion_date": "2000-01-01"},
            "deposit over fee": {"deposit": "9000"},
            "signature": {"company_signature_typed": ""},
            "bad email": {"client_email": "kwame@"},
            "bad fee": {"fee": "lots"},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                resp = self.client.post(reverse("psa_admin:psa_new"), _form(**overrides))
                self.assertEqual(resp.status_code, 400)
                self.assertFalse(ServiceAgreement.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_save_keeps_what_was_typed(self):
        resp = self.client.post(reverse("psa_admin:psa_new"), _form(service_title=""))
        self.assertContains(resp, "Search strategy", status_code=400)
        self.assertContains(resp, "Kwame Mensah", status_code=400)

    def test_send_a_finished_draft_from_its_page(self):
        a = self._sent(action="draft")
        self.assertEqual(a.status, Status.DRAFT)
        self.client.post(reverse("psa_admin:psa_send", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.status, Status.SENT)
        self.assertEqual(len(mail.outbox), 1)

    def test_unsigned_draft_cant_be_sent(self):
        a = self._sent(action="draft", company_signature_typed="")
        resp = self.client.post(reverse("psa_admin:psa_send", args=[a.pk]))
        self.assertRedirects(resp, reverse("psa_admin:psa_edit", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.status, Status.DRAFT)

    def test_edit_keeps_signature_and_resend_counts(self):
        a = self._sent()
        self.client.post(reverse("psa_admin:psa_edit", args=[a.pk]),
                         _form(fee="3000", company_signature_typed="", action="draft"))
        a.refresh_from_db()
        self.assertEqual(a.fee, Decimal("3000.00"))
        self.assertEqual(a.status, Status.SENT)
        self.assertEqual(a.company_signature, "Ada Admin")
        self.client.post(reverse("psa_admin:psa_resend", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.send_count, 2)
        self.assertIn("Reminder", mail.outbox[-1].subject)

    def test_pages_render(self):
        a = self._sent()
        for url in (reverse("psa_admin:psa_list"), reverse("psa_admin:psa_new"),
                    reverse("psa_admin:psa_detail", args=[a.pk]), reverse("psa_admin:psa_edit", args=[a.pk])):
            with self.subTest(url):
                self.assertEqual(self.client.get(url).status_code, 200)


class ClientSigningTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.a = self._sent()
        self.url = reverse("psa:client", args=[self.a.token])
        mail.outbox.clear()

    def test_draft_link_is_not_found(self):
        draft = self._sent(action="draft")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("psa:client", args=[draft.token])).status_code, 404)

    def test_opening_is_recorded(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertContains(resp, "Accept &amp; sign agreement")
        self.assertEqual(resp["Cache-Control"], "no-store")
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.viewed_at)

    def test_client_must_complete_their_part(self):
        self.client.logout()
        cases = {
            "name": {"client_name": ""},
            "phone": {"client_phone": ""},
            "short phone": {"client_phone": "024"},
            "email": {"client_email": "nope"},
            "acceptance": {"accept": ""},
            "signature": {"client_signature_typed": ""},
            "broken drawing": {"client_signature_kind": "drawn", "client_signature_drawn": "data:image/png;base64,???"},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                resp = self.client.post(self.url, _client_form(**overrides))
                self.assertEqual(resp.status_code, 400)
                self.a.refresh_from_db()
                self.assertEqual(self.a.status, Status.SENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_signing(self):
        self.client.logout()
        resp = self.client.post(self.url, _client_form(client_signature_kind="drawn", client_signature_typed="",
                                                       client_signature_drawn=_drawn_signature()),
                                REMOTE_ADDR="203.0.113.9")
        self.assertRedirects(resp, self.url)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SIGNED)
        self.assertEqual(self.a.client_signature_kind, "drawn")
        self.assertEqual(self.a.client_phone, "+233 24 123 4567")
        self.assertEqual(self.a.client_address, "Accra")
        self.assertEqual(self.a.client_signed_ip, "203.0.113.9")
        # A copy to the client, and word to the CEO and the staff member who sent it.
        self.assertEqual(len(mail.outbox), 2)
        client_copy, staff = sorted(mail.outbox, key=lambda m: m.to[0] != "kwame@example.com")
        self.assertEqual(client_copy.to, ["kwame@example.com"])
        self.assertEqual(staff.to, ["ceo@academicdigital.space", "admin@example.com"])
        self.assertIn("Kwame Mensah", staff.subject)
        self.assertTrue(Notification.objects.filter(link_url_name="psa_admin:psa_detail").exists())
        # The signed copy shows, without a form.
        page = self.client.get(self.url)
        self.assertContains(page, "Your signed agreement")
        self.assertNotContains(page, 'id="psaClientForm"')

    def test_signed_agreement_is_locked(self):
        self.client.post(self.url, _client_form())
        before = ServiceAgreement.objects.get(pk=self.a.pk)
        # A second submission changes nothing.
        self.client.post(self.url, _client_form(client_name="Someone Else"))
        self.a.refresh_from_db()
        self.assertEqual(self.a.client_name, before.client_name)
        # Staff can no longer edit or cancel it.
        resp = self.client.post(reverse("psa_admin:psa_edit", args=[self.a.pk]), _form(fee="1"))
        self.assertRedirects(resp, reverse("psa_admin:psa_detail", args=[self.a.pk]))
        self.client.post(reverse("psa_admin:psa_cancel", args=[self.a.pk]))
        self.client.post(reverse("psa_admin:psa_delete", args=[self.a.pk]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SIGNED)
        self.assertEqual(self.a.fee, Decimal("2500.00"))

    def test_cancelled_link_cannot_be_signed(self):
        self.client.post(reverse("psa_admin:psa_cancel", args=[self.a.pk]))
        self.client.logout()
        self.client.post(self.url, _client_form())
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CANCELLED)
        self.assertContains(self.client.get(self.url), "withdrawn")


class ListTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.one = self._sent(client_name="Abena Owusu", client_email="abena@example.com", service_title="Data analysis")
        self.two = self._sent(client_name="Yaw Boateng", client_email="yaw@example.com", action="draft", currency="USD")
        self.url = reverse("psa_admin:psa_list")

    def test_search_and_filters(self):
        resp = self.client.get(self.url, {"q": "abena"})
        self.assertEqual([a.pk for a in resp.context["page"]], [self.one.pk])
        resp = self.client.get(self.url, {"q": self.two.reference})
        self.assertEqual([a.pk for a in resp.context["page"]], [self.two.pk])
        resp = self.client.get(self.url, {"status": "draft"})
        self.assertEqual([a.pk for a in resp.context["page"]], [self.two.pk])
        resp = self.client.get(self.url, {"currency": "GHS"})
        self.assertEqual([a.pk for a in resp.context["page"]], [self.one.pk])
        resp = self.client.get(self.url, {"sort": "client"})
        self.assertEqual([a.pk for a in resp.context["page"]], [self.one.pk, self.two.pk])
        self.assertEqual(resp.context["stats"]["all"], 2)

    def test_export_follows_filters(self):
        resp = self.client.get(reverse("psa_admin:psa_export"), {"status": "sent"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        body = resp.content.decode("utf-8-sig")
        lines = body.strip().splitlines()
        self.assertTrue(lines[0].startswith("Reference,Status"))
        self.assertEqual(len(lines), 2)
        self.assertIn(self.one.reference, body)
        self.assertIn("1. Search strategy | 2. Screening of records", body)
        self.assertNotIn(self.two.reference, body)
