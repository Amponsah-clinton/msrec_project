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
        "client_signature_kind": "typed", "client_signature_typed": "Kwame Mensah",
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

    def test_balance_is_filled_in_on_load(self):
        a = self._sent(fee="300", deposit="100")
        resp = self.client.get(reverse("psa_admin:psa_edit", args=[a.pk]))
        self.assertEqual(resp.context["balance"], "GHS 200.00")
        self.assertContains(resp, 'value="GHS 200.00"')
        # Shown again after a failed save, from what was typed.
        resp = self.client.post(reverse("psa_admin:psa_new"), _form(fee="1,250", deposit="250", service_title=""))
        self.assertEqual(resp.context["balance"], "GHS 1,000.00")
        resp = self.client.post(reverse("psa_admin:psa_new"), _form(fee="100", deposit="900", service_title=""))
        self.assertEqual(resp.context["balance"], "Deposit is more than the fee")

    def test_scripts_carry_a_version(self):
        resp = self.client.get(reverse("psa_admin:psa_new"))
        self.assertRegex(resp.content.decode(), r"dashboard/js/psa-form\.js\?v=\d+")

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

    def test_client_must_give_name_phone_and_signature(self):
        self.client.logout()
        cases = {
            "name": {"client_name": "  "},
            "phone": {"client_phone": ""},
            "short phone": {"client_phone": "024"},
            "typed signature": {"client_signature_typed": ""},
            "drawn signature": {"client_signature_kind": "drawn", "client_signature_typed": "", "client_signature_drawn": ""},
            "no signature at all": {"client_signature_kind": "", "client_signature_typed": ""},
            "broken drawing": {"client_signature_kind": "drawn", "client_signature_drawn": "data:image/png;base64,???"},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                resp = self.client.post(self.url, _client_form(**overrides))
                self.assertEqual(resp.status_code, 400)
                self.a.refresh_from_db()
                self.assertEqual(self.a.status, Status.SENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_only_those_three_are_needed(self):
        # No address, no email, no tick box: name, phone and signature sign it.
        self.client.logout()
        self.client.post(self.url, {
            "client_name": "Kwame Mensah", "client_phone": "0241234567",
            "client_signature_kind": "typed", "client_signature_typed": "Kwame Mensah",
        })
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SIGNED)

    def test_client_cannot_change_the_email(self):
        self.client.logout()
        page = self.client.get(self.url)
        self.assertNotContains(page, 'name="client_email"')
        self.assertNotContains(page, 'name="accept"')
        self.client.post(self.url, _client_form(client_email="someone.else@example.com"))
        self.a.refresh_from_db()
        self.assertEqual(self.a.client_email, "kwame@example.com")

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


class ChangeRequestTests(StaffTestCase):
    """The client flags something to fix instead of signing; staff fix it
    (or reply that it stands) and send it back; the client can then sign."""

    def setUp(self):
        super().setUp()
        self.a = self._sent()
        self.url = reverse("psa:client", args=[self.a.token])
        self.flag_url = reverse("psa:request_changes", args=[self.a.token])
        mail.outbox.clear()

    def _flag(self, message="The deposit we agreed was GHS 800, not 1,000.", section="payment"):
        anon = self.client_class()
        return anon.post(self.flag_url, {"section": section, "message": message}, REMOTE_ADDR="198.51.100.4")

    def _send_back(self, **overrides):
        data = _form(company_signature_typed="", action="send", seen_status="changes",
                     client_note="Deposit corrected to GHS 800.", deposit="800")
        data.update(overrides)
        return self.client.post(reverse("psa_admin:psa_edit", args=[self.a.pk]), data)

    def test_client_flags_an_issue(self):
        resp = self._flag()
        self.assertRedirects(resp, self.url)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CHANGES)
        req = self.a.change_requests.get()
        self.assertEqual(req.section, "payment")
        self.assertEqual(req.client_ip, "198.51.100.4")
        self.assertIsNone(req.resolved_at)
        # Staff (CEO + preparer) are told, and the client gets a receipt.
        staff, receipt = sorted(mail.outbox, key=lambda m: m.to[0] == "kwame@example.com")
        self.assertEqual(staff.to, ["ceo@academicdigital.space", "admin@example.com"])
        self.assertIn("Changes requested", staff.subject)
        self.assertIn("GHS 800", staff.body)
        self.assertEqual(receipt.to, ["kwame@example.com"])
        self.assertTrue(Notification.objects.filter(icon="warn", link_url_name="psa_admin:psa_detail").exists())

    def test_request_needs_a_real_message(self):
        anon = self.client_class()
        for message in ("", "   ", "fix it"):
            with self.subTest(message=message):
                resp = anon.post(self.flag_url, {"section": "term", "message": message})
                self.assertEqual(resp.status_code, 400)
                self.assertContains(resp, 'id="psaChanges" open', status_code=400)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SENT)
        self.assertFalse(self.a.change_requests.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_signing_is_locked_while_changes_are_pending(self):
        self._flag()
        anon = self.client_class()
        anon.post(self.url, _client_form())
        self._flag("A second request from another tab.")
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CHANGES)
        self.assertEqual(self.a.change_requests.count(), 1)
        page = anon.get(self.url)
        self.assertContains(page, "Your requested changes are with Metascholar")
        self.assertContains(page, "GHS 800")
        self.assertNotContains(page, 'id="psaClientForm"')
        self.assertNotContains(page, 'id="psaChangesForm"')

    def test_staff_see_it(self):
        self._flag()
        detail = self.client.get(reverse("psa_admin:psa_detail", args=[self.a.pk]))
        self.assertContains(detail, 'id="psaOpenRequest"')
        self.assertContains(detail, "GHS 800")
        listing = self.client.get(reverse("psa_admin:psa_list"), {"status": "changes"})
        self.assertEqual([x.pk for x in listing.context["page"]], [self.a.pk])
        self.assertEqual(listing.context["stats"]["changes"], 1)
        edit = self.client.get(reverse("psa_admin:psa_edit", args=[self.a.pk]))
        self.assertContains(edit, 'id="psaRequestCallout"')
        self.assertContains(edit, 'name="seen_status" value="changes"')
        csv_body = self.client.get(reverse("psa_admin:psa_export")).content.decode("utf-8-sig")
        self.assertIn("4. Payment: The deposit we agreed", csv_body)

    def test_fix_and_send_back_then_client_signs(self):
        self._flag()
        mail.outbox.clear()
        resp = self._send_back()
        self.assertRedirects(resp, reverse("psa_admin:psa_detail", args=[self.a.pk]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SENT)
        self.assertEqual(self.a.deposit, Decimal("800.00"))
        req = self.a.change_requests.get()
        self.assertIsNotNone(req.resolved_at)
        self.assertEqual(req.resolved_by, self.admin)
        self.assertEqual(req.response, "Deposit corrected to GHS 800.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].subject.startswith("Updated:"))
        self.assertIn("Deposit corrected to GHS 800.", mail.outbox[0].body)
        # The client sees the reply and can sign now.
        anon = self.client_class()
        page = anon.get(self.url)
        self.assertContains(page, 'id="psaLastReply"')
        self.assertContains(page, 'id="psaClientForm"')
        anon.post(self.url, _client_form())
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SIGNED)

    def test_send_back_unchanged_needs_a_reply(self):
        self._flag()
        url = reverse("psa_admin:psa_send", args=[self.a.pk])
        self.client.post(url, {"client_note": "  "})
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CHANGES)
        self.client.post(url, {"client_note": "The deposit was agreed at GHS 1,000 on our call."})
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SENT)
        self.assertEqual(self.a.deposit, Decimal("1000.00"))
        self.assertEqual(self.a.change_requests.get().response, "The deposit was agreed at GHS 1,000 on our call.")

    def test_request_arriving_while_editing_is_not_closed_unread(self):
        # Staff opened the edit form while it was still with the client...
        self._flag()
        mail.outbox.clear()
        resp = self._send_back(seen_status="sent", fee="2600")
        self.assertRedirects(resp, reverse("psa_admin:psa_edit", args=[self.a.pk]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.fee, Decimal("2600.00"))          # the edit is kept
        self.assertEqual(self.a.status, Status.CHANGES)           # but nothing was sent
        self.assertIsNone(self.a.change_requests.get().resolved_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_several_rounds(self):
        self._flag()
        self._send_back()
        self._flag("Please also add the poster design as a deliverable.", section="service")
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CHANGES)
        self.assertEqual(self.a.change_requests.count(), 2)
        self.assertEqual(self.a.open_change_request.section, "service")

    def test_saving_without_sending_keeps_it_with_staff(self):
        self._flag()
        self._send_back(action="draft")
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CHANGES)
        self.assertIsNone(self.a.change_requests.get().resolved_at)

    def test_cancel_while_changes_pending(self):
        self._flag()
        self.client.post(reverse("psa_admin:psa_cancel", args=[self.a.pk]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.CANCELLED)
        self.assertContains(self.client_class().get(self.url), "withdrawn")

    def test_no_flagging_drafts_or_signed_agreements(self):
        draft = self._sent(action="draft")
        anon = self.client_class()
        resp = anon.post(reverse("psa:request_changes", args=[draft.token]), {"message": "Something is wrong here."})
        self.assertEqual(resp.status_code, 404)
        anon.post(self.url, _client_form())
        self._flag()
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SIGNED)
        self.assertFalse(self.a.change_requests.exists())

    def test_signing_area_is_the_large_layout(self):
        page = self.client_class().get(self.url)
        self.assertContains(page, 'class="psa-signs is-form"')
