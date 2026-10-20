"""Tests for the Registrations tab's message composer: staff write their own
email and/or SMS and send it to one registrant, the rows they tick, or the
group chip they pick (everyone / paid / not paid ...).
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from workshop.models import WorkshopRegistration
from workshop.tests_compulsory_certificate import PinnedRateMixin, _workshop

PS = WorkshopRegistration.PaymentStatus

SMS_OK = {"ok": True, "sent_to": [], "error": None}


class ComposerTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )
        self.client.force_login(admin)
        self.url = reverse("workshop_admin:manage", args=[self.ws.pk])

        self.paid = self._reg("Kofi Paid", "kofi@example.com", "0241111111",
                              wants_certificate=True, payment_status=PS.SUCCESS, amount=Decimal("150.00"))
        self.owes = self._reg("Ama Owes", "ama@example.com", "+233 24 222 2222",
                              wants_certificate=True, payment_status=PS.PENDING, amount=Decimal("150.00"))
        self.no_phone = self._reg("Esi Nophone", "esi@example.com", "",
                                  wants_certificate=True, payment_status=PS.FAILED, amount=Decimal("150.00"))

        sms_cfg = mock.patch("notifications.sms.is_configured", return_value=True)
        sms_cfg.start()
        self.addCleanup(sms_cfg.stop)

    def _reg(self, name, email, phone, **kwargs):
        return WorkshopRegistration.objects.create(
            workshop=self.ws, name=name, institution="UG", email=email, phone=phone, **kwargs
        )

    def _post(self, **extra):
        data = {"action": "send_message", "tab": "registrations", "scope": "all", "reg_ids": "",
                "send_email": "on", "subject": "Hello {first_name}", "body": "Hi {name},\nSee you at {workshop}."}
        data.update(extra)
        return self.client.post(self.url, data, follow=True)

    def _emailed(self, send):
        return sorted(c.kwargs["to"] for c in send.call_args_list)

    def test_email_to_everyone_is_personalised(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self._post()
        self.assertEqual(self._emailed(send), ["ama@example.com", "esi@example.com", "kofi@example.com"])
        call = next(c for c in send.call_args_list if c.kwargs["to"] == "ama@example.com")
        self.assertEqual(call.kwargs["subject"], "Hello Ama")
        self.assertEqual(call.kwargs["paragraphs"], ["Hi Ama Owes,", f"See you at {self.ws.title}."])

    def test_not_paid_group_reaches_only_those_who_owe(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self._post(scope="unpaid")
        self.assertEqual(self._emailed(send), ["ama@example.com", "esi@example.com"])

    def test_paid_group_reaches_only_those_who_paid(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self._post(scope="paid")
        self.assertEqual(self._emailed(send), ["kofi@example.com"])

    def test_ticked_rows_win_over_the_group_and_stay_in_this_workshop(self):
        other = _workshop(title="Another workshop")
        outsider = WorkshopRegistration.objects.create(
            workshop=other, name="Out Sider", institution="X", email="out@example.com")
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self._post(scope="unpaid", reg_ids=f"{self.paid.pk},{outsider.pk}")
        self.assertEqual(self._emailed(send), ["kofi@example.com"])

    def test_one_person(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self._post(reg_ids=str(self.owes.pk))
        self.assertEqual(self._emailed(send), ["ama@example.com"])

    def test_pay_button_only_for_those_who_owe(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self._post(button="pay")
        by_to = {c.kwargs["to"]: c.kwargs for c in send.call_args_list}
        self.assertIsNone(by_to["kofi@example.com"]["cta_url"])
        self.assertIn(reverse("workshop:pay", kwargs={"pk": self.owes.pk}), by_to["ama@example.com"]["cta_url"])

    def test_plain_sms_goes_out_as_one_bulk_send(self):
        with mock.patch("notifications.sms.send_sms", return_value=SMS_OK) as send_sms:
            resp = self._post(send_email="", send_sms="on", sms_body="MSREC: The workshop starts at 9am.")
        send_sms.assert_called_once()
        self.assertEqual(sorted(send_sms.call_args.args[0]), ["0241111111", "0242222222"])
        self.assertContains(resp, "SMS to 2")
        self.assertContains(resp, "1 without a valid Ghana number")

    def test_personalised_sms_is_sent_per_person(self):
        with mock.patch("notifications.sms.send_sms", return_value=SMS_OK) as send_sms:
            self._post(send_email="", send_sms="on", scope="unpaid",
                       sms_body="MSREC: {first_name}, you owe {amount}. Pay: {pay_link}")
        send_sms.assert_called_once()  # Esi has no phone, so only Ama is texted
        phones, text = send_sms.call_args.args
        self.assertEqual(phones, ["0242222222"])
        self.assertIn("Ama, you owe GHS 150.00. Pay: ", text)
        self.assertIn(f"/{self.owes.pk}/", text)

    def test_email_and_sms_together_mark_who_was_messaged(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True), \
                mock.patch("notifications.sms.send_sms", return_value=SMS_OK):
            self._post(send_sms="on", sms_body="MSREC: hello", scope="paid")
        self.paid.refresh_from_db()
        self.owes.refresh_from_db()
        self.assertIsNotNone(self.paid.message_sent_at)
        self.assertIsNone(self.owes.message_sent_at)

    def test_nothing_is_sent_without_a_channel_or_text(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send, \
                mock.patch("notifications.sms.send_sms", return_value=SMS_OK) as send_sms:
            self._post(send_email="")
            self._post(subject="")
            self._post(send_email="", send_sms="on", sms_body="")
        send.assert_not_called()
        send_sms.assert_not_called()

    def test_sms_refused_when_not_configured(self):
        with mock.patch("notifications.sms.is_configured", return_value=False), \
                mock.patch("notifications.sms.send_sms") as send_sms:
            resp = self._post(send_email="", send_sms="on", sms_body="hi")
        send_sms.assert_not_called()
        self.assertContains(resp, "SMS isn")

    def test_page_shows_the_composer(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, 'id="wsaComposeForm"')
        self.assertContains(resp, 'value="send_message"')
        self.assertContains(resp, "No phone — email only")
