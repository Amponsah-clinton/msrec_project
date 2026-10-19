"""Template access to the approximate USD equivalent of a cedi price.

The rate behind these is cached (see payments/currency.py), so a page may
use them more than once without repeating any lookup.
"""
from django import template

from payments import currency

register = template.Library()


@register.filter
def usd(amount):
    """`{{ ws.certificate_fee|usd }}` -> "US$13.04", or "" when no rate is
    available. Assumes the amount is in GHS; use `usd_of` when the row
    carries its own currency."""
    return currency.usd_display(amount)


@register.simple_tag
def usd_of(amount, currency_code):
    """`{% usd_of reg.amount reg.currency %}` -- blank unless the amount is
    actually in cedis, so a row priced in another currency is never
    converted as though it were."""
    return currency.usd_display(amount, currency_code)
