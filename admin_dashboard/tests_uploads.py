"""The Upload page and the share link each upload gets."""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import SharedUpload

ADMIN = reverse("admin_dashboard:uploads")


def _file(name="report.pdf", content=b"%PDF-1.4 hello", ctype="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=ctype)


class UploadTestCase(TestCase):
    """Storage is stubbed: these tests are about this app, not Supabase."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin-123",
            first_name="Ada", last_name="Admin")
        self.client.force_login(self.admin)
        self.bucket = {}

        def fake_upload(path, data, ctype):
            self.bucket[path] = (data, ctype)
            return path

        def fake_download(path):
            return self.bucket.get(path, (None, None))

        def fake_delete(path):
            return self.bucket.pop(path, None) is not None

        patches = [
            mock.patch("admin_dashboard.uploads_storage.upload", side_effect=fake_upload),
            mock.patch("admin_dashboard.uploads_storage.download", side_effect=fake_download),
            mock.patch("admin_dashboard.uploads_storage.delete", side_effect=fake_delete),
            mock.patch("admin_dashboard.uploads_storage._configured", return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _upload(self, **over):
        data = {"action": "upload", "file": _file(), "title": "Ethics Guidelines 2026"}
        data.update(over)
        self.client.post(ADMIN, data)
        return SharedUpload.objects.order_by("-pk").first()


class UploadingTests(UploadTestCase):

    def test_a_file_is_stored_and_gets_its_own_link(self):
        row = self._upload()
        self.assertEqual(row.title, "Ethics Guidelines 2026")
        self.assertEqual(row.original_name, "report.pdf")
        self.assertEqual(row.content_type, "application/pdf")
        self.assertIn(row.object_path, self.bucket)
        self.assertGreaterEqual(len(row.token), 24)
        self.assertIn(row.token, row.share_url())

    def test_the_typed_name_is_what_the_file_downloads_as(self):
        row = self._upload(title="Ethics Guidelines 2026")
        self.assertEqual(row.download_name, "Ethics_Guidelines_2026.pdf")

    def test_without_a_typed_name_the_file_keeps_its_own(self):
        row = self._upload(title="   ")
        self.assertEqual(row.title, "report.pdf")

    def test_two_files_of_the_same_name_never_collide(self):
        a = self._upload(file=_file())
        b = self._upload(file=_file())
        self.assertNotEqual(a.object_path, b.object_path)
        self.assertNotEqual(a.token, b.token)
        self.assertEqual(len(self.bucket), 2)

    def test_the_stored_path_gives_nothing_away(self):
        row = self._upload(title="Board Minutes")
        self.assertNotIn("Board", row.object_path)
        self.assertNotIn("report", row.object_path)

    def test_a_file_over_the_limit_is_refused(self):
        # The limit is checked against what actually arrived, so the test
        # lowers the limit rather than lying about the file's size -- the
        # test client rebuilds the upload and recomputes it anyway.
        payload = SimpleUploadedFile("big.bin", b"x" * 64, content_type="application/octet-stream")
        with mock.patch("admin_dashboard.uploads_views.MAX_BYTES", 16):
            self.client.post(ADMIN, {"action": "upload", "file": payload, "title": "Big"})
        self.assertEqual(SharedUpload.objects.count(), 0)
        self.assertEqual(self.bucket, {})

    def test_a_storage_failure_leaves_no_half_made_record(self):
        with mock.patch("admin_dashboard.uploads_storage.upload", return_value=None):
            self.client.post(ADMIN, {"action": "upload", "file": _file(), "title": "Nope"})
        self.assertEqual(SharedUpload.objects.count(), 0)

    def test_the_page_needs_a_staff_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(ADMIN).status_code, 302)
        self.assertEqual(self.client.post(ADMIN, {"action": "upload", "file": _file()}).status_code, 302)
        self.assertEqual(SharedUpload.objects.count(), 0)


class ShareLinkTests(UploadTestCase):

    def test_anyone_with_the_link_can_open_and_download_it(self):
        row = self._upload()
        self.client.logout()
        page = self.client.get(row.share_url())
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Ethics Guidelines 2026")
        self.assertEqual(page["Cache-Control"], "no-store")

        got = self.client.get(row.file_url() + "?download=1")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.content, b"%PDF-1.4 hello")
        self.assertIn("attachment", got["Content-Disposition"])
        self.assertIn("Ethics_Guidelines_2026.pdf", got["Content-Disposition"])

    def test_a_guessed_link_finds_nothing(self):
        self._upload()
        self.client.logout()
        self.assertEqual(self.client.get("/u/not-a-real-token/").status_code, 404)
        self.assertEqual(self.client.get("/u/not-a-real-token/file/").status_code, 404)

    def test_views_and_downloads_are_counted(self):
        row = self._upload()
        self.client.logout()
        self.client.get(row.share_url())
        self.client.get(row.share_url())
        self.client.get(row.file_url() + "?download=1")
        row.refresh_from_db()
        self.assertEqual(row.view_count, 2)
        self.assertEqual(row.download_count, 1)
        self.assertIsNotNone(row.last_seen_at)

    def test_turning_a_link_off_stops_it_dead(self):
        row = self._upload()
        self.client.post(ADMIN, {"action": "toggle", "id": row.pk})
        self.client.logout()
        self.assertEqual(self.client.get(row.share_url()).status_code, 404)
        self.assertEqual(self.client.get(row.file_url()).status_code, 404)

    def test_a_new_link_retires_the_old_address(self):
        row = self._upload()
        was = row.share_url()
        self.client.post(ADMIN, {"action": "relink", "id": row.pk})
        row.refresh_from_db()
        self.assertNotEqual(row.share_url(), was)
        self.client.logout()
        self.assertEqual(self.client.get(was).status_code, 404)
        self.assertEqual(self.client.get(row.share_url()).status_code, 200)

    def test_deleting_takes_the_file_out_of_storage(self):
        row = self._upload()
        path, url = row.object_path, row.share_url()
        self.client.post(ADMIN, {"action": "delete", "id": row.pk})
        self.assertNotIn(path, self.bucket)
        self.assertEqual(SharedUpload.objects.count(), 0)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_renaming_changes_the_name_not_the_link(self):
        row = self._upload()
        url = row.share_url()
        self.client.post(ADMIN, {"action": "rename", "id": row.pk, "title": "Renamed Thing"})
        row.refresh_from_db()
        self.assertEqual(row.title, "Renamed Thing")
        self.assertEqual(row.share_url(), url)


class ServingSafetyTests(UploadTestCase):
    """A file comes back from our own domain, so what we serve inline
    decides whether an upload can run script against our users."""

    def test_html_is_never_served_inline(self):
        row = self._upload(file=_file("evil.html", b"<script>alert(1)</script>", "text/html"),
                           title="Evil")
        self.assertEqual(row.kind, "file")
        self.assertFalse(row.can_preview)
        self.client.logout()
        got = self.client.get(row.file_url())
        self.assertIn("attachment", got["Content-Disposition"])
        self.assertEqual(got["Content-Type"], "application/octet-stream")

    def test_svg_is_treated_as_a_script_container_not_an_image(self):
        row = self._upload(file=_file("x.svg", b"<svg onload='alert(1)'/>", "image/svg+xml"),
                           title="Logo")
        self.assertEqual(row.kind, "file")
        self.client.logout()
        self.assertIn("attachment", self.client.get(row.file_url())["Content-Disposition"])

    def test_every_file_response_is_sandboxed_and_never_sniffed(self):
        row = self._upload()
        self.client.logout()
        got = self.client.get(row.file_url())
        self.assertIn("sandbox", got["Content-Security-Policy"])
        self.assertEqual(got["X-Content-Type-Options"], "nosniff")
        self.assertIn("noindex", got["X-Robots-Tag"])

    def test_the_served_type_comes_from_the_record_not_the_fetch(self):
        # Storage reporting text/html for a file we recorded as a PDF must
        # not change what the browser is told.
        row = self._upload()
        self.bucket[row.object_path] = (b"%PDF-1.4 hello", "text/html")
        self.client.logout()
        self.assertEqual(self.client.get(row.file_url())["Content-Type"], "application/pdf")

    def test_the_kinds_a_browser_can_safely_show_are_shown(self):
        cases = {
            "image/png": "image", "image/jpeg": "image", "application/pdf": "pdf",
            "video/mp4": "video", "audio/mpeg": "audio", "text/plain": "text",
            "image/svg+xml": "file", "text/html": "file",
            "application/zip": "file", "application/octet-stream": "file",
        }
        for ctype, expected in cases.items():
            with self.subTest(ctype):
                self.assertEqual(SharedUpload(content_type=ctype).kind, expected)

    def test_a_pdf_is_shown_on_the_page(self):
        row = self._upload()
        self.client.logout()
        page = self.client.get(row.share_url())
        self.assertContains(page, row.file_url())
        self.assertContains(page, "<iframe")

    def test_an_unviewable_file_offers_a_download_instead(self):
        row = self._upload(file=_file("data.zip", b"PK\x03\x04", "application/zip"), title="Bundle")
        self.client.logout()
        page = self.client.get(row.share_url())
        self.assertContains(page, "can&rsquo;t be shown in a browser")
        self.assertContains(page, row.download_url())


class ShareLinkHostTests(UploadTestCase):
    """The link you copy has to work from where you copied it."""

    def test_the_link_follows_the_host_the_page_was_served_on(self):
        self._upload()
        page = self.client.get(ADMIN, HTTP_HOST="127.0.0.1:8000")
        link = page.context["uploads"][0].link
        self.assertTrue(link.startswith("http://127.0.0.1:8000/u/"), link)
        self.assertNotIn("ghethicalclearance", link)

    def test_a_link_built_in_production_carries_that_host(self):
        self._upload()
        page = self.client.get(ADMIN, HTTP_HOST="ghethicalclearance.academicdigital.space", secure=True)
        link = page.context["uploads"][0].link
        self.assertTrue(link.startswith("https://ghethicalclearance.academicdigital.space/u/"), link)

    def test_without_a_request_it_falls_back_to_site_url(self):
        from django.conf import settings
        row = self._upload()
        self.assertTrue(row.share_url().startswith(settings.SITE_URL.rstrip("/") + "/u/"))

    def test_the_link_reaches_the_file_on_whatever_host(self):
        row = self._upload()
        self.client.logout()
        resp = self.client.get(row.share_path(), HTTP_HOST="127.0.0.1:8000")
        self.assertEqual(resp.status_code, 200)


class ActionRoutingTests(UploadTestCase):
    """Every action posts its own name.

    The shared confirm dialog re-submits with form.submit(), which drops
    the clicked button -- so an action carried only on a <button name=...>
    never arrives. Delete and Replace-the-link both did that, and the view
    read the missing field as "upload", which is why deleting a file
    answered "Choose a file to upload."
    """

    def test_every_form_carries_its_action_in_a_hidden_field(self):
        self._upload()
        body = self.client.get(ADMIN).content.decode()
        for action in ("upload", "toggle", "relink", "delete"):
            with self.subTest(action):
                self.assertIn(f'name="action" value="{action}"', body)
        # And never on a button, where a programmatic submit loses it.
        self.assertNotRegex(body, r'<button[^>]*name="action"')

    def test_delete_without_its_action_is_not_read_as_an_upload(self):
        row = self._upload()
        resp = self.client.post(ADMIN, {"id": row.pk}, follow=True)
        page = resp.content.decode()
        self.assertNotIn("Choose a file to upload", page)
        self.assertIn("wasn&#x27;t understood", page)
        self.assertTrue(SharedUpload.objects.filter(pk=row.pk).exists())

    def test_an_unknown_action_changes_nothing(self):
        row = self._upload()
        self.client.post(ADMIN, {"action": "destroy", "id": row.pk})
        self.assertTrue(SharedUpload.objects.filter(pk=row.pk).exists())
        self.assertIn(row.object_path, self.bucket)

    def test_delete_with_its_action_really_deletes(self):
        row = self._upload()
        path = row.object_path
        self.client.post(ADMIN, {"action": "delete", "id": row.pk}, follow=True)
        self.assertFalse(SharedUpload.objects.filter(pk=row.pk).exists())
        self.assertNotIn(path, self.bucket)

    def test_the_confirm_dialog_carries_the_clicked_button(self):
        # The root fix, so the three other admin forms that put their
        # action on the button (reactivate an account, approve and send
        # workshop documents) work too.
        js = open("static/dashboard/js/script.js", encoding="utf-8").read()
        block = js[js.index('form[data-confirm]'):]
        block = block[:block.index("form.submit();")]
        self.assertIn("event.submitter", block)
        self.assertIn("carried.name = submitter.name", block)
