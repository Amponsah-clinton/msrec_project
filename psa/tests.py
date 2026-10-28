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

from .models import Payment, PaymentRequest, ServiceAgreement

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

    def test_staff_never_set_the_phone_number(self):
        # It isn't on the staff form at all -- the client gives it when
        # they sign -- and a posted one is ignored rather than trusted.
        page = self.client.get(reverse("psa_admin:psa_new"))
        self.assertNotContains(page, 'name="client_phone"')
        a = self._sent(client_phone="0241234567")
        self.assertEqual(a.client_phone, "")

    def test_a_staff_edit_leaves_the_clients_own_number_alone(self):
        a = self._sent()
        a.client_phone = "+233 24 123 4567"
        a.save()
        self.client.post(reverse("psa_admin:psa_edit", args=[a.pk]),
                         _form(client_phone="0000000000", action="draft"))
        a.refresh_from_db()
        self.assertEqual(a.client_phone, "+233 24 123 4567")

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


class PaymentLedgerTests(StaffTestCase):
    """Money received against an agreement, and the amount owing that
    follows from it."""

    def setUp(self):
        super().setUp()
        self.a = self._sent()          # GHS 2,500 fee, sent to the client
        self.url = reverse("psa_admin:psa_payment_add", args=[self.a.pk])

    def _pay(self, amount="1000", **overrides):
        data = {"kind": "received", "amount": amount, "method": "momo",
                "paid_on": timezone.localdate().isoformat(), "note": ""}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_the_deposit_from_the_form_counts_as_received(self):
        """The admin typed a GHS 1,000 deposit when preparing the
        agreement, so that much is in before any entry is recorded."""
        self.assertEqual(self.a.deposit, Decimal("1000.00"))
        self.assertEqual(self.a.ledger_total, Decimal("0.00"))
        self.assertEqual(self.a.amount_paid, Decimal("1000.00"))
        self.assertEqual(self.a.amount_owing, Decimal("1500.00"))
        self.assertEqual(self.a.payment_state, "part")
        # Which is what the agreement document itself says is left.
        self.assertEqual(self.a.amount_owing, self.a.balance)

    def test_with_no_deposit_the_whole_fee_is_owing(self):
        a = self._sent(client_name="No Deposit", deposit="")
        self.assertEqual(a.deposit, Decimal("0.00"))
        self.assertIsNone(a.deposit_paid)
        self.assertEqual(a.amount_paid, Decimal("0.00"))
        self.assertEqual(a.amount_owing, Decimal("2500.00"))
        self.assertEqual(a.payment_state, "unpaid")

    def test_recording_a_payment_reduces_what_is_owing(self):
        resp = self._pay("1000")
        self.assertRedirects(resp, reverse("psa_admin:psa_detail", args=[self.a.pk]))
        payment = self.a.payments.get()
        self.assertEqual(payment.amount, Decimal("1000.00"))
        self.assertEqual(payment.method, "momo")
        self.assertEqual(payment.recorded_by, self.admin)
        self.a.refresh_from_db()
        # On top of the GHS 1,000 deposit already counted.
        self.assertEqual(self.a.ledger_total, Decimal("1000.00"))
        self.assertEqual(self.a.amount_paid, Decimal("2000.00"))
        self.assertEqual(self.a.amount_owing, Decimal("500.00"))
        self.assertEqual(self.a.payment_state, "part")

    def test_paid_in_full(self):
        self._pay("1000", note="Second instalment")
        self._pay("500", note="Balance")
        self.a.refresh_from_db()
        self.assertEqual(self.a.amount_owing, Decimal("0.00"))
        self.assertEqual(self.a.payment_state, "settled")
        self.assertEqual(self.a.payment_state_label, "Paid in full")

    def test_overpayment_shows_as_overpaid(self):
        self._pay("2000")                      # 1,000 deposit + 2,000 > 2,500
        self.a.refresh_from_db()
        self.assertEqual(self.a.amount_owing, Decimal("-500.00"))
        self.assertEqual(self.a.overpaid_by, Decimal("500.00"))
        self.assertEqual(self.a.payment_state, "over")

    def test_recording_the_deposit_again_shows_up_as_overpaid(self):
        """Nothing stops it, but the figures say so plainly -- which is why
        the form says the deposit is already counted."""
        self._pay("1500", note="Balance")
        self.a.refresh_from_db()
        self.assertEqual(self.a.payment_state, "settled")
        self._pay("1000", note="The deposit, by mistake")
        self.a.refresh_from_db()
        self.assertEqual(self.a.payment_state, "over")
        self.assertEqual(self.a.overpaid_by, Decimal("1000.00"))

    def test_refund_is_a_negative_entry(self):
        self._pay("1000")
        self._pay("400", kind="refund", note="Overpaid the instalment")
        self.a.refresh_from_db()
        self.assertEqual(self.a.payments.count(), 2)
        self.assertEqual(self.a.ledger_total, Decimal("600.00"))
        self.assertEqual(self.a.amount_paid, Decimal("1600.00"))
        self.assertEqual(self.a.amount_owing, Decimal("900.00"))
        refund = self.a.payments.order_by("-pk").first()
        self.assertTrue(refund.is_refund)
        self.assertEqual(refund.abs_amount, Decimal("400.00"))

    def test_a_refund_cannot_exceed_what_came_in(self):
        a = self._sent(client_name="No Deposit", deposit="")
        url = reverse("psa_admin:psa_payment_add", args=[a.pk])
        base = {"method": "cash", "paid_on": timezone.localdate().isoformat()}
        self.client.post(url, {"kind": "received", "amount": "500", **base})
        self.client.post(url, {"kind": "refund", "amount": "600", "note": "Too much", **base})
        self.assertEqual(a.payments.count(), 1)

    def test_the_deposit_can_be_given_back(self):
        """The deposit is money in, so it is money a refund can reach."""
        self._pay("1000", kind="refund", note="Deposit returned")
        self.a.refresh_from_db()
        self.assertEqual(self.a.amount_paid, Decimal("0.00"))
        self.assertEqual(self.a.amount_owing, Decimal("2500.00"))
        self.assertEqual(self.a.payment_state, "unpaid")

    def test_a_refund_needs_a_reason(self):
        self._pay("500")
        self._pay("100", kind="refund", note="")
        self.assertEqual(self.a.payments.count(), 1)

    def test_bad_entries_are_refused(self):
        tomorrow = (timezone.localdate() + timezone.timedelta(days=1)).isoformat()
        cases = {
            "blank": {"amount": ""},
            "words": {"amount": "five hundred"},
            "zero": {"amount": "0"},
            "negative": {"amount": "-100"},
            "slipped decimal": {"amount": "250000"},
            "future date": {"paid_on": tomorrow},
            "no date": {"paid_on": ""},
            "unknown method": {"method": "crypto"},
        }
        for case, data in cases.items():
            with self.subTest(case):
                self._pay(**data)
                self.assertFalse(self.a.payments.exists(), case)

    def test_a_saved_entry_cannot_be_changed_or_deleted(self):
        self._pay("1000")
        payment = self.a.payments.get()
        payment.amount = Decimal("9999.00")
        with self.assertRaises(ValueError):
            payment.save()
        with self.assertRaises(ValueError):
            payment.delete()
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("1000.00"))

    def test_no_edit_or_delete_route_exists(self):
        """There is nothing on the site that could change an entry."""
        from django.urls import NoReverseMatch
        self._pay("1000")
        pk = self.a.payments.get().pk
        for name in ("psa_payment_edit", "psa_payment_delete"):
            with self.subTest(name), self.assertRaises(NoReverseMatch):
                reverse(f"psa_admin:{name}", args=[pk])

    def test_a_double_submit_records_one_payment(self):
        self._pay("1000", note="Teller 88213")
        self._pay("1000", note="Teller 88213")
        self.assertEqual(self.a.payments.count(), 1)

    def test_two_real_payments_of_the_same_amount_are_told_apart(self):
        self._pay("500", note="Teller 1")
        self._pay("500", note="Teller 2")
        self.assertEqual(self.a.payments.count(), 2)

    def test_a_draft_with_a_fee_can_take_a_deposit(self):
        """Money can arrive before the paperwork goes out."""
        draft = self._sent(action="draft", client_name="Draft Client")
        self.assertEqual(draft.status, Status.DRAFT)
        self.assertTrue(draft.can_record_payment)
        self.client.post(reverse("psa_admin:psa_payment_add", args=[draft.pk]),
                         {"kind": "received", "amount": "100", "method": "cash",
                          "paid_on": timezone.localdate().isoformat()})
        self.assertEqual(draft.payments.get().amount, Decimal("100.00"))

    def test_nothing_is_recorded_without_an_agreed_fee(self):
        a = ServiceAgreement.objects.create(client_name="No Fee", status=Status.SENT,
                                            created_by=self.admin)
        self.assertIsNone(a.fee)
        self.assertIsNone(a.amount_owing)
        self.assertEqual(a.payment_state, "no_fee")
        self.assertFalse(a.can_record_payment)
        self.client.post(reverse("psa_admin:psa_payment_add", args=[a.pk]),
                         {"kind": "received", "amount": "100", "method": "cash",
                          "paid_on": timezone.localdate().isoformat()})
        self.assertFalse(a.payments.exists())

    def test_a_cancelled_agreement_keeps_its_deposit_on_the_record(self):
        self._pay("1000")
        self.client.post(reverse("psa_admin:psa_cancel", args=[self.a.pk]))
        self._pay("500", note="Second instalment")
        self.assertEqual(self.a.payments.count(), 2)

    def test_signed_agreements_still_take_payments(self):
        """Signing locks the agreement, not the money that comes in after."""
        anon = self.client_class()
        anon.get(reverse("psa:client", args=[self.a.token]))
        anon.post(reverse("psa:client", args=[self.a.token]), _client_form())
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, Status.SIGNED)
        self._pay("1500", note="Paid on delivery")   # the 1,000 deposit, then this
        self.a.refresh_from_db()
        self.assertEqual(self.a.amount_owing, Decimal("0.00"))

    def test_only_staff_can_record_a_payment(self):
        applicant = User.objects.create_user(email="nope@example.com", password="pw-12345678",
                                             first_name="N", last_name="P", role=User.Role.APPLICANT)
        other = self.client_class()
        other.force_login(applicant)
        self.assertEqual(other.post(self.url, {"amount": "100"}).status_code, 302)
        self.assertFalse(self.a.payments.exists())

    def test_the_secretariat_can_record_a_payment(self):
        sec = User.objects.create_user(email="sec@example.com", password="pw-12345678",
                                       first_name="Sam", last_name="Sec", role=User.Role.SECRETARIAT)
        theirs = self.client_class()
        theirs.force_login(sec)
        theirs.post(self.url, {"kind": "received", "amount": "250", "method": "cash",
                               "paid_on": timezone.localdate().isoformat()})
        self.assertEqual(self.a.payments.get().recorded_by, sec)

    def test_it_comes_back_to_the_list_it_was_recorded_from(self):
        back = reverse("psa_admin:psa_list") + "?pay=owing&page=1"
        self.assertRedirects(self._pay("100", next=back), back)
        # Somewhere else's URL is ignored.
        self.assertRedirects(self._pay("200", next="https://evil.example.com/x", note="2"),
                             reverse("psa_admin:psa_detail", args=[self.a.pk]))


