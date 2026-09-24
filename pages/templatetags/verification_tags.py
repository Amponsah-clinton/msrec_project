from django import template

from pages import verification

register = template.Library()


@register.inclusion_tag("pages/_verification_block.html", takes_context=True)
def verification_block(context, application):
    """The verification code + QR shown on approval letters and certificates.
    Renders nothing for an application without a reference number."""
    reference_no = application.reference_no
    if not reference_no:
        return {"reference_no": None}
    url = verification.verify_url(context["request"], reference_no)
    return {
        "reference_no": reference_no,
        "code": verification.verification_code(reference_no),
        "url": url,
        "page_url": url.split("?")[0],
        "qr": verification.qr_svg_data_uri(url),
    }
