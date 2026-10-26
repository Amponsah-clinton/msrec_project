"""The staff Workshops list (/admins/workshop/): one card per workshop with
its status, date, registration and fee numbers."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from workshop.models import Workshop, WorkshopRegistration
from workshop.tests_compulsory_certificate import PinnedRateMixin, _workshop

PS = WorkshopRegistration.PaymentStatus


class WorkshopListTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )
        self.client.force_login(admin)
        self.url = reverse("workshop_admin:list")

    def test_cards_show_state_and_numbers(self):
        now = timezone.now()
        soon = _workshop(title="Soon Workshop", starts_at=now + timezone.timedelta(days=5))
        _workshop(title="Old Workshop", starts_at=now - timezone.timedelta(days=30))
        _workshop(title="Hidden Draft", is_published=False)
        Workshop.objects.create(title="Undated Workshop")
        # Three different fee-payers (one active registration per address
        # per workshop), two of them paid -> the 67% and GHS 300.00 below.
        for i, status in enumerate((PS.SUCCESS, PS.SUCCESS, PS.PENDING), start=1):
            WorkshopRegistration.objects.create(
                workshop=soon, name=f"P{i}", institution="UG", email=f"p{i}@example.com",
                wants_certificate=True, payment_status=status, amount=Decimal("150.00"),
            )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Registration open")
        self.assertContains(resp, "Completed")
        self.assertContains(resp, "Draft — not public")
        self.assertContains(resp, "No date yet")
        self.assertContains(resp, "67%")  # 2 of 3 fee-payers have paid
        self.assertContains(resp, "GHS 300.00")

        cards = resp.context["workshops"]
        soon_card = next(w for w in cards if w.pk == soon.pk)
        self.assertEqual((soon_card.reg_count, soon_card.paid_count, soon_card.owed_count), (3, 2, 1))
        # Upcoming before past.
        titles = [w.title for w in cards]
        self.assertLess(titles.index("Soon Workshop"), titles.index("Old Workshop"))
        self.assertEqual(resp.context["totals"]["owed"], 1)

    def test_empty_list(self):
        Workshop.objects.all().delete()  # migration 0004 seeds a default one
        resp = self.client.get(self.url)
        self.assertContains(resp, "No workshops yet")