class PaymentListTests(StaffTestCase):
    """The amount owing column, its filters and the running total."""

    def setUp(self):
        super().setUp()
        # 2,500 fee, 1,000 deposit typed on the form -> 1,500 owing.
        self.a = self._sent()
        self.b = self._sent(client_name="Ama Owusu", fee="1000", deposit="0")
        Payment.objects.create(agreement=self.b, amount=Decimal("1000.00"),
                               paid_on=timezone.localdate(), method="bank")

    def test_the_column_shows_what_is_owing(self):
        resp = self.client.get(reverse("psa_admin:psa_list"))
        self.assertContains(resp, "Amount Owing")
        self.assertContains(resp, "GHS 1,500.00")          # fee less the deposit
        self.assertContains(resp, "GHS 1,000.00 paid")     # the deposit, counted
        self.assertContains(resp, "Paid in full")
        # The running total across live agreements.
        self.assertEqual([dict(row) for row in resp.context["outstanding"]],
                         [{"currency": "GHS", "total": Decimal("1500.00")}])

    def test_the_total_comes_from_the_ledger_not_a_query_per_row(self):
        for i in range(6):
            Payment.objects.create(agreement=self.a, amount=Decimal("10.00"),
                                   paid_on=timezone.localdate(), method="cash", note=str(i))
        resp = self.client.get(reverse("psa_admin:psa_list"))
        rows = {a.pk: (a.paid_total, a._ledger_total) for a in resp.context["page"].object_list}
        # The deposit and the entries, annotated together and apart.
        self.assertEqual(rows[self.a.pk], (Decimal("1060.00"), Decimal("60.00")))
        self.assertEqual(rows[self.b.pk], (Decimal("1000.00"), Decimal("1000.00")))

    def test_filters(self):
        url = reverse("psa_admin:psa_list")
        # a: part paid by its deposit. b: settled by its payment.
        cases = {"owing": [self.a.pk], "part": [self.a.pk], "settled": [self.b.pk],
                 "unpaid": [], "over": []}
        for value, expected in cases.items():
            with self.subTest(value):
                resp = self.client.get(url, {"pay": value})
                self.assertEqual([a.pk for a in resp.context["page"].object_list], expected)

    def test_sorting_by_what_is_owing(self):
        url = reverse("psa_admin:psa_list")
        high = [a.pk for a in self.client.get(url, {"sort": "owing_high"}).context["page"].object_list]
        self.assertEqual(high[0], self.a.pk)
        low = [a.pk for a in self.client.get(url, {"sort": "owing_low"}).context["page"].object_list]
        self.assertEqual(low[0], self.b.pk)

    def test_the_export_carries_the_money_columns(self):
        body = self.client.get(reverse("psa_admin:psa_export")).content.decode("utf-8-sig")
        self.assertIn("Total Received (Deposit + Payments)", body)
        self.assertIn("Payments Since Deposit", body)
        self.assertIn("Amount Owing", body)
        self.assertIn("Paid in full", body)
        self.assertIn("Part paid", body)

    def test_the_agreement_page_shows_the_ledger(self):
        resp = self.client.get(reverse("psa_admin:psa_detail", args=[self.b.pk]))
        self.assertContains(resp, "Amount owing")
        self.assertContains(resp, "GHS 1,000.00 received of GHS 1,000.00")
        self.assertContains(resp, "Bank transfer")

    def test_the_deposit_is_listed_as_the_first_thing_received(self):
        resp = self.client.get(reverse("psa_admin:psa_detail", args=[self.a.pk]))
        self.assertContains(resp, "is-deposit")
        self.assertContains(resp, "Taken upfront, from Section 4")
        self.assertContains(resp, "GHS 1,000.00 received of GHS 2,500.00")
        # And the form says not to enter it again.
        self.assertContains(resp, "deposit from Section 4 is already counted")

    def test_the_warning_paragraph_is_gone(self):
        for url in (reverse("psa_admin:psa_list"),
                    reverse("psa_admin:psa_detail", args=[self.a.pk])):
            with self.subTest(url):
                body = self.client.get(url).content.decode()
                self.assertNotIn("psa-pay-warn", body)
                self.assertNotIn("a mistake has to be put right", body)
                self.assertNotIn("Check the amount and date", body)


