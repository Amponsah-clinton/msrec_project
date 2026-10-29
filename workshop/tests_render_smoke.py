"""Every workshop page the compulsory-certificate switch touches must render
in both modes -- a template error here is invisible until a real visitor or
an admin hits the page."""
import os
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from reportlab.lib.units import mm

from reviewer_dashboard.certificate import BRASS

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


class RenderSmokeTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()  # pins the exchange rate
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )

    def _workshop(self, **kwargs):
        fields = dict(
            title="Ethics Workshop",
            starts_at=timezone.now() + timezone.timedelta(days=5),
            certificate_fee=Decimal("150.00"), fee_currency="GHS",
            is_published=True,
        )
        fields.update(kwargs)
        return Workshop.objects.create(**fields)

    def _reg(self, ws, **kwargs):
        # A distinct email per row by default: one workshop allows only one
        # active registration per address, so fixtures that need several
        # people on one workshop must use several addresses.
        self._seq = getattr(self, "_seq", 0) + 1
        base = dict(
            workshop=ws, name="Ama Mensah", institution="UG",
            email=f"ama{self._seq}@example.com", phone="0241234567",
        )
        base.update(kwargs)
        return WorkshopRegistration.objects.create(**base)

    def test_public_pages_render_in_both_modes(self):
        for required in (False, True):
            for fee in (Decimal("150.00"), Decimal("0.00")):
                with self.subTest(required=required, fee=fee):
                    ws = self._workshop(certificate_required=required, certificate_fee=fee)
                    self.assertEqual(self.client.get(reverse("workshop:list")).status_code, 200)
                    self.assertEqual(
                        self.client.get(reverse("workshop:register", args=[ws.slug])).status_code, 200
                    )

    def test_thanks_page_renders_for_every_payment_state(self):
        ws = self._workshop(certificate_required=True)
        states = [
            dict(wants_certificate=False, payment_status=PS.NOT_REQUIRED),
            dict(wants_certificate=True, payment_status=PS.NOT_REQUIRED),
            dict(wants_certificate=True, certificate_required_at_signup=True,
                 payment_status=PS.PENDING, amount=Decimal("150.00")),
            dict(wants_certificate=True, certificate_required_at_signup=True,
                 payment_status=PS.FAILED, amount=Decimal("150.00")),
            dict(wants_certificate=True, certificate_required_at_signup=True,
                 payment_status=PS.SUCCESS, amount=Decimal("150.00"), paid_at=timezone.now()),
        ]
        for state in states:
            with self.subTest(**state):
                reg = self._reg(ws, **state)
                resp = self.client.get(f"{reverse('workshop:thanks')}?r={reg.pk}")
                self.assertEqual(resp.status_code, 200)

    def test_pay_page_renders_in_both_modes(self):
        for required in (False, True):
            with self.subTest(required=required):
                ws = self._workshop(certificate_required=required)
                reg = self._reg(
                    ws, wants_certificate=True, certificate_required_at_signup=required,
                    payment_status=PS.PENDING, amount=Decimal("150.00"),
                    payment_reference="REF-%s" % required,
                )
                self.assertEqual(self.client.get(reverse("workshop:pay", args=[reg.pk])).status_code, 200)

    def test_documents_page_renders_for_a_free_certificate(self):
        ws = self._workshop(certificate_required=True, certificate_fee=Decimal("0.00"))
        reg = self._reg(
            ws, wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.NOT_REQUIRED, approved_at=timezone.now(),
        )
        reg.ensure_download_token()
        reg.save()
        resp = self.client.get(reverse("workshop:documents", kwargs={"token": reg.download_token}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Certificate of Participation")

    def test_pages_render_with_no_exchange_rate_available(self):
        """Every price surface has to survive the rates API being down."""
        ws = self._workshop(certificate_required=True)
        reg = self._reg(
            ws, wants_certificate=True, certificate_required_at_signup=True,
            payment_status=PS.PENDING, amount=Decimal("150.00"), payment_reference="REF-X",
        )
        with mock.patch.dict(os.environ, {"USD_GHS_RATE": ""}), \
                mock.patch("payments.currency._fetch_rate", return_value=None):
            cache.clear()
            for url in (
                reverse("workshop:list"),
                reverse("workshop:register", args=[ws.slug]),
                reverse("workshop:pay", args=[reg.pk]),
                f"{reverse('workshop:thanks')}?r={reg.pk}",
            ):
                with self.subTest(url=url):
                    resp = self.client.get(url)
                    self.assertEqual(resp.status_code, 200)
                    self.assertNotContains(resp, "US$")

    def test_admin_manage_page_renders_in_both_modes(self):
        self.client.force_login(self.admin)
        for required in (False, True):
            with self.subTest(required=required):
                ws = self._workshop(certificate_required=required)
                self._reg(
                    ws, wants_certificate=True, certificate_required_at_signup=required,
                    payment_status=PS.PENDING, amount=Decimal("150.00"),
                )
                self._reg(ws, name="Kojo", email="kojo@example.com", wants_certificate=False)
                resp = self.client.get(reverse("workshop_admin:manage", args=[ws.pk]))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, 'name="certificate_required"')
                if required:
                    self.assertContains(resp, "Certificates are compulsory for this workshop")
                else:
                    self.assertContains(resp, "Certificates are optional")


class CertificateProgrammeTests(TestCase):
    """The programme is the subject of the certificate, so it gets its own
    line rather than sitting buried in the body prose."""

    def _workshop(self, **over):
        from django.utils import timezone
        from workshop.models import Workshop
        fields = dict(title="Advanced Workshop on Research Ethics", slug="prog-test",
                      starts_at=timezone.now())
        fields.update(over)
        return Workshop.objects.create(**fields)

    def test_the_body_is_split_around_the_placeholder(self):
        from workshop.certificate import _split_statement
        lead, programme, tail = _split_statement(
            "participated in the {workshop} organised by the Committee, and is recognised.",
            "Research Ethics Essentials", "Kwame Mensah")
        self.assertEqual(lead, "participated in the")
        self.assertEqual(programme, "Research Ethics Essentials")
        self.assertTrue(tail.startswith("organised by the Committee"))

    def test_a_body_without_the_placeholder_still_gets_a_programme_line(self):
        from workshop.certificate import _split_statement
        lead, programme, tail = _split_statement(
            "has attended and completed the programme shown above.", "Ethics 101", "Ama")
        self.assertEqual(lead, "")
        self.assertEqual(programme, "Ethics 101")
        self.assertIn("has attended", tail)

    def test_the_name_placeholder_still_works_on_both_sides(self):
        from workshop.certificate import _split_statement
        lead, _, tail = _split_statement("{name} joined the {workshop}, and {name} passed.",
                                         "Ethics 101", "Ama Serwaa")
        self.assertEqual(lead, "Ama Serwaa joined the")
        self.assertIn("Ama Serwaa passed", tail)

    def test_the_programme_is_set_larger_than_the_prose_around_it(self):
        # What "distinct" means in practice: it must not come out at the
        # same size as the sentence it used to be buried in.
        from workshop.certificate import _statement_layout
        rows, _ = _statement_layout(
            "participated in the", "Research Ethics Essentials",
            "organised by the Metascholar Research Ethics Committee, and is recognised for "
            "their active engagement and commitment to advancing ethical research practice.",
            show_prose=True, budget=34 * mm)
        sizes = {kind: f.style.fontSize for kind, f, _ in rows if f is not None}
        self.assertGreater(sizes["programme"], sizes["prose"] + 2)
        self.assertEqual([f.style.textColor for k, f, _ in rows if k == "programme"], [BRASS])

    def test_a_very_long_programme_still_clears_the_seal(self):
        from workshop.certificate import _statement_layout
        budget = 34 * mm
        _, total = _statement_layout(
            "participated in the",
            "Regional Capacity-Building Workshop on Research Ethics Committee Governance, "
            "Standard Operating Procedures and Post-Approval Oversight for West Africa",
            "organised by the Metascholar Research Ethics Committee, and is recognised for "
            "their active engagement and commitment to advancing ethical research practice.",
            show_prose=True, budget=budget)
        self.assertLessEqual(total, budget)

    def test_turning_the_programme_off_puts_it_back_in_the_sentence(self):
        # Splitting the body and then dropping the programme would leave
        # "participated in the organised by the Committee".
        from workshop.certificate import render_sample_certificate_pdf
        ws = self._workshop(cert_show_programme=False)
        data = render_sample_certificate_pdf(ws, "Kwame Mensah")
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn("{workshop}", ws.cert_body)      # the wording is untouched

    def test_every_combination_of_toggles_renders(self):
        from workshop.certificate import render_sample_certificate_pdf
        from itertools import product
        for i, (prog, body, seal) in enumerate(product([True, False], repeat=3)):
            with self.subTest(programme=prog, body=body, seal=seal):
                ws = self._workshop(slug=f"combo-{i}", cert_show_programme=prog,
                                    cert_show_body=body, cert_show_seal=seal)
                self.assertTrue(render_sample_certificate_pdf(ws, "Kwame Mensah").startswith(b"%PDF"))

    def test_markup_in_a_title_cannot_reach_the_pdf_parser(self):
        from workshop.certificate import render_sample_certificate_pdf
        ws = self._workshop(slug="markup", title="Risk <b>&</b> Benefit Workshop")
        self.assertTrue(render_sample_certificate_pdf(ws, "Kwame Mensah").startswith(b"%PDF"))
