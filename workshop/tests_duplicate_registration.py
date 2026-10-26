"""One registration per person per workshop -- and no interference with
registering for a different workshop.

The rules under test (workshop/dedupe.py, the register view, and the
unique_active_email_per_workshop constraint):

  * same email, same workshop  -> denied
  * same name, same workshop   -> denied
  * same person, OTHER workshop -> allowed
  * an email clash with an unpaid fee -> offered that registration's
    checkout, because being turned away with nowhere to go is what made
    people register three times in the first place
  * a NAME clash -> never offered a payment link, since a namesake is a
    different person
"""
import os
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from workshop import dedupe
from workshop.models import Workshop, WorkshopRegistration

PS = WorkshopRegistration.PaymentStatus


class PinnedRateMixin:
    """Keeps page renders offline; see tests_compulsory_certificate."""

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
        "name": "Ama Mensah",
        "institution": "University Of Ghana",
        "email": "ama@example.com",
        "phone": "0241234567",
        "comments": "",
        "wants_certificate": "no",
    }
    data.update(overrides)
    return data


class NormalisationTests(TestCase):
    def test_names_differing_only_in_case_or_spacing_are_one_person(self):
        for variant in ("Ama Mensah", "ama mensah", "  AMA   MENSAH  ", "aMa\tMensah"):
            with self.subTest(variant=variant):
                self.assertEqual(dedupe.normalize_name(variant), "ama mensah")

    def test_different_names_stay_different(self):
        self.assertNotEqual(dedupe.normalize_name("Ama Mensah"), dedupe.normalize_name("Ama Mensa"))

    def test_emails_are_cased_and_trimmed(self):
        self.assertEqual(dedupe.normalize_email("  AMA@Example.COM "), "ama@example.com")

    def test_blank_input_matches_nothing(self):
        self.assertEqual(dedupe.normalize_name("   "), "")
        self.assertEqual(dedupe.normalize_email(None), "")


class DenyDuplicateTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        self.url = reverse("workshop:register", args=[self.ws.slug])

    def _register(self, **overrides):
        return self.client.post(self.url, _form(**overrides))

    def test_the_first_registration_is_accepted(self):
        self._register()
        self.assertEqual(WorkshopRegistration.objects.count(), 1)

    def test_the_same_email_is_denied(self):
        self._register()
        resp = self._register(name="Someone Else Entirely")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 1)
        self.assertContains(resp, "already registered for this workshop", status_code=409)

    def test_the_same_email_in_a_different_case_is_denied(self):
        self._register()
        resp = self._register(email="  AMA@Example.COM  ", name="Other Person")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 1)

    def test_the_same_name_is_denied_even_with_another_email(self):
        self._register()
        resp = self._register(email="different@example.com")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 1)
        self.assertContains(resp, "That name is already registered", status_code=409)

    def test_the_same_name_spelled_with_odd_spacing_is_denied(self):
        self._register()
        resp = self._register(name="  ama   MENSAH ", email="another@example.com")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 1)

    def test_a_different_person_is_still_accepted(self):
        self._register()
        resp = self._register(name="Kojo Boateng", email="kojo@example.com")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WorkshopRegistration.objects.count(), 2)

    def test_the_denial_does_not_touch_the_existing_row(self):
        self._register()
        before = WorkshopRegistration.objects.get()
        self._register(institution="Somewhere Else", phone="0550000000")
        after = WorkshopRegistration.objects.get()
        self.assertEqual(after.institution, before.institution)
        self.assertEqual(after.phone, before.phone)
        self.assertEqual(after.updated_at, before.updated_at)


