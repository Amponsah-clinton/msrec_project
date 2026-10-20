from django.test import TestCase

# Create your tests here.


class FileProxyDownloadTests(TestCase):
    """/files/<token>/ opens a file inline by default, and ?download=1
    (the Resource Centre's download buttons) saves it instead."""

    def _url(self):
        from django.core import signing
        from django.urls import reverse
        from pages import file_proxy
        token = signing.dumps({"b": "resources", "p": "guidelines/1/Guide.docx"}, salt=file_proxy.SALT)
        return reverse("pages:file_proxy", kwargs={"token": token})

    def test_inline_by_default_and_attachment_on_request(self):
        from unittest import mock
        with mock.patch("pages.file_proxy._fetch", return_value=(b"data", "application/octet-stream")):
            inline = self.client.get(self._url())
            saved = self.client.get(self._url() + "?download=1")
        self.assertTrue(inline["Content-Disposition"].startswith('inline; filename="Guide.docx"'))
        self.assertTrue(saved["Content-Disposition"].startswith('attachment; filename="Guide.docx"'))
