"""Tests for the compulsory-certificate switch on a workshop.

Off (the default), the public form asks each registrant whether they want a
certificate and only those who say yes are charged. On, the question is gone:
every registration is booked for a certificate, sent to checkout, and isn't
complete until the fee is paid.
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from workshop.models import Workshop, WorkshopRegistration

PS = WorkshopRegistration.PaymentStatus


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


class OptionalCertificateTests(TestCase):
    """The existing behaviour, which the switch must leave untouched."""

    def setUp(self):
        self.ws = _workshop()

    def test_form_asks_the_question(self):
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertIn('type="radio" name="wants_certificate"', html)
        self.assertNotIn("A certificate of participation is included", html)

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

    def test_an_unpaid_opt_in_may_skip_payment(self):
        """Nothing is compulsory, so "I'll pay later" stays on the pay page."""
        self.client.post(
            reverse("workshop:register", args=[self.ws.slug]),
            _form(wants_certificate="yes"),
        )
        reg = WorkshopRegistration.objects.get()
        html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        self.assertIn("pay later", html)
        self.assertTrue(reg.registration_complete)


class CompulsoryCertificateTests(TestCase):
    def setUp(self):
        self.ws = _workshop(certificate_required=True)

    def test_form_states_the_fee_instead_of_asking(self):
        html = self.client.get(reverse("workshop:register", args=[self.ws.slug])).content.decode()
        self.assertNotIn('type="radio" name="wants_certificate"', html)
        self.assertIn("A certificate of participation is included", html)
        self.assertIn("GHS 150.00", html)

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

    def test_pay_page_offers_no_way_to_skip(self):
        self.client.post(reverse("workshop:register", args=[self.ws.slug]), _form())
        reg = WorkshopRegistration.objects.get()
        html = self.client.get(reverse("workshop:pay", args=[reg.pk])).content.decode()
        self.assertNotIn("pay later", html)
        self.assertIn("only complete once this fee is paid", html)

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


class AdminSwitchTests(TestCase):
    def setUp(self):
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

    def test_an_optional_opt_in_is_not_chased_automatically(self):
        ws = _workshop()
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(
                reverse("workshop:register", args=[ws.slug]), _form(wants_certificate="yes")
            )
        subjects = [c.kwargs.get("subject", "") for c in send.call_args_list]
        self.assertFalse(any("Certificate fee outstanding" in s for s in subjects), subjects)
