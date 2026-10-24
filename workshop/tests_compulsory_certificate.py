"""Tests for the compulsory-certificate switch on a workshop.

Off (the default), the public form asks each registrant whether they want a
certificate and only those who say yes are charged. On, the question is gone:
every registration is booked for a certificate, sent to checkout, and isn't
complete until the fee is paid.
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
    """Pins the GHS->USD rate for every test in the class.

    Both doors are shut, deliberately. The env var is what the code reads
    first, and blocking _fetch_rate as well means that if the pin ever fails
    to apply, the test fails loudly instead of quietly reaching the live
    rates API -- which is how this suite briefly became flaky: a live rate
    of 11.653982 renders US$12.87, not the US$12.88 these tests assert.

    A fresh patcher per test (rather than one shared module-level instance
    used as a class decorator) is the point: mock patchers hold state about
    what they replaced, so reusing one across classes is not safe.
    """

    RATE = "11.65"  # GHS 150.00 / 11.65 -> US$12.88

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
    defaults = {
        "title": "Research Ethics Workshop",
        "starts_at": timezone.now() + timezone.timedelta(days=7),
        "certificate_fee": Decimal("150.00"),
        "fee_currency": "GHS",
        "is_published": True,
    }
    defaults.update(kwargs)
    return Workshop.objects.create(**defaults)


def _form(**overrides):
    data = {
        "name": "Ama Mensah",
        "institution": "University Of Ghana",
        "email": "ama@example.com",
        "phone": "0241234567",
        "comments": "",
    }
    data.update(overrides)
    return data


class OptionalCertificateTests(PinnedRateMixin, TestCase):
    """The existing behaviour, which the switch must leave untouched."""

    def setUp(self):
        super().setUp()  # pins the exchange rate
        self.ws = _workshop()

    def test_form_asks_the_question(self):
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertIn('type="radio" name="wants_certificate"', html)
        self.assertNotIn("Included for everyone", html)

    def test_the_optional_fee_note_also_quotes_dollars(self):
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertIn("US$12.88", html)

    def test_not_answering_is_rejected(self):
        resp = self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(WorkshopRegistration.objects.count(), 0)

    def test_opting_out_pays_nothing(self):
        self.client.post(
            reverse("workshop:register", args=[self.ws.slug]),
            _form(wants_certificate="no"),
        )
        reg = WorkshopRegistration.objects.get()
        self.assertFalse(reg.wants_certificate)
        self.assertFalse(reg.certificate_required_at_signup)
        self.assertEqual(reg.payment_status, PS.NOT_REQUIRED)
        self.assertEqual(reg.amount, Decimal("0.00"))
        self.assertFalse(reg.certificate_ready)
        self.assertFalse(reg.payment_outstanding)
        self.assertTrue(reg.registration_complete)

    def test_opting_in_goes_to_checkout(self):
        resp = self.client.post(
            reverse("workshop:register", args=[self.ws.slug]),
            _form(wants_certificate="yes"),
        )
        reg = WorkshopRegistration.objects.get()
        self.assertRedirects(resp, reverse("workshop:pay", args=[reg.pk]), fetch_redirect_response=False)
        self.assertTrue(reg.wants_certificate)
        self.assertFalse(reg.certificate_required_at_signup)
        self.assertEqual(reg.payment_status, PS.PENDING)
        self.assertEqual(reg.amount, Decimal("150.00"))

    def test_an_unpaid_opt_in_is_not_a_completed_registration(self):
        """Asking for a certificate commits you to paying for it, so there
        is no "pay later" on the optional path either -- see
        tests_payment_required for the full rule."""
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(
                reverse("workshop:register", args=[self.ws.slug]),
                _form(wants_certificate="yes"),
            )
        reg = WorkshopRegistration.objects.get()
        html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        self.assertNotIn("pay later", html)
        self.assertIn("Payment is required to complete your registration", html)
        self.assertFalse(reg.registration_complete)
        # What they can do instead is drop the certificate, which is a
        # change of choice rather than a non-payment.
        self.assertIn("don't want a certificate after all", html)


class CompulsoryCertificateTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()  # pins the exchange rate
        self.ws = _workshop(certificate_required=True)

    def test_form_states_the_fee_instead_of_asking(self):
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertNotIn('type="radio" name="wants_certificate"', html)
        self.assertIn("Certificate of participation", html)
        self.assertIn("150.00", html)

    def test_the_form_quotes_the_dollar_equivalent(self):
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertIn("US$12.88", html)

    def test_a_free_certificate_quotes_no_dollar_figure(self):
        self.ws.certificate_fee = Decimal("0.00")
        self.ws.save()
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertNotIn("US$", html)
        self.assertIn("No fee", html)

    def test_everyone_is_charged_and_sent_to_checkout(self):
        resp = self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        self.assertRedirects(resp, reverse("workshop:pay", args=[reg.pk]), fetch_redirect_response=False)
        self.assertTrue(reg.wants_certificate)
        self.assertTrue(reg.certificate_required_at_signup)
        self.assertEqual(reg.payment_status, PS.PENDING)
        self.assertEqual(reg.amount, Decimal("150.00"))
        self.assertEqual(reg.currency, "GHS")
        self.assertTrue(reg.payment_reference)

    def test_posting_no_cannot_opt_anyone_out(self):
        """The question isn't asked, so a forged "no" must not get through."""
        self.client.post(
            reverse("workshop:register", args=[self.ws.slug]),
            _form(wants_certificate="no"),
        )
        reg = WorkshopRegistration.objects.get()
        self.assertTrue(reg.wants_certificate)
        self.assertEqual(reg.payment_status, PS.PENDING)

    def test_registration_is_incomplete_until_paid(self):
        self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        self.assertTrue(reg.payment_outstanding)
        self.assertFalse(reg.registration_complete)
        self.assertFalse(reg.certificate_ready)

        html = self.client.get(f"{reverse('workshop:thanks')}?r={reg.pk}").content.decode()
        self.assertIn("One step left", html)
        self.assertIn("not complete", html)

    def test_pay_page_shows_cedis_and_the_dollar_equivalent(self):
        self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        # The charge, in cedis.
        self.assertIn("GHS", html)
        self.assertIn("150.00", html)
        # The guide, in dollars, labelled as approximate.
        self.assertIn("US$12.88", html)
        self.assertIn("Approximate equivalent", html)
        self.assertIn("converts at its own rate", html)
        # Paystack is still handed cedi subunits, never the dollar figure.
        self.assertIn('currency: "GHS"', html)
        self.assertIn("amount: 15000", html)

    def test_pay_page_hides_the_dollar_line_when_no_rate_is_available(self):
        """No rate must degrade to the cedi price alone, never to a guess."""
        self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        with mock.patch.dict(os.environ, {"USD_GHS_RATE": ""}), \
                mock.patch("payments.currency._fetch_rate", return_value=None):
            cache.clear()
            html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        self.assertNotIn("US$", html)
        self.assertIn("150.00", html)

    def test_pay_page_offers_no_way_to_skip(self):
        self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        self.assertNotIn("pay later", html)
        self.assertIn("Payment is required to complete your registration", html)
        # Nothing to decline when the workshop compels the certificate.
        self.assertNotIn("don't want a certificate after all", html)

    def test_paying_completes_the_registration(self):
        self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        paystack = {
            "status": "success", "amount": reg.amount_subunit, "currency": "GHS",
            "reference": reg.payment_reference,
        }
        with mock.patch("payments.paystack.verify_transaction", return_value=paystack):
            resp = self.client.post(
                reverse("workshop:pay_verify", args=[reg.pk]),
                {"reference": reg.payment_reference},
            )
        self.assertEqual(resp.status_code, 200)
        reg.refresh_from_db()
        self.assertTrue(reg.is_paid)
        self.assertTrue(reg.certificate_ready)
        self.assertTrue(reg.registration_complete)
        self.assertTrue(reg.certificate_ref)

    def test_zero_fee_means_a_free_certificate_for_all(self):
        self.ws.certificate_fee = Decimal("0.00")
        self.ws.save()
        resp = self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        # Nobody is sent to a 0.00 checkout.
        self.assertRedirects(
            resp, f"{reverse('workshop:thanks')}?r={reg.pk}", fetch_redirect_response=False
        )
        self.assertTrue(reg.wants_certificate)
        self.assertEqual(reg.payment_status, PS.NOT_REQUIRED)
        self.assertTrue(reg.certificate_ready)
        self.assertTrue(reg.registration_complete)


