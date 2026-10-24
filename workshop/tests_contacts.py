"""The workshop contact list (/admins/workshop/contacts/): everyone who has
ever registered, saved the moment they register, kept when a workshop is
deleted, messageable and exportable."""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from workshop.models import WorkshopContact, WorkshopRegistration
from workshop.tests_compulsory_certificate import PinnedRateMixin, _form, _workshop

PS = WorkshopRegistration.PaymentStatus
SMS_OK = {"ok": True, "sent_to": [], "error": None}


class ContactSyncTests(PinnedRateMixin, TestCase):
    def test_registering_saves_the_person_immediately(self):
        ws = _workshop()
        with mock.patch("workshop.emails.send_branded_email", return_value=True):
            self.client.post(reverse("workshop:register", args=[ws.slug]), _form(wants_certificate="no"))
        c = WorkshopContact.objects.get(email="ama@example.com")
        self.assertEqual((c.name, c.phone, c.registration_count, c.has_paid), ("Ama Mensah", "0241234567", 1, False))
        self.assertEqual(c.workshop_titles, [ws.title])

    def test_same_person_across_workshops_is_one_contact(self):
        first, second = _workshop(title="First"), _workshop(title="Second")
        WorkshopRegistration.objects.create(workshop=first, name="Ama M", institution="UG", email="Ama@Example.com")
        WorkshopRegistration.objects.create(workshop=second, name="Ama Mensah", institution="KNUST",
                                            email="ama@example.com", phone="0241234567")
        c = WorkshopContact.objects.get()
        self.assertEqual(c.registration_count, 2)
        self.assertEqual((c.name, c.institution), ("Ama Mensah", "KNUST"))  # newest details win
        self.assertEqual(sorted(c.workshop_titles), ["First", "Second"])

    def test_paying_marks_the_contact_and_workshop_deletion_keeps_them(self):
        ws = _workshop()
        reg = WorkshopRegistration.objects.create(
            workshop=ws, name="Kofi", institution="UG", email="kofi@example.com",
            wants_certificate=True, payment_status=PS.PENDING, amount=Decimal("150.00"))
        reg.payment_status = PS.SUCCESS
        reg.save(update_fields=["payment_status"])
        self.assertTrue(WorkshopContact.objects.get().has_paid)

        ws.delete()
        c = WorkshopContact.objects.get()
        self.assertEqual(c.workshop_titles, [ws.title])
        self.assertTrue(c.has_paid)


