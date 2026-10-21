"""CSV / PDF export of a workshop's registrations: follows the same chip,
search and ticks as the Registrations tab's send buttons."""
import csv
import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from workshop.models import WorkshopRegistration
from workshop.tests_compulsory_certificate import PinnedRateMixin, _workshop

PS = WorkshopRegistration.PaymentStatus


class RegistrationExportTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop(title="AI Ethics & Responsible Research")
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123", first_name="Ada", last_name="Admin")
        self.client.force_login(admin)
        self.url = reverse("workshop_admin:registrations_export", args=[self.ws.pk])
        self.paid = self._reg("Kofi Paid", "kofi@example.com", "0241111111", wants_certificate=True,
                              payment_status=PS.SUCCESS, amount=Decimal("150.00"))
        self.owes = self._reg("Ama Owes", "ama@example.com", "+233 24 222 2222", wants_certificate=True,
                              payment_status=PS.PENDING, amount=Decimal("150.00"))
        self.ghana = self._reg("Ɔsɛi Kwame", "osei@example.com", "")

    def _reg(self, name, email, phone, **kw):
        return WorkshopRegistration.objects.create(
            workshop=self.ws, name=name, institution="University of Ghana", email=email, phone=phone, **kw)

    def _csv(self, **params):
        resp = self.client.get(self.url, {"format": "csv", **params})
        self.assertEqual(resp.status_code, 200)
        text = resp.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        return resp, list(csv.reader(io.StringIO(text.lstrip("﻿"))))

    def test_csv_everyone(self):
        resp, rows = self._csv(scope="all")
        self.assertIn("attachment;", resp["Content-Disposition"])
        self.assertIn("ai-ethics-responsible-research-registrations-", resp["Content-Disposition"])
        self.assertEqual(rows[0][:4], ["No.", "Name", "Institution", "Email"])
        self.assertEqual(sorted(r[1] for r in rows[1:]), ["Ama Owes", "Kofi Paid", "Ɔsɛi Kwame"])
        ama = next(r for r in rows if r[1] == "Ama Owes")
        self.assertEqual(ama[5], "0242222222")          # SMS number, cleaned
        self.assertEqual(ama[7], "Payment pending")
        self.assertEqual(ama[8], "150.00")

    def test_csv_follows_the_chip(self):
        _, rows = self._csv(scope="paid")
        self.assertEqual([r[1] for r in rows[1:]], ["Kofi Paid"])
        _, rows = self._csv(scope="unpaid")
        self.assertEqual([r[1] for r in rows[1:]], ["Ama Owes"])

    def test_csv_follows_ticks_and_search_ids_within_this_workshop_only(self):
        other = _workshop(title="Other")
        outsider = WorkshopRegistration.objects.create(workshop=other, name="Out Sider", institution="X", email="o@x.org")
        _, rows = self._csv(scope="all", reg_ids=f"{self.owes.pk},{outsider.pk}")
        self.assertEqual([r[1] for r in rows[1:]], ["Ama Owes"])

    def test_a_search_that_found_nobody_exports_nobody(self):
        _, rows = self._csv(scope="all", reg_ids="0")
        self.assertEqual(len(rows), 1)  # just the header

    def test_pdf(self):
        resp = self.client.get(self.url, {"format": "pdf", "scope": "all", "label": "Everyone (3)"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(".pdf", resp["Content-Disposition"])
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertGreater(len(resp.content), 2000)

    def test_empty_pdf_still_renders(self):
        resp = self.client.get(self.url, {"format": "pdf", "reg_ids": "0"})
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_page_has_export_buttons(self):
        resp = self.client.get(reverse("workshop_admin:manage", args=[self.ws.pk]))
        self.assertContains(resp, 'class="wsa-btn ghost wsa-export-link" data-format="csv"')
        self.assertContains(resp, 'data-format="pdf"')

    def test_staff_only(self):
        self.client.logout()
        resp = self.client.get(self.url, {"format": "csv"})
        self.assertEqual(resp.status_code, 302)