class CertificateEntitlementTests(TestCase):
    """Who gets an actual certificate out the other end."""

    def setUp(self):
        self.ws = _workshop(certificate_required=True)

    def _reg(self, **kwargs):
        base = dict(
            workshop=self.ws, name="Ama Mensah", institution="UG",
            email="ama@example.com", phone="0241234567",
        )
        base.update(kwargs)
        return WorkshopRegistration.objects.create(**base)

    def test_unpaid_compulsory_registration_gets_the_letter_only(self):
        reg = self._reg(
            wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.PENDING, amount=Decimal("150.00"),
        )
        from workshop import approval
        with mock.patch("workshop.approval.send_branded_email", return_value=True) as send:
            ok, _ = approval.approve_and_send(reg, self.ws)
        self.assertTrue(ok)
        names = [a[0] for a in send.call_args.kwargs["attachments"]]
        self.assertEqual(len(names), 1)
        self.assertIn("Confirmation_of_Participation", names[0])

    def test_paid_registration_gets_both_documents(self):
        reg = self._reg(
            wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.SUCCESS, amount=Decimal("150.00"), paid_at=timezone.now(),
        )
        from workshop import approval
        with mock.patch("workshop.approval.send_branded_email", return_value=True) as send:
            approval.approve_and_send(reg, self.ws)
        names = sorted(a[0] for a in send.call_args.kwargs["attachments"])
        self.assertEqual(len(names), 2)
        self.assertTrue(any("Certificate" in n for n in names))

    def test_free_certificate_is_still_issued(self):
        reg = self._reg(
            wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.NOT_REQUIRED, amount=Decimal("0.00"),
        )
        from workshop import approval
        with mock.patch("workshop.approval.send_branded_email", return_value=True) as send:
            approval.approve_and_send(reg, self.ws)
        names = sorted(a[0] for a in send.call_args.kwargs["attachments"])
        self.assertEqual(len(names), 2)

    def test_unpaid_certificate_cannot_be_downloaded(self):
        reg = self._reg(
            wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.PENDING, amount=Decimal("150.00"),
            approved_at=timezone.now(),
        )
        reg.ensure_download_token()
        reg.save()
        url = reverse("workshop:download_document", kwargs={"token": reg.download_token, "kind": "certificate"})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_free_certificate_can_be_downloaded(self):
        reg = self._reg(
            wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.NOT_REQUIRED, amount=Decimal("0.00"),
            approved_at=timezone.now(),
        )
        reg.ensure_download_token()
        reg.save()
        url = reverse("workshop:download_document", kwargs={"token": reg.download_token, "kind": "certificate"})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


class AdminSwitchTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()  # pins the exchange rate
        self.ws = _workshop()
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )
        self.client.force_login(self.admin)
        self.url = reverse("workshop_admin:manage", args=[self.ws.pk])

    def _settings_post(self, **extra):
        data = {
            "action": "save_settings", "tab": "settings",
            "title": self.ws.title, "certificate_fee": "150.00", "fee_currency": "GHS",
            "is_published": "on",
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_switch_turns_compulsory_on_and_off(self):
        self._settings_post(certificate_required="on")
        self.ws.refresh_from_db()
        self.assertTrue(self.ws.certificate_required)

        self._settings_post()  # checkbox absent = off
        self.ws.refresh_from_db()
        self.assertFalse(self.ws.certificate_required)

    def test_requiring_it_for_earlier_opt_outs_charges_them(self):
        opted_out = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Kojo", institution="UG", email="kojo@example.com",
            phone="0241112222", wants_certificate=False, payment_status=PS.NOT_REQUIRED,
        )
        self._settings_post(certificate_required="on")

        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(self.url, {
                "action": "require_certificates", "tab": "registrations", "scope": "no_cert",
            })
        opted_out.refresh_from_db()
        self.assertTrue(opted_out.wants_certificate)
        self.assertTrue(opted_out.certificate_required_at_signup)
        self.assertEqual(opted_out.payment_status, PS.PENDING)
        self.assertEqual(opted_out.amount, Decimal("150.00"))
        self.assertTrue(opted_out.payment_reference)

    def test_it_refuses_while_the_switch_is_off(self):
        reg = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Kojo", institution="UG", email="kojo@example.com",
            phone="0241112222", wants_certificate=False,
        )
        self.client.post(self.url, {
            "action": "require_certificates", "tab": "registrations", "scope": "no_cert",
        })
        reg.refresh_from_db()
        self.assertFalse(reg.wants_certificate)

    def test_a_paid_registrant_is_left_alone(self):
        paid = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Abena", institution="UG", email="abena@example.com",
            phone="0243334444", wants_certificate=True, payment_status=PS.SUCCESS,
            amount=Decimal("150.00"), paid_at=timezone.now(), payment_reference="OLD-REF",
        )
        self._settings_post(certificate_required="on")
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(self.url, {
                "action": "require_certificates", "tab": "registrations", "scope": "no_cert",
            })
        paid.refresh_from_db()
        self.assertEqual(paid.payment_status, PS.SUCCESS)
        self.assertEqual(paid.payment_reference, "OLD-REF")

    def test_payment_link_only_goes_to_people_who_owe(self):
        owes = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Kojo", institution="UG", email="kojo@example.com",
            phone="0241112222", wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.PENDING, amount=Decimal("150.00"), payment_reference="REF-1",
        )
        WorkshopRegistration.objects.create(
            workshop=self.ws, name="Abena", institution="UG", email="abena@example.com",
            phone="0243334444", wants_certificate=False, payment_status=PS.NOT_REQUIRED,
        )
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(self.url, {
                "action": "send_payment_link", "tab": "registrations", "scope": "unpaid",
            })
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.kwargs["to"], owes.email)

    def test_manage_page_counts_what_is_outstanding(self):
        WorkshopRegistration.objects.create(
            workshop=self.ws, name="Kojo", institution="UG", email="kojo@example.com",
            phone="0241112222", wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.PENDING, amount=Decimal("150.00"),
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["counts"]["unpaid"], 1)
        self.assertEqual(resp.context["counts"]["outstanding"], Decimal("150.00"))


