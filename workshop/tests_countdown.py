"""The public workshop countdown: Workshop.countdown, and the countdown on
/workshop/ and on the homepage's Upcoming Workshop band."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workshop.models import Workshop
from workshop.tests_compulsory_certificate import PinnedRateMixin, _workshop


class CountdownStateTests(TestCase):
    def test_upcoming_splits_the_time_left(self):
        ws = Workshop(title="W", starts_at=timezone.now() + timezone.timedelta(days=3, hours=4, minutes=5, seconds=30))
        cd = ws.countdown
        self.assertEqual(cd["state"], "upcoming")
        self.assertEqual((cd["days"], cd["hours"], cd["minutes"]), (3, 4, 5))

    def test_live_while_running_and_over_after(self):
        now = timezone.now()
        live = Workshop(title="W", starts_at=now - timezone.timedelta(hours=1), ends_at=now + timezone.timedelta(hours=1))
        self.assertEqual(live.countdown["state"], "live")
        done = Workshop(title="W", starts_at=now - timezone.timedelta(hours=3), ends_at=now - timezone.timedelta(hours=1))
        self.assertEqual(done.countdown["state"], "over")
        self.assertEqual(Workshop(title="W").countdown["state"], "none")

    def test_deadline_flagged_only_when_it_comes_before_the_start(self):
        now = timezone.now()
        early = Workshop(title="W", starts_at=now + timezone.timedelta(days=5),
                         registration_closes_at=now + timezone.timedelta(days=2))
        self.assertTrue(early.countdown["deadline_soon"])
        self.assertFalse(Workshop(title="W", starts_at=now + timezone.timedelta(days=5)).countdown["deadline_soon"])


class CountdownPageTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        Workshop.objects.all().delete()  # migration 0004 seeds one

    def test_workshops_page_has_a_countdown_on_each_card_only(self):
        now = timezone.now()
        _workshop(title="Soonest", starts_at=now + timezone.timedelta(days=2))
        _workshop(title="Later", starts_at=now + timezone.timedelta(days=20))
        resp = self.client.get(reverse("workshop:list"))
        self.assertNotContains(resp, "Next up")
        self.assertNotContains(resp, "wcd wcd--lg")
        self.assertContains(resp, "wcd wcd--line", count=2)
        self.assertContains(resp, "workshop-countdown.js")

    def test_no_countdown_without_a_date(self):
        _workshop(title="Undated", starts_at=None)
        resp = self.client.get(reverse("workshop:list"))
        self.assertNotContains(resp, "data-wcd")

    def test_homepage_band_has_the_countdown(self):
        _workshop(title="Homepage Workshop", starts_at=timezone.now() + timezone.timedelta(days=4))
        resp = self.client.get(reverse("pages:index"))
        self.assertContains(resp, "Homepage Workshop")
        self.assertContains(resp, "wcd wcd--lg")
        self.assertContains(resp, "workshop-countdown.js")
