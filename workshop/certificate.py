"""Workshop certificate PDF.

Same MSREC "white edition" look as the Peer Review / Committee certificates
(it reuses their exact border, seal, logo letterhead, title and typography
from reviewer_dashboard.certificate). A workshop certificate can carry TWO
signatures, and each workshop sets its own wording, signatories and which
elements (body, seal, second signature, verification footer) appear --
Signature 1 falls back to the Chair (Site Settings -> Certificates) when left
blank, keeping it consistent with every other MSREC certificate.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph

from reviewer_dashboard.certificate import (
    BRASS, INK, INK_SOFT, PAGE_H, PAGE_W,
    _border, _seal, _signature_image, _spaced, draw_header, draw_title,
)


def _sig_block(c, cx, y, name, title, signature_png):
    if signature_png:
        _signature_image(c, cx, y, signature_png)
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.line(cx - 35 * mm, y, cx + 35 * mm, y)
    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    if name:
        c.drawCentredString(cx, y - 6 * mm, name)
    if title:
        _spaced(c, title.upper(), cx, y - 11 * mm, "Times-Roman", 8.5, 1.2, INK_SOFT)


def _date_block(c, cx, y, issued_at):
    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    if issued_at:
        c.drawCentredString(cx, y - 6 * mm, issued_at.strftime("%d %B %Y").lstrip("0"))
    _spaced(c, "DATE OF ISSUE", cx, y - 11 * mm, "Times-Roman", 8.5, 1.2, INK_SOFT)


def _signatories(workshop):
    """(sig1, sig2) each (name, title, png|None). Slot 1 falls back to the
    Chair when no name is set."""
    from . import storage

    def png(path):
        return storage.download_object(path) if path else None

    s1_name = (workshop.cert_sig1_name or "").strip()
    if s1_name:
        sig1 = (s1_name, (workshop.cert_sig1_title or "").strip(), png(workshop.cert_sig1_signature_path))
    else:
        from pages.certificate_signatory import chair_details, chair_signature_bytes
        ch = chair_details()
        sig1 = (ch["name"], ch["title"], chair_signature_bytes(ch))

    sig2 = (
        (workshop.cert_sig2_name or "").strip(),
        (workshop.cert_sig2_title or "").strip() or "Workshop Coordinator",
        png(workshop.cert_sig2_signature_path),
    )
    return sig1, sig2


# ---------------------------------------------------------------------
# The certifying statement
# ---------------------------------------------------------------------
# The programme is the thing the certificate is about, so it is set as
# its own line rather than left buried mid-sentence in the body prose.
# The admin's wording decides where it sits: whatever comes before
# {workshop} becomes the lead-in above it, whatever follows becomes the
# trailing prose below. "participated in the {workshop} organised by the
# Committee..." therefore reads
#
#                        participated in the
#          Advanced Workshop on Research Ethics and Integrity
#       organised by the Committee, and is recognised for their...
#
# which is how a certificate is normally set, and needs no change to any
# wording anyone has already written.

STATEMENT_W = 196 * mm          # the programme may run wider than the prose
PROSE_W = 178 * mm
GAP_ABOVE_PROGRAMME = 3.2 * mm
GAP_BELOW_PROGRAMME = 3.6 * mm

# Tried largest first; the first combination that fits the space between
# the name and the seal wins. The programme gives up size last -- making
# it distinct is the point, so the prose around it yields first.
PROGRAMME_SIZES = (21, 19.5, 18, 16.5, 15, 14, 13, 12, 11)
PROSE_SIZES = (13.5, 13, 12.5, 12, 11.5, 11, 10.5, 10)


def _split_statement(body_template, title, name):
    """(lead, programme, tail) from the workshop's own wording.

    Without a {workshop} placeholder there is nothing to split around, so
    the programme is given its own line above whatever the body says."""
    raw = body_template or ""
    programme = " ".join((title or "").split())
    if "{workshop}" in raw:
        before, _, after = raw.partition("{workshop}")
        lead = " ".join(before.replace("{name}", name).split())
        tail = " ".join(after.replace("{name}", name).split())
    else:
        lead = ""
        tail = " ".join(raw.replace("{name}", name).split())
    return lead, programme, tail


def _para(text, font, size, leading, color, width, *, escape_text=False):
    """(flowable, height) centred at `width`, or (None, 0) for empty text."""
    if not text:
        return None, 0.0
    if escape_text:
        text = escape(text)
    p = Paragraph(text, ParagraphStyle(
        "s", fontName=font, fontSize=size, leading=leading, textColor=color, alignment=TA_CENTER))
    return p, p.wrap(width, 400 * mm)[1]


def _statement_layout(lead, programme, tail, *, show_prose, budget):
    """The biggest set of sizes whose stack fits `budget`, as a list of
    (flowable, height) in drawing order plus the total height.

    Always returns something: if even the smallest sizes overrun -- a very
    long programme on a certificate that also wants a seal -- the smallest
    is used and the caller tightens the gap instead of dropping words."""
    attempt = None
    # Programme size is the outer loop and is tried largest first, so the
    # prose around it gives up its size before the programme gives up any
    # of its own. Making the programme stand out is the whole point.
    for prog_size in PROGRAMME_SIZES:
        for prose_size in PROSE_SIZES:
            rows, total = [], 0.0
            if show_prose and lead:
                flowable, height = _para(lead, "Times-Italic", prose_size,
                                         prose_size * 1.42, INK_SOFT, PROSE_W)
                rows.append(("prose", flowable, height))
                total += height + GAP_ABOVE_PROGRAMME
            if programme:
                flowable, height = _para(programme, "Times-Bold", prog_size, prog_size * 1.26,
                                         BRASS, STATEMENT_W, escape_text=True)
                rows.append(("programme", flowable, height))
                total += height
            if show_prose and tail:
                flowable, height = _para(tail, "Times-Roman", prose_size,
                                         prose_size * 1.46, INK_SOFT, PROSE_W)
                total += GAP_BELOW_PROGRAMME + height
                rows.append(("prose", flowable, height))
            if total <= budget:
                return rows, total
            attempt = (rows, total)              # the floor, if nothing fits
    return attempt


def render_workshop_certificate_pdf(registration, *, workshop=None):
    """Certificate PDF bytes for one registration, using its workshop's design.

    `workshop` lets the admin preview an *unsaved* design (a transient
    Workshop built from the posted fields). When omitted, the registration's
    saved workshop is used.
    """
    workshop = workshop or registration.workshop

    cert_id = registration.ensure_certificate_ref()
    issued_at = registration.paid_at or registration.created_at
    message = (workshop.cert_body or "").replace("{workshop}", workshop.title).replace("{name}", registration.name)

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Certificate {workshop.cert_title_tail} - {cert_id}")

    _border(c)
    mid = PAGE_W / 2
    draw_header(c)

    title_y = PAGE_H - 60 * mm
    draw_title(c, title_y, "Certificate", workshop.cert_title_tail or "")

    c.setFont("Times-Italic", 14)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(mid, title_y - 22 * mm, (workshop.cert_intro or "This is to certify that"))

    name = registration.name
    name_y = title_y - 36 * mm
    name_size = 34
    while name_size > 20 and c.stringWidth(name, "Times-Bold", name_size) > 200 * mm:
        name_size -= 1
    c.setFont("Times-Bold", name_size)
    c.setFillColor(INK)
    c.drawCentredString(mid, name_y, name)

    name_w = max(c.stringWidth(name, "Times-Bold", name_size), 90 * mm)
    span = name_w + 12 * mm
    left = mid - span / 2
    c.setStrokeColor(BRASS)
    c.setLineWidth(0.9)
    for i in range(40):
        t = (i + 0.5) / 40
        c.setStrokeAlpha(min(1.0, min(t, 1 - t) * 5))
        c.line(left + span * i / 40, name_y - 4 * mm, left + span * (i + 1) / 40, name_y - 4 * mm)
    c.setStrokeAlpha(1.0)

    sign_y = 46 * mm

    # The statement sits between the rule under the name and whatever
    # comes next below it -- the seal when there is one, otherwise the
    # signature line. Measured, not assumed, so a long programme shrinks
    # to fit instead of running into the seal.
    if workshop.cert_show_programme:
        lead, programme, tail = _split_statement(workshop.cert_body, workshop.title,
                                                 registration.name)
    else:
        # Turned off, the programme goes back where the wording expects
        # it -- inline in the sentence. Splitting the body around a
        # placeholder and then dropping it would leave "participated in
        # the organised by the Committee".
        lead, programme, tail = "", "", message.strip()
    floor = (sign_y + 24 * mm) if workshop.cert_show_seal else (sign_y + 11 * mm)
    top = name_y - 10 * mm
    rows, total = _statement_layout(
        lead, programme, tail, show_prose=workshop.cert_show_body, budget=top - floor,
    )
    y = top
    for kind, flowable, height in rows:
        if flowable is None:
            continue
        width = STATEMENT_W if kind == "programme" else PROSE_W
        y -= height
        flowable.drawOn(c, mid - width / 2, y)
        y -= GAP_BELOW_PROGRAMME if kind == "programme" else GAP_ABOVE_PROGRAMME

    (s1_name, s1_title, s1_png), (s2_name, s2_title, s2_png) = _signatories(workshop)
    if workshop.cert_show_second_signature:
        _sig_block(c, mid - 82 * mm, sign_y, s1_name, s1_title, s1_png)
        _sig_block(c, mid + 82 * mm, sign_y, s2_name, s2_title, s2_png)
    else:
        _date_block(c, mid - 82 * mm, sign_y, issued_at)
        _sig_block(c, mid + 82 * mm, sign_y, s1_name, s1_title, s1_png)

    if workshop.cert_show_seal:
        _seal(c, mid, sign_y + 6 * mm, workshop.cert_seal_caption or "WORKSHOP")

    if workshop.cert_show_verification:
        _spaced(c, f"CERTIFICATE NO. {cert_id}", mid, 24 * mm, "Times-Roman", 8.5, 1.0, INK_SOFT)

    c.showPage()
    c.save()
    return buffer.getvalue()


def _watermark_overlay_bytes(text="SPECIMEN · NOT A VALID CERTIFICATE"):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape

    W, H = landscape(A4)
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H))
    c.saveState()
    c.translate(W / 2, H / 2)
    c.rotate(30)
    c.setFillColor(colors.HexColor("#c0392b"))
    c.setFillAlpha(0.16)
    c.setFont("Helvetica-Bold", 30)
    for row in range(-5, 6):
        c.drawCentredString(0, row * 46, text)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def render_sample_certificate_pdf(workshop, sample_name="Your Name Here"):
    """Watermarked sample of a workshop's certificate for the public preview."""
    from django.utils import timezone
    from pypdf import PdfReader, PdfWriter

    from .models import WorkshopRegistration

    sample = WorkshopRegistration(
        workshop=workshop,
        name=(sample_name or "Your Name Here").strip()[:80] or "Your Name Here",
        institution="Sample Institution", email="sample@example.com",
        wants_certificate=True, payment_status=WorkshopRegistration.PaymentStatus.SUCCESS,
    )
    sample.paid_at = timezone.now()
    sample.pk = 0

    base = render_workshop_certificate_pdf(sample, workshop=workshop)
    overlay = _watermark_overlay_bytes()

    base_reader = PdfReader(BytesIO(base))
    wm_page = PdfReader(BytesIO(overlay)).pages[0]
    writer = PdfWriter()
    for page in base_reader.pages:
        page.merge_page(wm_page)
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