class CheckoutEmailTests(TestCase):
    """A compulsory fee must come with a way back to it."""

    def test_compulsory_registration_is_emailed_the_payment_link(self):
        ws = _workshop(certificate_required=True)
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(reverse("workshop:register", args=[ws.slug]), _form())
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertTrue(any("Certificate fee outstanding" in s for s in subjects), subjects)

    def test_an_optional_opt_in_is_also_sent_the_payment_link(self):
        """It used not to be, back when an unpaid opt-in still counted as a
        registration. Now it doesn't count until the fee is paid, so the way
        back to the checkout has to reach them too."""
        ws = _workshop()
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(
                reverse("workshop:register", args=[ws.slug]), _form(wants_certificate="yes")
            )
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertTrue(any("Certificate fee outstanding" in s for s in subjects), subjects)

    def test_declining_the_certificate_needs_no_payment_link(self):
        ws = _workshop()
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(
                reverse("workshop:register", args=[ws.slug]), _form(wants_certificate="no")
            )
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertFalse(any("Certificate fee outstanding" in s for s in subjects), subjects)


class AdminDollarGuideTests(PinnedRateMixin, TestCase):
    """Staff should see the same dollar figure an overseas participant is
    quoted, so a fee change is never a surprise to either of them."""

    def setUp(self):
        super().setUp()  # pins the exchange rate
        self.ws = _workshop(certificate_required=True)
        admin = User.objects.create_superuser(
            email="admin2@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )
        self.client.force_login(admin)

    def test_the_fee_field_quotes_the_dollar_equivalent(self):
        html = self.client.get(reverse("workshop_admin:manage", args=[self.ws.pk])).content.decode()
        self.assertIn("US$12.88", html)
        self.assertIn("the charge is always in GHS", html)

    def test_a_zero_fee_quotes_no_dollar_figure(self):
        self.ws.certificate_fee = Decimal("0.00")
        self.ws.save()
        html = self.client.get(reverse("workshop_admin:manage", args=[self.ws.pk])).content.decode()
        self.assertNotIn("US$", html)
