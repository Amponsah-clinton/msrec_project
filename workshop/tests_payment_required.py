"""Choosing a certificate commits you to paying for it.

Until the fee is settled the registration is not complete -- no
confirmation email, no SMS, not counted as registered -- whether the
certificate was compulsory for the workshop or the registrant chose it
from the optional question.

Changing that choice is a separate thing from not paying, so an optional
certificate can be dropped (decline_certificate), which settles the fee at
zero and completes the registration. Without that the optional path is a
trap, and people escape it by registering again without a certificate --
which is exactly what the live data showed before this existed.
"""
import os
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from workshop.models import Workshop, WorkshopRegistration

PS = WorkshopRegistration.PaymentStatus


class PinnedRateMixin:
    RATE = "11.65"

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"USD_GHS_RATE": self.RATE})
        env.start()
        self.addCleanup(env.stop)
        no_network = mock.patch(
            "payments.currency._fetch_rate",
            side_effect=AssertionError("the rate pin did not apply -- no live lookup in tests"),
        )
        no_network.start()
        self.addCleanup(no_network.stop)
        cache.clear()
        self.addCleanup(cache.clear)


def _workshop(**kwargs):
    fields = {
        "title": "Research Ethics Workshop",
        "starts_at": timezone.now() + timezone.timedelta(days=7),
        "certificate_fee": Decimal("35.00"),
        "fee_currency": "GHS",
        "is_published": True,
    }
    fields.update(kwargs)
    return Workshop.objects.create(**fields)


def _form(**overrides):
    data = {
        "name": "Ama Mensah", "institution": "University Of Ghana",
        "email": "ama@example.com", "phone": "0241234567", "comments": "",
        "wants_certificate": "yes",
    }
    data.update(overrides)
    return data


