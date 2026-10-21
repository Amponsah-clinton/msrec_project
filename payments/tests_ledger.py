"""The admin Finance page's income, grouped: ethics application review fees
by review type, workshop certificate fees by workshop -- never one mixed list."""
import csv
import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from payments import ledger
from payments.models import Payment
from workshop.models import Workshop, WorkshopRegistration

PS = WorkshopRegistration.PaymentStatus


class FinanceGroupingTests(TestCase):
    def setUp(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123", first_name="Ada", last_name="Admin")
        self.client.force_login(admin)
        self.url = reverse("admin_dashboard:finance")
        applicant = User.objects.create_user(
            email="applicant@example.com", password="pw-123456", first_name="Yaw", last_name="Mensah")
        # Purpose is how checkout records the fee charged ("<label> fee").
        for ref, purpose, amount, status in (
            ("APP-1", "PhD / Doctoral Student Research fee", "500.00", Payment.Status.SUCCESS),
            ("APP-2", "PhD / Doctoral Student Research fee", "500.00", Payment.Status.PENDING),
            ("APP-3", "Undergraduate / Diploma Student Research fee", "800.00", Payment.Status.SUCCESS),
        ):
            Payment.objects.create(applicant=applicant, purpose=purpose, review_type="", reference=ref,
                                   amount=Decimal(amount), status=status)

        now = timezone.now()
        self.ai = Workshop.objects.create(title="AI Ethics Workshop", starts_at=now + timezone.timedelta(days=5))
        self.thesis = Workshop.objects.create(title="Thesis to Journal", starts_at=now + timezone.timedelta(days=30))

        def reg(ws, name, status, amount="35.00", wants=True, currency="GHS"):
            return WorkshopRegistration.objects.create(
                workshop=ws, name=name, institution="UG", email=f"{name.split()[0].lower()}@example.com",
                wants_certificate=wants, payment_status=status, amount=Decimal(amount), currency=currency,
                payment_reference=f"WS-{name.split()[0]}")
        reg(self.ai, "Kofi Paid", PS.SUCCESS)
        reg(self.ai, "Esi Paid", PS.SUCCESS)
        reg(self.ai, "Ama Owes", PS.PENDING)
        reg(self.ai, "Free Person", PS.NOT_REQUIRED, amount="0.00")           # not income
        reg(self.ai, "No Cert", PS.NOT_REQUIRED, amount="0.00", wants=False)  # not income
        reg(self.thesis, "Yaa Paid", PS.SUCCESS, amount="50.00")

    # ---- the grouped summary ----
    def test_breakdown_by_stream_and_group(self):
        s = ledger.breakdown()
        self.assertEqual(s.applications.collected, [("GHS", Decimal("1300.00"))])
        self.assertEqual(s.applications.outstanding, [("GHS", Decimal("500.00"))])
        self.assertEqual({g.fee_key: (g.paid, g.pending) for g in s.application_groups},
                         {"phd": (1, 1), "ug_diploma": (1, 0)})
        self.assertIn("PhD / Doctoral Student Research", [g.label for g in s.application_groups])
        self.assertEqual(s.workshops.collected, [("GHS", Decimal("120.00"))])
        by_ws = {g.label: (g.paid, g.pending, g.collected) for g in s.workshop_groups}
        self.assertEqual(by_ws["AI Ethics Workshop"], (2, 1, [("GHS", Decimal("70.00"))]))
        self.assertEqual(by_ws["Thesis to Journal"], (1, 0, [("GHS", Decimal("50.00"))]))
        self.assertEqual(s.total.collected, [("GHS", Decimal("1420.00"))])
        # Most recent workshop first.
        self.assertEqual([g.label for g in s.workshop_groups], ["Thesis to Journal", "AI Ethics Workshop"])

    def test_page_shows_the_breakdown(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "Income by Source")
        self.assertContains(resp, "Ethics applications")
        self.assertContains(resp, "AI Ethics Workshop")
        self.assertContains(resp, "Thesis to Journal")
        self.assertContains(resp, "GHS 1,420.00")
        self.assertContains(resp, f'href="?source=workshops&amp;group={self.ai.pk}#ledger"')

    # ---- the list: one stream at a time ----
    def test_list_defaults_to_ethics_applications_only(self):
        resp = self.client.get(self.url)
        self.assertEqual({r.reference for r in resp.context["page"]}, {"APP-1", "APP-2", "APP-3"})

    def test_workshop_list_is_grouped_by_workshop(self):
        resp = self.client.get(self.url, {"source": "workshops"})
        refs = [r.reference for r in resp.context["page"]]
        self.assertEqual(set(refs), {"WS-Kofi", "WS-Esi", "WS-Ama", "WS-Yaa"})
        # Each workshop's payments sit together, under a header with its subtotal.
        self.assertEqual(refs[0], "WS-Yaa")
        self.assertContains(resp, 'class="fin-group-row"', count=2)
        self.assertContains(resp, "collected <b>GHS 70.00</b>")

    def test_one_workshop(self):
        resp = self.client.get(self.url, {"source": "workshops", "group": str(self.ai.pk), "tab": "success"})
        self.assertEqual({r.reference for r in resp.context["page"]}, {"WS-Kofi", "WS-Esi"})
        self.assertEqual(resp.context["group_label"], "AI Ethics Workshop")

    def test_one_fee_category(self):
        resp = self.client.get(self.url, {"source": "applications", "group": "phd"})
        self.assertEqual({r.reference for r in resp.context["page"]}, {"APP-1", "APP-2"})

    def test_other_currencies_are_never_added_into_the_cedi_total(self):
        WorkshopRegistration.objects.create(
            workshop=self.thesis, name="Dollar Payer", institution="X", email="d@example.com", wants_certificate=True,
            payment_status=PS.SUCCESS, amount=Decimal("10.00"), currency="USD", payment_reference="WS-USD")
        s = ledger.breakdown()
        self.assertEqual(s.total.collected, [("GHS", Decimal("1420.00")), ("USD", Decimal("10.00"))])

    def test_workshop_csv_has_the_workshop_column(self):
        resp = self.client.get(self.url, {"source": "workshops", "tab": "success", "export": "csv"})
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8").lstrip("﻿"))))
        self.assertEqual(rows[0][:3], ["Workshop", "Reference", "Participant"])
        self.assertEqual(sorted((r[0], r[1]) for r in rows[1:]), [
            ("AI Ethics Workshop", "WS-Esi"), ("AI Ethics Workshop", "WS-Kofi"), ("Thesis to Journal", "WS-Yaa")])
        self.assertIn("msrec-workshop-payments-", resp["Content-Disposition"])

    def test_application_csv_has_the_review_type_column(self):
        resp = self.client.get(self.url, {"source": "applications", "export": "csv"})
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8").lstrip("﻿"))))
        self.assertEqual(rows[0][0], "Fee Category")
        self.assertIn(["PhD / Doctoral Student Research", "APP-1"], [r[:2] for r in rows])
        self.assertEqual(len(rows), 4)

    def test_reports_page_counts_workshop_fees(self):
        resp = self.client.get(reverse("admin_dashboard:reports_analytics"))
        self.assertEqual(resp.context["total_collected"], Decimal("1420.00"))
        self.assertContains(resp, "incl. 120.00 workshop fees")