class DeadlineTests(StaffTestCase):
    """Days left to deliver the work, on the list."""

    def _with_deadline(self, days, **overrides):
        today = timezone.localdate()
        # Well back, so a deadline in the past is still after the start.
        return self._sent(start_date=(today - timezone.timedelta(days=120)).isoformat(),
                          completion_date=(today + timezone.timedelta(days=days)).isoformat(),
                          **overrides)

    def test_the_countdown_reads_as_days_left(self):
        cases = {30: "In 4 weeks", 12: "In 12 days", 3: "In 3 days", 1: "Due tomorrow",
                 0: "Due today", -1: "1 day overdue", -9: "9 days overdue"}
        for days, expected in cases.items():
            with self.subTest(days=days):
                a = self._with_deadline(days)
                self.assertEqual(a.days_to_deadline, days)
                self.assertEqual(a.deadline_countdown, expected)

    def test_the_state_follows_the_countdown(self):
        for days, state in {40: "ok", 7: "soon", 1: "soon", 0: "today", -2: "overdue"}.items():
            with self.subTest(days=days):
                self.assertEqual(self._with_deadline(days).deadline_state, state)

    def test_no_deadline_set(self):
        a = self._sent(action="draft", completion_date="")
        self.assertIsNone(a.completion_date)
        self.assertIsNone(a.days_to_deadline)
        self.assertEqual(a.deadline_state, "none")
        self.assertEqual(a.deadline_countdown, "")

    def test_a_cancelled_agreement_stops_counting_down(self):
        a = self._with_deadline(-3)
        self.client.post(reverse("psa_admin:psa_cancel", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.deadline_state, "closed")
        self.assertEqual(a.deadline_countdown, "")

    def test_the_column_is_on_the_list(self):
        overdue = self._with_deadline(-4, client_name="Late Client")
        soon = self._with_deadline(2, client_name="Soon Client")
        resp = self.client.get(reverse("psa_admin:psa_list"))
        self.assertContains(resp, "<th>Deadline</th>", html=False)
        self.assertContains(resp, "4 days overdue")
        self.assertContains(resp, "In 2 days")
        self.assertContains(resp, 'psa-deadline is-overdue')
        self.assertContains(resp, 'psa-deadline is-soon')
        self.assertContains(resp, overdue.completion_date.strftime("%d %b %Y"))
        self.assertContains(resp, soon.completion_date.strftime("%d %b %Y"))

    def test_sorting_by_deadline_puts_the_nearest_first(self):
        far = self._with_deadline(90, client_name="Far")
        near = self._with_deadline(2, client_name="Near")
        none = self._sent(action="draft", completion_date="", client_name="Undated")
        url = reverse("psa_admin:psa_list")
        soonest = [a.pk for a in self.client.get(url, {"sort": "deadline_soon"}).context["page"].object_list]
        self.assertEqual(soonest[:2], [near.pk, far.pk])
        self.assertEqual(soonest[-1], none.pk, "no deadline sorts last")
        latest = [a.pk for a in self.client.get(url, {"sort": "deadline_late"}).context["page"].object_list]
        self.assertEqual(latest[:2], [far.pk, near.pk])
        self.assertEqual(latest[-1], none.pk, "no deadline sorts last either way")

class TemplateHygieneTests(StaffTestCase):
    """Django's {# ... #} comment is single-line only: written across two
    lines it prints on the page as text. One did, in the agreement page's
    sidebar, so this keeps it from coming back."""

    def test_no_comment_is_left_open_on_its_line(self):
        from pathlib import Path
        from django.conf import settings
        root = Path(settings.BASE_DIR) / "templates" / "psa"
        offenders = [
            f"{path.name}:{n}: {line.strip()}"
            for path in sorted(root.glob("*.html"))
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if "{#" in line and "#}" not in line
        ]
        self.assertEqual(offenders, [], "use {% comment %} for a comment over several lines")

    def test_no_template_syntax_reaches_the_page(self):
        a = self._sent()
        for url in (reverse("psa_admin:psa_list"),
                    reverse("psa_admin:psa_detail", args=[a.pk]),
                    reverse("psa_admin:psa_edit", args=[a.pk])):
            with self.subTest(url):
                body = self.client.get(url).content.decode()
                for leak in ("{#", "#}", "{%", "%}", "{{", "}}"):
                    self.assertNotIn(leak, body, f"{leak} printed on {url}")


class PsaSmsTests(StaffTestCase):
    """Every PSA email that has a number to reach also goes out as a text."""

    def setUp(self):
        super().setUp()
        self.a = self._sent()
        self.a.client_phone = "+233 24 123 4567"
        self.a.save(update_fields=["client_phone"])

    def test_every_message_is_one_gsm_segment(self):
        # A segment costs a credit. The signing link alone is 97 of the
        # 160 characters, and one curly quote would cut the budget to 70,
        # so each message is checked against a deliberately awkward
        # agreement: a long client name and a six-figure fee.
        from notifications import sms

        from psa import emails

        a = self.a
        a.client_name = "University of Ghana, School of Public Health"
        a.fee = Decimal("184500.00")
        req = PaymentRequest(agreement=a, amount=Decimal("138375.00"), currency=a.currency)
        payment = Payment(agreement=a, amount=Decimal("138375.00"), receipt_number="MSR-2026-00007")
        for label, message in (
            ("link", emails.sms_to_client(a)),
            ("reminder", emails.sms_to_client(a, reminder=True)),
            ("updated", emails.sms_to_client(a, updated=True)),
            ("signed copy", emails.sms_client_copy(a)),
            ("receipt", emails.sms_change_request_receipt(a)),
            ("staff signed", emails.sms_signed_to_staff(a)),
            ("staff changes", emails.sms_changes_requested_to_staff(a)),
            ("pay link", emails.sms_payment_link(a, req)),
            ("pay reminder", emails.sms_payment_link(a, req, reminder=True)),
            ("receipt", emails.sms_receipt(a, payment)),
            ("staff paid", emails.sms_payment_to_staff(a, payment)),
        ):
            with self.subTest(label):
                count, encoding = sms.segments(message)
                self.assertEqual(encoding, "gsm", f"{label} left GSM-7: {message!r}")
                self.assertEqual(count, 1, f"{label} costs {count} credits: {message!r}")

    def test_curly_punctuation_is_folded_before_it_reaches_a_handset(self):
        from notifications import sms

        from psa import emails

        self.a.client_name = "Nkrumah\u2019s Trust \u2014 Accra"
        message = emails.sms_signed_to_staff(self.a)
        self.assertNotIn("\u2019", message)
        self.assertNotIn("\u2014", message)
        self.assertIn("Nkrumah's Trust - Accra", message)
        self.assertEqual(sms.segments(message)[1], "gsm")

    def test_a_long_name_is_clipped_not_left_to_run(self):
        from psa import emails
        self.a.client_name = "A" * 200
        self.assertIn("A" * emails.SMS_NAME_LEN + "...", emails.sms_signed_to_staff(self.a))

    def test_nothing_is_sent_without_a_number_or_an_api_key(self):
        from notifications import sms as sms_module

        from psa import emails

        sent = []
        original = sms_module.send_sms

        def fake(recipients, message, sender=None):
            sent.append((list(recipients), message))
            return {"ok": True}

        original_conf = sms_module.is_configured
        sms_module.send_sms = fake
        self.addCleanup(lambda: setattr(sms_module, "send_sms", original))
        self.addCleanup(lambda: setattr(sms_module, "is_configured", original_conf))

        # BMS_API_KEY is unset under test, so the gateway is never called.
        self.assertFalse(sms_module.is_configured())
        self.assertFalse(emails._sms(["0241234567"], "hello", "test"))
        # And an empty number short-circuits even once a key is set.
        sms_module.is_configured = lambda: True
        self.assertFalse(emails._sms([""], "hello", "test"))
        self.assertEqual(sent, [])

    def test_an_unreachable_client_is_skipped_quietly(self):
        from psa import emails
        self.a.client_phone = ""
        self.assertEqual(emails._client_phone(self.a), "")
        # A landline or a foreign number is not a Ghana mobile.
        self.a.client_phone = "+44 20 7946 0958"
        self.assertEqual(emails._client_phone(self.a), "")
        self.a.client_phone = "0241234567"
        self.assertEqual(emails._client_phone(self.a), "0241234567")

    def test_staff_phones_follow_the_email_list_and_the_opt_out(self):
        from psa import emails
        self.admin.phone = "0244000111"
        self.admin.save(update_fields=["phone"])
        self.assertIn("0244000111", emails._staff_phones(self.a))
        self.admin.sms_notifications_enabled = False
        self.admin.save(update_fields=["sms_notifications_enabled"])
        self.assertNotIn("0244000111", emails._staff_phones(self.a))

    def test_the_client_link_text_is_sent_when_the_email_goes(self):
        from psa import emails
        sent = self._patch_send([])
        self.client.post(reverse("psa_admin:psa_resend", args=[self.a.pk]))
        self.assertEqual(len(sent), 1)
        numbers, message = sent[0]
        self.assertEqual(numbers, ["0241234567"])
        self.assertIn(self.a.reference, message)
        self.assertIn(self.a.token, message)

    def test_a_text_that_fails_never_breaks_the_email(self):
        from psa import emails
        from notifications import sms as sms_module

        def boom(*args, **kwargs):
            raise RuntimeError("gateway down")

        original_send, original_conf = sms_module.send_sms, sms_module.is_configured
        sms_module.send_sms, sms_module.is_configured = boom, lambda: True
        try:
            self.assertTrue(emails.send_to_client(self.a))
        finally:
            sms_module.send_sms, sms_module.is_configured = original_send, original_conf
        self.assertEqual(mail.outbox[-1].to, [self.a.client_email])

    # ---- helpers ----------------------------------------------------

    def _patch_send(self, sink):
        """Capture outgoing texts instead of calling the gateway."""
        from notifications import sms as sms_module
        original_send, original_conf = sms_module.send_sms, sms_module.is_configured

        def fake(recipients, message, sender=None):
            sink.append((list(recipients), message))
            return {"ok": True, "sent_to": list(recipients)}

        sms_module.send_sms = fake
        sms_module.is_configured = lambda: True
        self.addCleanup(lambda: setattr(sms_module, "send_sms", original_send))
        self.addCleanup(lambda: setattr(sms_module, "is_configured", original_conf))
        return sink


class PaymentLinkTests(StaffTestCase):
    """Sending a client a link to settle what they owe, and what comes back."""

    def setUp(self):
        super().setUp()
        self.a = self._sent()                      # fee 2500, deposit 1000
        self.a.client_phone = "0241234567"
        self.a.save(update_fields=["client_phone"])
        self.url = reverse("psa_admin:psa_payment_link", args=[self.a.pk])

    # ---- helpers ------------------------------------------------------

    def _paystack(self, req, *, status="success", amount=None, currency=None):
        """Stand in for Paystack's verify endpoint."""
        from payments import paystack
        data = {
            "status": status,
            "amount": req.amount_subunit if amount is None else amount,
            "currency": req.currency if currency is None else currency,
            "gateway_response": "Approved" if status == "success" else "Declined",
        }
        original = paystack.verify_transaction
        paystack.verify_transaction = lambda reference: data
        self.addCleanup(lambda: setattr(paystack, "verify_transaction", original))
        return data

    def _request_link(self, **post):
        self.client.post(self.url, {"next": "", **post})
        return PaymentRequest.objects.filter(agreement=self.a).order_by("-pk").first()

    # ---- creating and sending -----------------------------------------

    def test_link_defaults_to_everything_outstanding(self):
        req = self._request_link()
        self.assertEqual(req.amount, Decimal("1500.00"))      # 2500 fee - 1000 deposit
        self.assertEqual(req.status, PaymentRequest.Status.PENDING)
        self.assertEqual(req.send_count, 1)
        self.assertTrue(req.reference.startswith("MSREC-PSA-"))
        self.assertGreaterEqual(len(req.token), 40)
        # Emailed to the client with the link in it.
        self.assertEqual(mail.outbox[-1].to, [self.a.client_email])
        self.assertIn(req.token, mail.outbox[-1].body)

    def test_an_instalment_may_be_less_but_never_more(self):
        self.assertEqual(self._request_link(amount="500").amount, Decimal("500.00"))
        before = PaymentRequest.objects.count()
        self.client.post(self.url, {"amount": "9000"})
        self.assertEqual(PaymentRequest.objects.count(), before)

    def test_nothing_to_collect_is_refused(self):
        Payment.objects.create(agreement=self.a, amount=Decimal("1500.00"))
        self.client.post(self.url, {})
        self.assertFalse(PaymentRequest.objects.filter(agreement=self.a).exists())

    def test_a_new_link_retires_the_old_one(self):
        first = self._request_link()
        second = self._request_link()
        first.refresh_from_db()
        self.assertEqual(first.status, PaymentRequest.Status.CANCELLED)
        self.assertEqual(second.status, PaymentRequest.Status.PENDING)
        self.assertEqual(self.a.open_payment_request.pk, second.pk)

    def test_resending_chases_the_same_link_and_extends_it(self):
        req = self._request_link()
        was = req.expires_at
        resp = self.client.post(
            reverse("psa_admin:psa_payment_link_resend", args=[self.a.pk, req.pk]), {})
        self.assertEqual(resp.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.send_count, 2)
        self.assertGreater(req.expires_at, was)
        self.assertEqual(PaymentRequest.objects.filter(agreement=self.a).count(), 1)
        self.assertIn("Reminder", mail.outbox[-1].subject)

    def test_staff_can_withdraw_a_link(self):
        req = self._request_link()
        self.client.post(reverse("psa_admin:psa_payment_link_cancel", args=[self.a.pk, req.pk]), {})
        req.refresh_from_db()
        self.assertEqual(req.status, PaymentRequest.Status.CANCELLED)
        self.assertFalse(req.is_payable)

    # ---- the link itself ----------------------------------------------

    def test_the_page_needs_the_token_and_is_never_cached(self):
        req = self._request_link()
        self.client.logout()
        resp = self.client.get(reverse("psa:pay", kwargs={"token": req.token}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Cache-Control"], "no-store")
        self.assertEqual(resp["Referrer-Policy"], "same-origin")
        self.assertContains(resp, "1,500.00")
        # The primary key is not a way in.
        self.assertEqual(self.client.get(f"/psa/pay/{req.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/psa/pay/not-a-real-token/").status_code, 404)

    def test_opening_the_page_is_recorded(self):
        req = self._request_link()
        self.client.logout()
        self.client.get(reverse("psa:pay", kwargs={"token": req.token}))
        req.refresh_from_db()
        self.assertIsNotNone(req.viewed_at)

    def test_an_expired_link_stops_collecting(self):
        req = self._request_link()
        req.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        req.save(update_fields=["expires_at"])
        self.assertTrue(req.is_expired)
        self.assertFalse(req.is_payable)
        self.client.logout()
        page = self.client.get(reverse("psa:pay", kwargs={"token": req.token}))
        self.assertContains(page, "expired")
        resp = self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {})
        self.assertEqual(resp.status_code, 400)

    def test_a_link_stands_down_rather_than_overcharge(self):
        # Staff take GHS 1,000 by bank transfer while the GHS 1,500 link
        # is still out. Charging it now would collect 500 too much.
        req = self._request_link()
        Payment.objects.create(agreement=self.a, amount=Decimal("1000.00"), method="bank")
        req.refresh_from_db()
        self.assertFalse(req.is_payable)
        self.client.logout()
        page = self.client.get(reverse("psa:pay", kwargs={"token": req.token}))
        self.assertContains(page, "amount due has changed")
        self._paystack(req)
        resp = self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {})
        self.assertEqual(resp.status_code, 400)
        self.a.refresh_from_db()
        self.assertEqual(self.a.amount_owing, Decimal("500.00"))

    def test_a_cancelled_agreement_stops_collecting(self):
        req = self._request_link()
        self.a.status = Status.CANCELLED
        self.a.save(update_fields=["status"])
        req.refresh_from_db()
        self.assertFalse(req.is_payable)

    # ---- taking the money ---------------------------------------------

    def test_a_verified_payment_lands_in_the_ledger_and_cuts_the_owing(self):
        req = self._request_link()
        self._paystack(req)
        self.client.logout()
        resp = self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}),
                                {"reference": req.reference})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

        req.refresh_from_db()
        self.a.refresh_from_db()
        self.assertEqual(req.status, PaymentRequest.Status.PAID)
        self.assertIsNotNone(req.paid_at)
        # The ledger entry is what makes the list's Amount Owing column move.
        self.assertEqual(req.payment.amount, Decimal("1500.00"))
        self.assertEqual(req.payment.method, Payment.Method.CARD)
        self.assertEqual(self.a.amount_paid, Decimal("2500.00"))
        self.assertEqual(self.a.amount_owing, Decimal("0.00"))
        self.assertEqual(self.a.payment_state, "settled")

    def test_the_receipt_is_numbered_emailed_and_downloadable(self):
        req = self._request_link()
        self._paystack(req)
        self.client.logout()
        self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {})
        req.refresh_from_db()

        self.assertTrue(req.payment.receipt_number.startswith("MSR-"))
        client_copy = [m for m in mail.outbox if m.to == [self.a.client_email]][-1]
        self.assertIn(req.payment.receipt_number, client_copy.subject)
        self.assertTrue(client_copy.attachments, "the receipt PDF should be attached")
        self.assertTrue(client_copy.attachments[0][0].endswith(".pdf"))

        # The client's own copy, from the payment page.
        resp = self.client.get(reverse("psa:receipt", kwargs={"token": req.token}))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertEqual(resp["Cache-Control"], "no-store")
        self.assertTrue(resp.content.startswith(b"%PDF"))

        # And the staff copy, filed against the agreement.
        self.client.force_login(self.admin)
        staff_copy = self.client.get(
            reverse("psa_admin:psa_receipt", args=[self.a.pk, req.payment.pk]))
        self.assertTrue(staff_copy.content.startswith(b"%PDF"))

    def test_the_same_charge_is_never_banked_twice(self):
        req = self._request_link()
        self._paystack(req)
        self.client.logout()
        url = reverse("psa:pay_verify", kwargs={"token": req.token})
        for _ in range(3):
            self.assertTrue(self.client.post(url, {}).json()["ok"])
        self.assertEqual(self.a.payments.count(), 1)
        self.a.refresh_from_db()
        self.assertEqual(self.a.amount_owing, Decimal("0.00"))

    def test_a_wrong_amount_is_refused_and_banks_nothing(self):
        req = self._request_link()
        self._paystack(req, amount=100)          # GHS 1.00 against a GHS 1,500 request
        self.client.logout()
        resp = self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {})
        self.assertEqual(resp.status_code, 400)
        req.refresh_from_db()
        self.assertEqual(req.status, PaymentRequest.Status.PENDING)
        self.assertEqual(self.a.payments.count(), 0)

    def test_a_wrong_currency_is_refused(self):
        req = self._request_link()
        self._paystack(req, currency="NGN")
        self.client.logout()
        self.assertEqual(
            self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {}).status_code, 400)
        self.assertEqual(self.a.payments.count(), 0)

    def test_a_failed_charge_banks_nothing(self):
        req = self._request_link()
        self._paystack(req, status="failed")
        self.client.logout()
        resp = self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.a.payments.count(), 0)
        req.refresh_from_db()
        self.assertEqual(req.status, PaymentRequest.Status.PENDING)

    def test_a_browser_quoting_someone_elses_reference_is_refused(self):
        req = self._request_link()
        self._paystack(req)
        self.client.logout()
        resp = self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}),
                                {"reference": "MSREC-PSA-999-deadbeef"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.a.payments.count(), 0)

    def test_the_amount_charged_is_never_read_from_the_browser(self):
        req = self._request_link()
        self._paystack(req)
        self.client.logout()
        self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}),
                         {"amount": "1", "amount_subunit": "100", "reference": req.reference})
        req.refresh_from_db()
        self.assertEqual(req.payment.amount, Decimal("1500.00"))

    # ---- what the staff see -------------------------------------------

    def test_the_owing_column_and_the_panel_follow_the_ledger(self):
        req = self._request_link(amount="500")
        self._paystack(req)
        self.client.logout()
        self.client.post(reverse("psa:pay_verify", kwargs={"token": req.token}), {})
        req.refresh_from_db()

        self.client.force_login(self.admin)
        listing = self.client.get(reverse("psa_admin:psa_list"))
        self.assertContains(listing, "1,000.00")       # 1500 owed, 500 just paid
        detail = self.client.get(reverse("psa_admin:psa_detail", args=[self.a.pk]))
        self.assertContains(detail, "1,000.00")
        self.assertContains(detail, req.payment.receipt_number)
        self.assertContains(detail, "Send payment link")   # more still owing

    def test_a_refund_gets_no_receipt(self):
        refund = Payment.objects.create(agreement=self.a, amount=Decimal("-100.00"))
        self.assertIsNone(refund.receipt_number)
        resp = self.client.get(reverse("psa_admin:psa_receipt", args=[self.a.pk, refund.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_only_staff_can_mint_or_chase_a_link(self):
        req = self._request_link()
        self.client.logout()
        for url in (self.url,
                    reverse("psa_admin:psa_payment_link_resend", args=[self.a.pk, req.pk]),
                    reverse("psa_admin:psa_payment_link_cancel", args=[self.a.pk, req.pk]),
                    reverse("psa_admin:psa_receipt", args=[self.a.pk, req.pk])):
            with self.subTest(url):
                self.assertEqual(self.client.post(url, {}).status_code, 302)
