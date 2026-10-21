"""{{ amounts|money }} -- a payments.ledger money list ([("GHS", Decimal), ...])
as "GHS 1,234.00 + USD 10.00", or "GHS 0.00" when there's nothing."""
from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def money(amounts):
    parts = [f"{currency} {floatformat(amount, '2g')}" for currency, amount in (amounts or [])]
    return " + ".join(parts) if parts else "GHS 0.00"
