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
            ("Yaw Twin", "yaw@example.com", "0241111111", PS.NOT_REQUIRED),  # shares Kofi's number
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

    def test_full_csv_export(self):
        resp = self.client.get(reverse("workshop_admin:contacts_export"), {"kind": "full", "sort": "name"})
        text = resp.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        lines = text.lstrip("﻿").splitlines()
        self.assertTrue(lines[0].startswith("Name,Email,Phone,SMS Number,Institution"))
        self.assertEqual(len(lines), 5)
        self.assertIn("Ama Owes,ama@example.com,+233 24 222 2222,0242222222,UG,1,Ethics 101,No", text)
        self.assertIn("msrec-workshop-contacts-", resp["Content-Disposition"])

    def test_sms_export_is_clean_unique_ghana_numbers(self):
        resp = self.client.get(reverse("workshop_admin:contacts_export"), {"kind": "sms"})
        lines = resp.content.decode("utf-8").lstrip("﻿").splitlines()
        self.assertEqual(lines[0], "Phone,Name,First Name")
        phones = sorted(line.split(",")[0] for line in lines[1:])
        self.assertEqual(phones, ["0241111111", "0242222222"])  # no UK number, no duplicate

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
        self.assertEqual(sorted(send_sms.call_args.args[0]), ["0241111111", "0242222222"])
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
