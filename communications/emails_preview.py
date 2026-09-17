"""Renders an EmailTemplate through the same branded shell every real
outbound email uses (notifications.emails), filled with sample data, so
"Preview" shows the Secretariat exactly what a recipient will see --
never a bare textarea dump of the raw {{ placeholder }} source.
"""
from notifications.emails import render_email_html

SAMPLE_CONTEXT = {
    "full_name": "Dr. Amina Yusuf",
    "first_name": "Amina",
    "reference_no": "MSREC-2026-0142",
    "study_title": "Community Health Literacy in Peri-Urban Accra",
    "status": "Under Review",
    "deadline": "30 September 2026",
}


def render_template_preview(email_template):
    subject, body = email_template.render(**SAMPLE_CONTEXT)
    paragraphs = [line for line in body.splitlines()]
    return render_email_html(
        heading=subject,
        paragraphs=paragraphs,
        preheader=subject,
    )