class OtherWorkshopsStayOpenTests(PinnedRateMixin, TestCase):
    """The rule is per workshop and must not leak across them."""

    def setUp(self):
        super().setUp()
        self.first = _workshop(title="Workshop One")
        self.second = _workshop(title="Workshop Two")

    def test_the_same_person_may_register_for_another_workshop(self):
        self.client.post(reverse("workshop:register", args=[self.first.slug]), _form())
        resp = self.client.post(reverse("workshop:register", args=[self.second.slug]), _form())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WorkshopRegistration.objects.count(), 2)
        self.assertEqual(
            sorted(r.workshop_id for r in WorkshopRegistration.objects.all()),
            sorted([self.first.pk, self.second.pk]),
        )

    def test_but_still_only_once_on_each(self):
        for ws in (self.first, self.second):
            url = reverse("workshop:register", args=[ws.slug])
            self.assertEqual(self.client.post(url, _form()).status_code, 302)
            self.assertEqual(self.client.post(url, _form()).status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 2)

    def test_the_database_constraint_is_also_per_workshop(self):
        WorkshopRegistration.objects.create(
            workshop=self.first, name="Ama", institution="UG",
            email="ama@example.com", phone="0241234567",
        )
        # Same email on the other workshop: fine.
        WorkshopRegistration.objects.create(
            workshop=self.second, name="Ama", institution="UG",
            email="ama@example.com", phone="0241234567",
        )
        # Same email on the same workshop: refused by the database.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkshopRegistration.objects.create(
                    workshop=self.first, name="Ama", institution="UG",
                    email="AMA@example.com", phone="0241234567",
                )


class OutstandingFeeTests(PinnedRateMixin, TestCase):
    """The case that caused the duplicates: an unpaid registration with no
    way back to it."""

    def setUp(self):
        super().setUp()
        self.ws = _workshop(certificate_required=True)
        self.url = reverse("workshop:register", args=[self.ws.slug])

    def test_an_email_clash_is_offered_the_existing_checkout(self):
        self.client.post(self.url, _form())
        reg = WorkshopRegistration.objects.get()
        self.assertTrue(reg.payment_outstanding)

        resp = self.client.post(self.url, _form())
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 1)
        # Their own registration's checkout, not a new one.
        self.assertContains(resp, reverse("workshop:pay", args=[reg.pk]), status_code=409)
        self.assertContains(resp, "Pay GHS 35.00 now", status_code=409)

    def test_a_name_clash_is_never_given_someone_elses_payment_link(self):
        self.client.post(self.url, _form())
        reg = WorkshopRegistration.objects.get()

        resp = self.client.post(self.url, _form(email="namesake@example.com"))
        self.assertEqual(resp.status_code, 409)
        self.assertNotContains(resp, reverse("workshop:pay", args=[reg.pk]), status_code=409)
        self.assertNotContains(resp, "Pay GHS", status_code=409)
        self.assertContains(resp, "contact the Secretariat", status_code=409)

    def test_a_settled_registration_is_told_there_is_nothing_to_do(self):
        self.client.post(self.url, _form())
        reg = WorkshopRegistration.objects.get()
        reg.payment_status = PS.SUCCESS
        reg.paid_at = timezone.now()
        reg.save()

        resp = self.client.post(self.url, _form())
        self.assertEqual(resp.status_code, 409)
        self.assertNotContains(resp, "Pay GHS", status_code=409)
        self.assertContains(resp, "fee is paid", status_code=409)


class RaceTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        self.url = reverse("workshop:register", args=[self.ws.slug])

    def test_a_race_past_the_check_is_caught_by_the_database(self):
        """Two submissions can both pass find_existing(); the constraint is
        what actually guarantees one registration, and the loser is shown
        the row that won rather than a 500."""
        real = dedupe.find_existing

        def blind_first_call(*args, **kwargs):
            # Pretend the row wasn't there -- exactly what the losing
            # request of a double-submit sees.
            blind_first_call.calls += 1
            if blind_first_call.calls == 1:
                return None, None
            return real(*args, **kwargs)
        blind_first_call.calls = 0

        WorkshopRegistration.objects.create(
            workshop=self.ws, name="Ama Mensah", institution="UG",
            email="ama@example.com", phone="0241234567",
        )
        with mock.patch("workshop.views.dedupe.find_existing", side_effect=blind_first_call):
            resp = self.client.post(self.url, _form())

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(WorkshopRegistration.objects.count(), 1)


class DuplicateFlagTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        self.url = reverse("workshop:register", args=[self.ws.slug])

    def test_a_flagged_row_frees_that_person_to_register_again(self):
        self.client.post(self.url, _form())
        first = WorkshopRegistration.objects.get()
        first.is_duplicate = True
        first.save(update_fields=["is_duplicate"])

        resp = self.client.post(self.url, _form())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WorkshopRegistration.objects.count(), 2)
        # The flagged row is kept, not overwritten.
        first.refresh_from_db()
        self.assertTrue(first.is_duplicate)

    def test_find_existing_ignores_flagged_rows(self):
        reg = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Ama Mensah", institution="UG",
            email="ama@example.com", phone="0241234567", is_duplicate=True,
        )
        clash, matched = dedupe.find_existing(self.ws, email=reg.email, name=reg.name)
        self.assertIsNone(clash)
        self.assertIsNone(matched)

    def test_the_constraint_only_applies_to_unflagged_rows(self):
        WorkshopRegistration.objects.create(
            workshop=self.ws, name="Ama", institution="UG",
            email="ama@example.com", phone="0241234567",
        )
        # A flagged repeat on the same email is allowed to exist -- that is
        # how the live duplicates are kept instead of deleted.
        WorkshopRegistration.objects.create(
            workshop=self.ws, name="Ama", institution="UG",
            email="ama@example.com", phone="0241234567", is_duplicate=True,
        )
        self.assertEqual(WorkshopRegistration.objects.count(), 2)


class AdminDuplicateTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ws = _workshop()
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin",
        )
        self.client.force_login(self.admin)
        self.manage = reverse("workshop_admin:manage", args=[self.ws.pk])

        self.keeper = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Ama Mensah", institution="UG",
            email="ama@example.com", phone="0241234567",
        )
        self.repeat = WorkshopRegistration.objects.create(
            workshop=self.ws, name="Ama Mensah", institution="UG",
            email="ama@example.com", phone="0241234567", is_duplicate=True,
        )

    def test_counts_exclude_repeats(self):
        counts = self.client.get(self.manage).context["counts"]
        self.assertEqual(counts["all"], 1)
        self.assertEqual(counts["duplicates"], 1)

    def test_a_bulk_send_reaches_each_person_once(self):
        self.ws.meeting_link = "https://zoom.us/j/123"
        self.ws.save()
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(self.manage, {
                "action": "send_meeting_link", "tab": "registrations", "scope": "all",
            })
        self.assertEqual(send.call_count, 1)

    def test_an_admin_can_flag_and_restore(self):
        self.client.post(self.manage, {
            "action": "mark_duplicate", "tab": "registrations", "reg_id": self.keeper.pk,
        })
        self.keeper.refresh_from_db()
        self.assertTrue(self.keeper.is_duplicate)

        self.client.post(self.manage, {
            "action": "unmark_duplicate", "tab": "registrations", "reg_id": self.keeper.pk,
        })
        self.keeper.refresh_from_db()
        self.assertFalse(self.keeper.is_duplicate)

    def test_restoring_a_second_row_on_one_email_is_refused_not_crashed(self):
        resp = self.client.post(self.manage, {
            "action": "unmark_duplicate", "tab": "registrations", "reg_id": self.repeat.pk,
        })
        self.assertEqual(resp.status_code, 302)
        self.repeat.refresh_from_db()
        self.assertTrue(self.repeat.is_duplicate)

    def test_a_single_named_row_can_still_be_actioned_even_if_flagged(self):
        """Picking one person by hand is an explicit decision, so the
        duplicate filter must not silently swallow it."""
        self.ws.meeting_link = "https://zoom.us/j/123"
        self.ws.save()
        with mock.patch("workshop.emails.send_branded_email", return_value=True) as send:
            self.client.post(self.manage, {
                "action": "send_meeting_link", "tab": "registrations", "reg_id": self.repeat.pk,
            })
        self.assertEqual(send.call_count, 1)