class DuplicateTests(PinnedRateMixin, TestCase):
    """One person, one row -- however they registered."""

    def setUp(self):
        super().setUp()
        self.ws = _workshop(title="AI Ethics")

    def _reg(self, name, email, phone="", ws=None, **kw):
        return WorkshopRegistration.objects.create(
            workshop=ws or self.ws, name=name, institution="UG", email=email, phone=phone, **kw)

    def test_registering_twice_for_one_workshop_counts_once(self):
        # The public form now refuses the second and third attempt, but rows
        # like these are still in the table from before the rule, kept as
        # flagged duplicates rather than deleted. The contact layer counts
        # distinct workshops, so all three are still one registration.
        self._reg("Emmanuel Kofi Obah", "obah@example.com", "0545254190")
        for _ in range(2):
            self._reg("Emmanuel Kofi Obah", "obah@example.com", "0545254190",
                      is_duplicate=True)
        c = WorkshopContact.objects.get()
        self.assertEqual(c.registration_count, 1)
        self.assertEqual(c.workshop_titles, ["AI Ethics"])

    def test_same_name_in_another_order_is_the_same_person(self):
        self._reg("Atianashie Miracle", "miracle81@gmail.com", "+233593464021")
        self._reg("Miracle Atianashie", "miracle@cug.edu.gh", "0598299648")
        c = WorkshopContact.objects.get()
        self.assertEqual(c.email, "miracle@cug.edu.gh")  # newest details lead
        self.assertEqual(c.other_emails, ["miracle81@gmail.com"])
        self.assertEqual(c.other_phones, ["+233593464021"])

    def test_same_phone_in_any_format_is_the_same_person(self):
        self._reg("Ama Mensah", "ama@one.com", "0241234567")
        self._reg("A. Mensah", "ama@two.com", "+233 24 123 4567")
        self.assertEqual(WorkshopContact.objects.count(), 1)

    def test_honorifics_dont_split_a_person(self):
        self._reg("Patrick Twumasi", "pt@one.com")
        self._reg("Dr. Patrick Twumasi", "pt@two.com")
        self.assertEqual(WorkshopContact.objects.count(), 1)

    def test_a_registration_that_links_two_contacts_merges_them(self):
        self._reg("Kwame Asante", "kwame@one.com", "0201111111")
        self._reg("Yaa Owusu", "yaa@two.com", "0202222222")
        self.assertEqual(WorkshopContact.objects.count(), 2)
        other = _workshop(title="Thesis to Journal")
        # Kwame's email with Yaa's phone: these turn out to be one person.
        self._reg("Kwame Asante", "kwame@one.com", "0202222222", ws=other)
        c = WorkshopContact.objects.get()
        self.assertEqual(c.registration_count, 2)
        self.assertEqual(sorted(c.workshop_titles), ["AI Ethics", "Thesis to Journal"])

    def test_different_people_stay_apart(self):
        self._reg("Ama Mensah", "ama@one.com", "0241234567")
        self._reg("Kofi Mensah", "kofi@two.com", "0247654321")
        self._reg("Mohammed Mahmud", "mm@three.com", "+2348062622277")
        self._reg("Mohammed Yussif Mahmud", "myh@four.com", "0241800335")
        self.assertEqual(WorkshopContact.objects.count(), 4)