class OptionalChoiceRequiresPaymentTests(PinnedRateMixin, TestCase):
    """The case asked for: the certificate is optional, but choosing it
    makes payment compulsory."""

    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        self.url = reverse("workshop:register", args=[self.ws.slug])

    def _opt_in(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(self.url, _form())
        return WorkshopRegistration.objects.get()

    def test_choosing_a_certificate_leaves_the_registration_incomplete(self):
        reg = self._opt_in()
        self.assertTrue(reg.wants_certificate)
        self.assertEqual(reg.payment_status, PS.PENDING)
        self.assertTrue(reg.payment_outstanding)
        self.assertFalse(reg.registration_complete)
        self.assertFalse(reg.certificate_ready)

    def test_declining_a_certificate_completes_it_immediately(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(self.url, _form(wants_certificate="no"))
        reg = WorkshopRegistration.objects.get()
        self.assertFalse(reg.wants_certificate)
        self.assertEqual(reg.payment_status, PS.NOT_REQUIRED)
        self.assertTrue(reg.registration_complete)

    def test_paying_completes_it(self):
        reg = self._opt_in()
        data = {"status": "success", "amount": reg.amount_subunit,
                "currency": "GHS", "reference": reg.payment_reference}
        with mock.patch("payments.paystack.verify_transaction", return_value=data), \
                mock.patch("workshop.emails.send_branded_email", return_value=True):
            resp = self.client.post(
                reverse("workshop:pay_verify", args=[reg.pk]),
                {"reference": reg.payment_reference},
            )
        self.assertEqual(resp.status_code, 200)
        reg.refresh_from_db()
        self.assertTrue(reg.is_paid)
        self.assertTrue(reg.registration_complete)

    def test_no_confirmation_is_sent_while_the_fee_is_outstanding(self):
        """They must not be told they're registered when they aren't."""
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send, \
                mock.patch("notifications.sms.send_sms") as sms:
            self.client.post(self.url, _form())
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertFalse(
            any("Registration received" in s for s in subjects),
            f"a confirmation went out for an unpaid registration: {subjects}",
        )
        # What they do get is the way back to the fee.
        self.assertTrue(any("Certificate fee outstanding" in s for s in subjects), subjects)
        self.assertTrue(sms.called)

    def test_a_confirmation_is_sent_once_paid(self):
        reg = self._opt_in()
        data = {"status": "success", "amount": reg.amount_subunit,
                "currency": "GHS", "reference": reg.payment_reference}
        with mock.patch("payments.paystack.verify_transaction", return_value=data), \
                mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(reverse("workshop:pay_verify", args=[reg.pk]),
                             {"reference": reg.payment_reference})
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertTrue(any("Registration received" in s for s in subjects), subjects)

    def test_the_checkout_says_payment_is_required_and_offers_no_skip(self):
        reg = self._opt_in()
        html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        self.assertIn("Payment is required to complete your registration", html)
        self.assertIn("not registered for this", html)
        self.assertNotIn("pay later", html)

    def test_the_thanks_page_says_it_is_not_complete(self):
        reg = self._opt_in()
        html = self.client.get(f"{reverse('workshop:thanks')}?r={reg.pk}").content.decode()
        self.assertIn("One step left", html)
        self.assertIn("Payment is required", html)
        self.assertIn("not complete", html)

    def test_the_form_warns_before_they_commit(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Certificate fee — payment required", html)
        self.assertIn("registration isn't complete until", html)


class DeclineCertificateTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        self.url = reverse("workshop:register", args=[self.ws.slug])

    def _pending(self, **ws_kwargs):
        if ws_kwargs:
            for k, v in ws_kwargs.items():
                setattr(self.ws, k, v)
            self.ws.save()
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        return WorkshopRegistration.objects.get()

    def test_dropping_the_certificate_settles_the_fee_at_zero(self):
        reg = self._pending()
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            resp = self.client.post(reverse("workshop:decline_certificate", args=[reg.pk]))
        self.assertEqual(resp.status_code, 302)
        reg.refresh_from_db()
        self.assertFalse(reg.wants_certificate)
        self.assertEqual(reg.payment_status, PS.NOT_REQUIRED)
        self.assertEqual(reg.amount, Decimal("0.00"))
        self.assertTrue(reg.registration_complete)
        self.assertFalse(reg.certificate_ready)

    def test_it_confirms_the_registration_by_email(self):
        reg = self._pending()
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(reverse("workshop:decline_certificate", args=[reg.pk]))
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertTrue(any("Registration received" in s for s in subjects), subjects)

    def test_a_compulsory_certificate_cannot_be_dropped(self):
        reg = self._pending(certificate_required=True)
        self.assertTrue(reg.certificate_required_at_signup)
        resp = self.client.post(reverse("workshop:decline_certificate", args=[reg.pk]))
        self.assertEqual(resp.status_code, 302)
        reg.refresh_from_db()
        self.assertTrue(reg.wants_certificate)
        self.assertEqual(reg.payment_status, PS.PENDING)
        self.assertFalse(reg.registration_complete)

    def test_the_option_is_offered_only_when_the_certificate_was_a_choice(self):
        optional = self._pending()
        html = self.client.get(reverse("workshop:pay", args=[optional.pk])).content.decode()
        self.assertIn("don't want a certificate after all", html)

        WorkshopRegistration.objects.all().delete()
        compulsory = self._pending(certificate_required=True)
        html = self.client.get(reverse("workshop:pay", args=[compulsory.pk])).content.decode()
        self.assertNotIn("don't want a certificate after all", html)

    def test_a_paid_certificate_is_not_undone(self):
        reg = self._pending()
        reg.payment_status = PS.SUCCESS
        reg.paid_at = timezone.now()
        reg.save()
        self.client.post(reverse("workshop:decline_certificate", args=[reg.pk]))
        reg.refresh_from_db()
        self.assertTrue(reg.is_paid)
        self.assertTrue(reg.wants_certificate)
        self.assertEqual(reg.amount, Decimal("35.00"))

    def test_it_is_post_only(self):
        reg = self._pending()
        resp = self.client.get(reverse("workshop:decline_certificate", args=[reg.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_the_payment_reference_is_kept_for_a_late_payment(self):
        """If a payment for the quoted reference ever does land, the row it
        belongs to must still be findable."""
        reg = self._pending()
        ref = reg.payment_reference
        self.assertTrue(ref)
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(reverse("workshop:decline_certificate", args=[reg.pk]))
        reg.refresh_from_db()
        self.assertEqual(reg.payment_reference, ref)


class CompulsoryUnchangedTests(PinnedRateMixin, TestCase):
    """The compulsory path already required payment; it must still."""

    def setUp(self):
        super().setUp()
        self.ws = _workshop(certificate_required=True)

    def test_still_incomplete_until_paid(self):
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        self.assertFalse(reg.registration_complete)
        self.assertTrue(reg.payment_outstanding)

    def test_a_free_compulsory_certificate_is_complete_at_once(self):
        self.ws.certificate_fee = Decimal("0.00")
        self.ws.save()
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        self.assertTrue(reg.registration_complete)
        self.assertTrue(reg.certificate_ready)


class AdminCountsTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )
        self.client.force_login(admin)
        self.manage = reverse("workshop_admin:manage", args=[self.ws.pk])

    def _reg(self, email, **kw):
        base = dict(workshop=self.ws, name=email.split("@")[0], institution="UG",
                    email=email, phone="0241234567")
        base.update(kw)
        return WorkshopRegistration.objects.create(**base)

    def test_an_unpaid_opt_in_is_not_counted_as_registered(self):
        self._reg("paid@example.com", wants_certificate=True,
                  payment_status=PS.SUCCESS, amount=Decimal("35.00"), paid_at=timezone.now())
        self._reg("nocert@example.com", payment_status=PS.NOT_REQUIRED)
        self._reg("owes@example.com", wants_certificate=True,
                  payment_status=PS.PENDING, amount=Decimal("35.00"))

        counts = self.client.get(self.manage).context["counts"]
        self.assertEqual(counts["all"], 3)          # every entry is still visible
        self.assertEqual(counts["confirmed"], 2)    # but only two are registered
        self.assertEqual(counts["unpaid"], 1)
        self.assertEqual(counts["outstanding"], Decimal("35.00"))

    def test_the_admin_is_told_a_registration_is_awaiting_payment(self):
        # _notify_admin_of_registration imports send_branded_email inside
        # the function, so it has to be patched at its source.
        with mock.patch("notifications.emails.send_branded_email", return_value=True) as send:
            self.client.post(
                reverse("workshop:register", args=[self.ws.slug]), _form(),
            )
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertTrue(any("awaiting payment" in s.lower() for s in subjects), subjects)
