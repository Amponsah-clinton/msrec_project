"""The certificate fee is paid on the workshop page itself.

The page submits the form in the background and opens the Paystack popup
there, rather than sending people to the standalone checkout -- which is
still what a no-JavaScript submit and the emailed payment link get.
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from workshop.models import WorkshopRegistration
from workshop.tests_payment_required import PinnedRateMixin, _form, _workshop

PS = WorkshopRegistration.PaymentStatus
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class InlineCheckoutTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop(certificate_required=True)
        self.url = reverse("workshop:register", args=[self.ws.slug])
        email = mock.patch("workshop.emails.send_branded_email", return_value=True)
        email.start()
        self.addCleanup(email.stop)

    def test_background_submit_returns_checkout_for_this_registration(self):
        resp = self.client.post(self.url, _form(), **AJAX)
        self.assertEqual(resp.status_code, 200)
        checkout = resp.json()["checkout"]
        reg = WorkshopRegistration.objects.get()
        self.assertEqual(reg.payment_status, PS.PENDING)
        self.assertEqual(checkout["reference"], reg.payment_reference)
        self.assertEqual(checkout["amount"], 3500)
        self.assertEqual(checkout["currency"], "GHS")
        self.assertEqual(checkout["email"], "ama@example.com")
        self.assertEqual(checkout["verify_url"], reverse("workshop:pay_verify", args=[reg.pk]))

    def test_plain_submit_still_goes_to_the_standalone_checkout(self):
        resp = self.client.post(self.url, _form())
        reg = WorkshopRegistration.objects.get()
        self.assertRedirects(resp, reverse("workshop:pay", args=[reg.pk]), fetch_redirect_response=False)

    def test_background_submit_without_a_fee_goes_to_thanks(self):
        ws = _workshop(title="Free one", certificate_fee=Decimal("0.00"))
        resp = self.client.post(
            reverse("workshop:register", args=[ws.slug]), _form(wants_certificate="no"), **AJAX
        )
        reg = WorkshopRegistration.objects.get()
        self.assertEqual(resp.json()["redirect"], f"{reverse('workshop:thanks')}?r={reg.pk}")

    def test_background_submit_with_errors_renders_the_page(self):
        # The script falls back to a normal submit on anything but JSON.
        resp = self.client.post(self.url, _form(name=""), **AJAX)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("text/html", resp["Content-Type"])
        self.assertFalse(WorkshopRegistration.objects.exists())

    def test_no_checkout_until_every_required_field_is_filled(self):
        cases = {
            "name": {"name": ""},
            "name (spaces only)": {"name": "   "},
            "institution": {"institution": ""},
            "institution (Other, left blank)": {"institution": "__other__", "institution_other": " "},
            "email": {"email": ""},
            "email (invalid)": {"email": "ama@example"},
            "phone": {"phone": ""},
            "phone (too short)": {"phone": "024"},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                resp = self.client.post(self.url, _form(**overrides), **AJAX)
                self.assertEqual(resp.status_code, 400)
                self.assertNotIn("application/json", resp["Content-Type"])
                self.assertFalse(WorkshopRegistration.objects.exists())

    def test_certificate_answer_required_before_checkout(self):
        ws = _workshop(title="Optional cert")
        data = _form()
        del data["wants_certificate"]
        resp = self.client.post(reverse("workshop:register", args=[ws.slug]), data, **AJAX)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(WorkshopRegistration.objects.exists())

    def test_already_registered_page_can_pay_in_place(self):
        self.client.post(self.url, _form())
        reg = WorkshopRegistration.objects.get()
        resp = self.client.post(self.url, _form())
        self.assertEqual(resp.status_code, 409)
        self.assertContains(resp, 'id="wsDupeCheckout"', status_code=409)
        self.assertContains(resp, "js.paystack.co/v1/inline.js", status_code=409)
        self.assertContains(resp, "csrfmiddlewaretoken", status_code=409)
        self.assertEqual(resp.context["duplicate"]["checkout"]["reference"], reg.payment_reference)
        # The link is kept as the fallback.
        self.assertContains(resp, reverse("workshop:pay", args=[reg.pk]), status_code=409)

    def test_namesake_gets_no_checkout(self):
        self.client.post(self.url, _form())
        resp = self.client.post(self.url, _form(email="someone.else@example.com"))
        self.assertIsNone(resp.context["duplicate"]["checkout"])
        self.assertNotContains(resp, 'id="wsDupeCheckout"', status_code=409)

    def test_verify_marks_paid(self):
        self.client.post(self.url, _form(), **AJAX)
        reg = WorkshopRegistration.objects.get()
        paid = {"status": "success", "amount": 3500, "currency": "GHS", "reference": reg.payment_reference}
        with mock.patch("payments.paystack.verify_transaction", return_value=paid), \
                mock.patch("notifications.sms.send_sms"):
            resp = self.client.post(
                reverse("workshop:pay_verify", args=[reg.pk]),
                {"reference": reg.payment_reference}, **AJAX,
            )
        self.assertTrue(resp.json()["ok"])
        reg.refresh_from_db()
        self.assertEqual(reg.payment_status, PS.SUCCESS)

    def test_pay_page_passes_checkout_as_json(self):
        self.client.post(self.url, _form())
        reg = WorkshopRegistration.objects.get()
        resp = self.client.get(reverse("workshop:pay", args=[reg.pk]))
        self.assertContains(resp, 'id="wspCheckout"')
        self.assertEqual(resp.context["checkout"]["reference"], reg.payment_reference)
        # The confirm message's line breaks must be escapes: a raw newline
        # inside the string literal is a syntax error that kills the button.
        self.assertContains(resp, r'"Register without a certificate?\n\n" +')
