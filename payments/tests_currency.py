"""Tests for the approximate USD equivalents shown beside cedi prices
(payments/currency.py).

The live rate lookup is always mocked here -- a test suite must not depend
on a third-party API being up, and must not hammer it.
"""
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.template import Context, Template
from django.test import SimpleTestCase

from payments import currency


class UsdRateTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_env_override_wins_without_any_lookup(self):
        with mock.patch.dict("os.environ", {"USD_GHS_RATE": "12.5"}):
            with mock.patch.object(currency, "_fetch_rate") as fetch:
                self.assertEqual(currency.usd_rate(), Decimal("12.5"))
            fetch.assert_not_called()

    def test_a_nonsense_env_override_is_ignored(self):
        with mock.patch.dict("os.environ", {"USD_GHS_RATE": "not-a-number"}):
            with mock.patch.object(currency, "_fetch_rate", return_value=Decimal("11")):
                self.assertEqual(currency.usd_rate(), Decimal("11"))

    def test_an_out_of_range_env_override_is_ignored(self):
        # A rate of 0 would divide by zero; 50_000 is a sign of a bad unit.
        for bad in ("0", "50000", "-12"):
            with self.subTest(bad=bad):
                cache.clear()
                with mock.patch.dict("os.environ", {"USD_GHS_RATE": bad}):
                    with mock.patch.object(currency, "_fetch_rate", return_value=Decimal("11")):
                        self.assertEqual(currency.usd_rate(), Decimal("11"))

    def test_the_rate_is_looked_up_once_and_cached(self):
        with mock.patch.object(currency, "_fetch_rate", return_value=Decimal("11.5")) as fetch:
            self.assertEqual(currency.usd_rate(), Decimal("11.5"))
            self.assertEqual(currency.usd_rate(), Decimal("11.5"))
            self.assertEqual(currency.usd_rate(), Decimal("11.5"))
        self.assertEqual(fetch.call_count, 1)

    def test_a_failed_lookup_is_also_cached(self):
        """A down API must not be re-hit on every page view."""
        with mock.patch.object(currency, "_fetch_rate", return_value=None) as fetch:
            self.assertIsNone(currency.usd_rate())
            self.assertIsNone(currency.usd_rate())
        self.assertEqual(fetch.call_count, 1)

    def _respond_with(self, payload):
        """Patch urlopen to return `payload` as the rates API's JSON body."""
        import json
        urlopen = mock.patch("payments.currency.urllib.request.urlopen")
        mocked = urlopen.start()
        self.addCleanup(urlopen.stop)
        mocked.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()

    def test_an_out_of_range_live_rate_is_discarded(self):
        """A GHS/USD rate in the thousands means the response isn't what we
        think it is -- better to show nothing than a wrong price."""
        self._respond_with({"rates": {"GHS": 99999}})
        self.assertIsNone(currency._fetch_rate())

    def test_a_usable_live_rate_is_parsed(self):
        self._respond_with({"rates": {"GHS": 11.653982}})
        self.assertEqual(currency._fetch_rate(), Decimal("11.653982"))

    def test_a_response_without_a_ghs_rate_is_discarded(self):
        self._respond_with({"result": "error"})
        self.assertIsNone(currency._fetch_rate())

    def test_malformed_json_is_swallowed(self):
        urlopen = mock.patch("payments.currency.urllib.request.urlopen")
        mocked = urlopen.start()
        self.addCleanup(urlopen.stop)
        mocked.return_value.__enter__.return_value.read.return_value = b"<html>not json</html>"
        self.assertIsNone(currency._fetch_rate())

    def test_a_network_failure_is_swallowed(self):
        with mock.patch("payments.currency.urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(currency._fetch_rate())


class ToUsdTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _rate(self, value):
        return mock.patch.object(currency, "_fetch_rate", return_value=Decimal(value))

    def test_converts_and_rounds_to_two_places(self):
        with self._rate("11.65"):
            self.assertEqual(currency.to_usd(Decimal("150.00")), Decimal("12.88"))

    def test_display_is_prefixed_and_formatted(self):
        with self._rate("11.65"):
            self.assertEqual(currency.usd_display(Decimal("150.00")), "US$12.88")

    def test_nothing_is_shown_without_a_rate(self):
        with mock.patch.object(currency, "_fetch_rate", return_value=None):
            self.assertIsNone(currency.to_usd(Decimal("150.00")))
            self.assertEqual(currency.usd_display(Decimal("150.00")), "")

    def test_a_zero_or_missing_price_shows_nothing(self):
        with self._rate("11.65"):
            self.assertEqual(currency.usd_display(Decimal("0.00")), "")
            self.assertEqual(currency.usd_display(None), "")

    def test_a_price_already_in_another_currency_is_never_converted(self):
        with self._rate("11.65"):
            self.assertEqual(currency.usd_display(Decimal("150.00"), "USD"), "")
            self.assertEqual(currency.usd_display(Decimal("150.00"), "NGN"), "")
            # Case and blank both mean cedis.
            self.assertEqual(currency.usd_display(Decimal("150.00"), "ghs"), "US$12.88")
            self.assertEqual(currency.usd_display(Decimal("150.00"), ""), "US$12.88")


class TemplateTagTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _render(self, template, **ctx):
        return Template("{% load currency_tags %}" + template).render(Context(ctx))

    def test_usd_filter(self):
        with mock.patch.object(currency, "_fetch_rate", return_value=Decimal("11.65")):
            self.assertEqual(self._render("{{ amount|usd }}", amount=Decimal("150.00")), "US$12.88")

    def test_usd_filter_is_blank_without_a_rate(self):
        with mock.patch.object(currency, "_fetch_rate", return_value=None):
            self.assertEqual(self._render("{{ amount|usd }}", amount=Decimal("150.00")), "")

    def test_usd_of_respects_the_rows_currency(self):
        with mock.patch.object(currency, "_fetch_rate", return_value=Decimal("11.65")):
            self.assertEqual(
                self._render("{% usd_of amount cur %}", amount=Decimal("150.00"), cur="GHS"),
                "US$12.88",
            )
            self.assertEqual(
                self._render("{% usd_of amount cur %}", amount=Decimal("150.00"), cur="USD"), ""
            )
