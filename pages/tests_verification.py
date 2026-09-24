"""Tests for the public approval-verification lookup (pages/verification.py)."""
import json
from datetime import timedelta
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from applicant_dashboard.models import Application
from pages import verification as v


def make_app(user, status, decided_days_ago=10, title="Study of X"):
    a = Application.objects.create(applicant=user, status=status, review_type="full",
                                   form_data={"studyTitle": title},
                                   decided_at=timezone.now() - timedelta(days=decided_days_ago))
    a.assign_reference_no()
    return a


class VerificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        U = get_user_model()
        kw = dict(email="p@x.org", password="pw12345678!")
        self.user = U.objects.create_user(**kw, first_name="Ama", last_name="Mensah") if U.USERNAME_FIELD == "email" else U.objects.create_user(username="p", **kw)
        self.ok = make_app(self.user, "approved", 10, "Good <i>study</i>")
        self.old = make_app(self.user, "approved", 800, "Old study")
        self.draft = make_app(self.user, "draft")
        self.rej = make_app(self.user, "not_approved")
        self.url = reverse("pages:verify_lookup")

    def q(self, q):
        r = self.client.get(self.url, {"q": q})
        return r, json.loads(r.content)

    def test_all(self):
        # page renders
        r = self.client.get(reverse("pages:verify")); self.assertEqual(r.status_code, 200)
        self.assertIn(b'data-lookup-url="/verify/lookup/"', r.content)
        self.assertNotIn(b"0142", r.content)

        ref = self.ok.reference_no
        r, d = self.q(ref)
        self.assertEqual(r.status_code, 200); self.assertTrue(d["found"]); self.assertEqual(d["status"], "approved")
        self.assertEqual(d["number"], ref); self.assertEqual(d["title"], "Good <i>study</i>")
        self.assertEqual(d["pi"], self.user.full_name); self.assertTrue(d["code"].startswith("VER-"))
        self.assertTrue(d["approvedOn"] and d["expiresOn"])
        code = d["code"]

        # tolerant number formats
        yr, n = ref.split("/")[1:]
        for variant in [ref.lower(), f"MSREC {yr} {int(n)}", f"msrec{yr}{n}", f"  {ref}  ", f"http://h/verify/?ref={ref}"]:
            _, d2 = self.q(variant); self.assertTrue(d2["found"], variant)
        # by code, tolerant
        for variant in [code, code.lower(), code.replace("-", " "), code.replace("-", ""), f"http://h/verify/?code={code}"]:
            _, d2 = self.q(variant); self.assertTrue(d2["found"], variant); self.assertEqual(d2["number"], ref)
        # expired
        _, d = self.q(self.old.reference_no); self.assertEqual(d["status"], "expired")
        # unapproved look identical to unknown
        for miss in [self.draft.reference_no, self.rej.reference_no, "MSREC/2026/9999", "VER-AAAA-BBBB", "garbage", "MSREC/2026/"]:
            r, d = self.q(miss); self.assertEqual(r.status_code, 200); self.assertFalse(d["found"], miss)
            self.assertEqual(set(d), {"ok", "found", "query"})
        # blank
        r, d = self.q("   "); self.assertEqual(r.status_code, 400)
        r = self.client.get(self.url); self.assertEqual(r.status_code, 400)
        # code isn't derivable from another ref
        self.assertNotEqual(v.verification_code("MSREC/2026/0001"), v.verification_code("MSREC/2026/0002"))
        self.assertEqual(v.verification_code(ref), code)

        # letters show block for approved, applicant view
        self.client.force_login(self.user)
        for kind in ("approval", "certificate", "decision"):
            resp = self.client.get(reverse("applicant_dashboard:application_letter", args=[self.ok.pk, kind]))
            self.assertEqual(resp.status_code, 200, kind)
            html = resp.content.decode()
            self.assertIn(code, html); self.assertIn("data:image/svg+xml", html); self.assertIn("/verify/", html)
        resp = self.client.get(reverse("applicant_dashboard:application_letter", args=[self.rej.pk, "decision"]))
        self.assertNotIn("Verify this approval", resp.content.decode())

    def test_rate_limit(self):
        for i in range(30):
            self.assertEqual(self.client.get(self.url, {"q": "x"}).status_code, 200)
        r = self.client.get(self.url, {"q": "x"})
        self.assertEqual(r.status_code, 429); self.assertIn("Retry-After", r)
