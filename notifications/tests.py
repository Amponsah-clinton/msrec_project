"""The notifications list page: full history, per-user delete, filters."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from applicant_dashboard.models import Application

from . import services
from .models import Notification, NotificationDismissal, NotificationRead

A = Notification.Audience


class NotificationPageTests(TestCase):
    def setUp(self):
        U = get_user_model()
        mk = lambda email, role, **kw: U.objects.create_user(
            email=email, password="pw12345678!", first_name=role.title(), last_name="T", role=role, **kw)
        self.admin = mk("adm@x.org", "admin", is_staff=True, is_superuser=True)
        self.admin2 = mk("adm2@x.org", "admin", is_staff=True, is_superuser=True)
        self.sec = mk("sec@x.org", "secretariat", is_staff=True)
        self.applicant = mk("app@x.org", "applicant")
        self.url = reverse("notifications:list", args=["admin"])
        self.bulk = reverse("notifications:bulk", args=["admin"])

    def note(self, audience=A.ADMIN, message="Something happened", **kw):
        return Notification.objects.create(audience=audience, message=message, **kw)

    def texts(self, response):
        return [n.message for _label, items in response.context["groups"] for n in items]

    # ---- what the admin inbox contains ----
    def test_admin_inbox_has_admin_and_secretariat_but_not_other_roles(self):
        self.note(A.ADMIN, "for admin")
        self.note(A.SECRETARIAT, "for secretariat")
        self.note(A.COMMITTEE, "for committee")
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(self.texts(response)), ["for admin", "for secretariat"])
        self.assertEqual(response.context["counts"], {"all": 2, "unread": 2, "read": 0})

    def test_secretariat_inbox_stays_its_own(self):
        self.note(A.ADMIN, "for admin")
        self.note(A.SECRETARIAT, "for secretariat")
        self.client.force_login(self.sec)
        response = self.client.get(reverse("notifications:list", args=["secretariat"]))
        self.assertEqual(self.texts(response), ["for secretariat"])

    def test_old_notifications_are_kept_and_paginated_not_capped(self):
        for i in range(130):
            self.note(message=f"n{i}")
        self.client.force_login(self.admin)
        first = self.client.get(self.url)
        self.assertEqual(first.context["counts"]["all"], 130)  # more than the old 100 cap
        self.assertEqual(len(self.texts(first)), 25)
        self.assertEqual(self.texts(first)[0], "n129")  # newest first
        last = self.client.get(self.url + "?page=6")
        self.assertEqual(len(self.texts(last)), 5)
        self.assertIn("n0", self.texts(last))
        self.assertEqual(self.client.get(self.url + "?page=999").status_code, 200)  # clamped, not an error
        self.assertEqual(self.client.get(self.url + "?page=abc").status_code, 200)

    # ---- reading and filtering ----
    def test_filters_and_search(self):
        a, b, c = self.note(message="alpha app"), self.note(message="beta"), self.note(message="alpha two")
        NotificationRead.objects.create(notification=a, user=self.admin)
        self.client.force_login(self.admin)
        self.assertEqual(sorted(self.texts(self.client.get(self.url + "?filter=unread"))), ["alpha two", "beta"])
        self.assertEqual(self.texts(self.client.get(self.url + "?filter=read")), ["alpha app"])
        self.assertEqual(sorted(self.texts(self.client.get(self.url + "?q=alpha"))), ["alpha app", "alpha two"])
        self.assertEqual(self.texts(self.client.get(self.url + "?filter=unread&q=alpha")), ["alpha two"])
        self.assertEqual(self.client.get(self.url + "?filter=bogus").context["state"], "all")
        empty = self.client.get(self.url + "?q=zzzz")
        self.assertContains(empty, "No notifications match")

    def test_read_state_is_per_user(self):
        n = self.note()
        NotificationRead.objects.create(notification=n, user=self.admin)
        self.assertEqual(services.unread_count(self.admin, "admin"), 0)
        self.assertEqual(services.unread_count(self.admin2, "admin"), 1)

    # ---- deleting is per user ----
    def test_delete_is_per_user_and_keeps_the_shared_row(self):
        keep, gone = self.note(message="keep"), self.note(message="gone")
        self.client.force_login(self.admin)
        self.client.post(self.bulk, {"action": "delete_selected", "ids": [gone.pk]})
        self.assertTrue(Notification.objects.filter(pk=gone.pk).exists())
        self.assertEqual(self.texts(self.client.get(self.url)), ["keep"])
        self.assertEqual(services.unread_count(self.admin, "admin"), 1)
        feed = self.client.get(reverse("notifications:feed", args=["admin"])).json()
        self.assertEqual([i["message"] for i in feed["items"]], ["keep"])
        # the other admin still has both
        self.client.force_login(self.admin2)
        self.assertEqual(sorted(self.texts(self.client.get(self.url))), ["gone", "keep"])
        self.assertEqual(keep.dismissals.count(), 0)

    def test_bulk_actions(self):
        ns = [self.note(message=f"m{i}") for i in range(5)]
        self.client.force_login(self.admin)
        self.client.post(self.bulk, {"action": "mark_read", "ids": [ns[0].pk, ns[1].pk]})
        self.assertEqual(services.unread_count(self.admin, "admin"), 3)
        self.client.post(self.bulk, {"action": "mark_unread", "ids": [ns[0].pk]})
        self.assertEqual(services.unread_count(self.admin, "admin"), 4)
        self.client.post(reverse("notifications:mark_all_read", args=["admin"]), {})
        self.assertEqual(services.unread_count(self.admin, "admin"), 0)
        self.client.post(self.bulk, {"action": "mark_unread", "ids": [ns[2].pk]})
        self.client.post(self.bulk, {"action": "delete_read"})  # deletes the 4 read, keeps the unread one
        self.assertEqual(self.texts(self.client.get(self.url)), ["m2"])
        self.client.post(self.bulk, {"action": "delete_all"})
        self.assertEqual(self.texts(self.client.get(self.url)), [])
        self.assertContains(self.client.get(self.url), "No notifications")
        self.assertEqual(Notification.objects.count(), 5)  # nothing was really deleted

    def test_bulk_ignores_ids_outside_the_inbox_and_is_idempotent(self):
        other = self.note(A.COMMITTEE, "committee only")
        mine = self.note(message="mine")
        self.client.force_login(self.admin)
        self.client.post(self.bulk, {"action": "delete_selected", "ids": [other.pk, "abc", mine.pk]})
        self.client.post(self.bulk, {"action": "delete_selected", "ids": [mine.pk]})  # again: no error
        self.assertFalse(NotificationDismissal.objects.filter(notification=other).exists())
        self.assertEqual(NotificationDismissal.objects.filter(notification=mine).count(), 1)
        self.assertEqual(self.client.post(self.bulk, {"action": "delete_selected"}).status_code, 302)  # nothing selected
        self.assertEqual(self.client.post(self.bulk, {"action": "explode"}).status_code, 302)

    # ---- access ----
    def test_access_control(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.bulk, {"action": "delete_all"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("notifications:list", args=["nonsense"])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)  # to login
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.bulk).status_code, 405)  # POST only

    # ---- links ----
    def test_open_marks_read_and_follows_links_including_dead_ones(self):
        app = Application.objects.create(applicant=self.applicant, status="submitted", form_data={"studyTitle": "S"})
        linked = self.note(A.SECRETARIAT, "new application", link_url_name="secretariat_dashboard:application_detail", link_kwargs={"pk": app.pk})
        dead = self.note(message="old", link_url_name="route_that_was_removed")
        plain = self.note(message="plain")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("notifications:open", args=["admin", linked.pk]))
        self.assertRedirects(r, reverse("admin_dashboard:application_detail", args=[app.pk]), fetch_redirect_response=False)
        self.assertTrue(NotificationRead.objects.filter(notification=linked, user=self.admin).exists())
        for n in (dead, plain):
            r = self.client.get(reverse("notifications:open", args=["admin", n.pk]))
            self.assertRedirects(r, self.url, fetch_redirect_response=False)  # no 500
            self.assertTrue(NotificationRead.objects.filter(notification=n, user=self.admin).exists())
        panel = self.client.get(self.url).content.decode().split('id="npRoot"', 1)[1]  # the list, not the topbar bell
        self.assertIn(reverse("notifications:open", args=["admin", linked.pk]), panel)
        self.assertNotIn(reverse("notifications:open", args=["admin", dead.pk]), panel)  # dead link isn't clickable
        gone = self.note(message="deleted")
        services.dismiss_many(self.admin, "admin", [gone.pk])
        r = self.client.get(reverse("notifications:open", args=["admin", gone.pk]))
        self.assertRedirects(r, self.url, fetch_redirect_response=False)

    def test_next_redirect_cannot_leave_the_site(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("notifications:mark_all_read", args=["admin"]), {"next": "https://evil.example/x"})
        self.assertEqual(r["Location"], "/")
        r = self.client.post(self.bulk, {"action": "delete_all", "next": "//evil.example"})
        self.assertEqual(r["Location"], self.url)
        r = self.client.post(self.bulk, {"action": "delete_all", "next": self.url + "?filter=read"})
        self.assertEqual(r["Location"], self.url + "?filter=read")

    def test_page_renders_for_other_audiences_and_shows_source_badges(self):
        self.note(A.ADMIN, "a")
        self.note(A.SECRETARIAT, "s")
        self.client.force_login(self.admin)
        html = self.client.get(self.url).content.decode()
        self.assertIn("text-bg-dark", html)
        self.assertIn("text-bg-info", html)
        self.assertIn("np-selectall", html)
        for audience in ("committee", "chair", "reviewer", "secretariat"):
            self.assertEqual(self.client.get(reverse("notifications:list", args=[audience])).status_code, 200, audience)