class ContactPageTests(PinnedRateMixin, TestCase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123", first_name="Ada", last_name="Admin")
        self.client.force_login(admin)
        self.url = reverse("workshop_admin:contacts")
        self.ws = _workshop(title="Ethics 101")
        for name, email, phone, status in (
            ("Kofi Paid", "kofi@example.com", "0241111111", PS.SUCCESS),
            ("Ama Owes", "ama@example.com", "+233 24 222 2222", PS.PENDING),
            ("Esi Abroad", "esi@example.com", "+44 7700 900123", PS.NOT_REQUIRED),
            ("Yaw Boateng", "yaw@example.com", "0553333333", PS.NOT_REQUIRED),
        ):
            WorkshopRegistration.objects.create(workshop=self.ws, name=name, institution="UG",
                                                email=email, phone=phone, payment_status=status)
        sms_cfg = mock.patch("notifications.sms.is_configured", return_value=True)
        sms_cfg.start()
        self.addCleanup(sms_cfg.stop)

    def test_page_lists_everyone_and_filters(self):
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context["people"]), 4)
        self.assertEqual(resp.context["stats"]["sms"], 3)
        resp = self.client.get(self.url, {"paid": "yes"})
        self.assertEqual([c.name for c in resp.context["people"]], ["Kofi Paid"])
        resp = self.client.get(self.url, {"phone": "no"})
        self.assertEqual([c.name for c in resp.context["people"]], ["Esi Abroad"])
        resp = self.client.get(self.url, {"q": "owes"})
        self.assertEqual([c.name for c in resp.context["people"]], ["Ama Owes"])

    def test_workshop_modal_data(self):
        kofi = WorkshopContact.objects.get(email="kofi@example.com")
        # A repeat row on the same workshop -- which is what this asserts:
        # the modal collapses it into one entry showing "times: 2". The
        # public form now refuses such a second attempt, so rows like this
        # exist only as flagged duplicates (the ones already in the live
        # table), and the modal must still account for them.
        WorkshopRegistration.objects.create(workshop=self.ws, name="Kofi Paid", institution="UG",
                                            email="kofi@example.com", phone="0241111111",
                                            is_duplicate=True)
        resp = self.client.get(self.url)
        self.assertContains(resp, 'id="wscModalData"')
        self.assertContains(resp, 'class="wsc-ws-btn"')
        d = resp.context["modal"][kofi.pk]
        self.assertEqual(d["registrations"], 2)
        self.assertEqual(len(d["workshops"]), 1)
        w = d["workshops"][0]
        self.assertEqual((w["title"], w["times"], w["paid"], w["past"]), ("Ethics 101", 2, True, False))
        self.assertEqual(w["url"], reverse("workshop_admin:manage", args=[self.ws.pk]))

    def test_full_csv_export(self):
        resp = self.client.get(reverse("workshop_admin:contacts_export"), {"kind": "full", "sort": "name"})
        text = resp.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        lines = text.lstrip("﻿").splitlines()
        self.assertTrue(lines[0].startswith("Name,Email,Phone,SMS Number,Institution"))
        self.assertEqual(len(lines), 5)
        self.assertIn("Ama Owes,ama@example.com,+233 24 222 2222,0242222222,UG,,,1,Ethics 101,No", text)
        self.assertIn("msrec-workshop-contacts-", resp["Content-Disposition"])

    def test_sms_export_is_clean_unique_ghana_numbers(self):
        resp = self.client.get(reverse("workshop_admin:contacts_export"), {"kind": "sms"})
        lines = resp.content.decode("utf-8").lstrip("﻿").splitlines()
        self.assertEqual(lines[0], "Phone,Name,First Name")
        phones = sorted(line.split(",")[0] for line in lines[1:])
        self.assertEqual(phones, ["0241111111", "0242222222", "0553333333"])  # no UK number

    def test_export_of_ticked_people_only(self):
        ama = WorkshopContact.objects.get(email="ama@example.com")
        resp = self.client.get(reverse("workshop_admin:contacts_export"), {"kind": "full", "ids": str(ama.pk)})
        lines = resp.content.decode("utf-8").lstrip("﻿").splitlines()
        self.assertEqual(len(lines), 2)

    def test_message_the_filtered_group_by_email_and_sms(self):
        with mock.patch("notifications.emails.send_branded_email", return_value=True) as send, \
                mock.patch("notifications.sms.send_sms", return_value=SMS_OK) as send_sms:
            resp = self.client.post(self.url, {
                "action": "send_message", "paid": "no", "send_email": "on", "send_sms": "on",
                "subject": "Hello {first_name}", "body": "Hi {name},\nNew workshop soon.",
                "sms_body": "MSREC: new workshop soon.",
            }, follow=True)
        self.assertEqual(sorted(c.kwargs["to"] for c in send.call_args_list),
                         ["ama@example.com", "esi@example.com", "yaw@example.com"])
        self.assertEqual(sorted(send_sms.call_args.args[0]), ["0242222222", "0553333333"])
        self.assertContains(resp, "1 without a valid Ghana number")
        self.assertIsNotNone(WorkshopContact.objects.get(email="ama@example.com").last_messaged_at)
        self.assertIsNone(WorkshopContact.objects.get(email="kofi@example.com").last_messaged_at)

    def test_message_one_person(self):
        esi = WorkshopContact.objects.get(email="esi@example.com")
        with mock.patch("notifications.emails.send_branded_email", return_value=True) as send:
            self.client.post(self.url, {"action": "send_message", "ids": str(esi.pk), "send_email": "on",
                                        "subject": "Hi", "body": "Hello {first_name}"})
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["paragraphs"], ["Hello Esi"])

    def test_remove_a_contact(self):
        esi = WorkshopContact.objects.get(email="esi@example.com")
        self.client.post(self.url, {"action": "delete_contact", "contact_id": esi.pk})
        self.assertFalse(WorkshopContact.objects.filter(pk=esi.pk).exists())
        self.assertTrue(WorkshopRegistration.objects.filter(email="esi@example.com").exists())
