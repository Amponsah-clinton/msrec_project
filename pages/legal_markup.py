"""The small, safe markup the Terms of Service / Privacy Policy sections are
written in (Site Settings > Legal Pages), rendered to HTML for
templates/pages/legal.html.

Everything an editor types is HTML-escaped first; only the constructs below
become markup, so a stray "<" or a pasted <script> is shown as text, never
run.

Blocks (separated by a blank line, or by a change of kind):
    plain lines            a paragraph (consecutive lines join into one)
    - item                 a bullet list
    1. item                a numbered list
    ### Heading            a sub-heading
    > text                 a highlighted note
    | Cell | Cell |        a table; the first row is the header row

Inline:
    **bold**   *italic*
    [text](https://...)   [text](mailto:...)   [text](#section)   [text](/path/)
    [text](page:contact)  -- any public page by its name: page:privacy,
                             page:fees, page:governance#gov-policies ...
    bare emails become mailto links

Placeholders, filled in from Site Settings so a changed address updates
every page: {email} (Secretariat email), {site_name}.
"""
import re

from django.urls import NoReverseMatch, reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")
_EMAIL = re.compile(r"(?<![\w.@/:\"'>])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w@])")
_NUMBERED = re.compile(r"^\d+[.)]\s+")


def _resolve(target):
    """An href for a [text](target) link, or None to leave it as text.
    Only web, mail, same-page and site-relative links are allowed --
    never javascript: or data: URLs."""
    if target.startswith("page:"):
        name, _, fragment = target[5:].partition("#")
        try:
            url = reverse(f"pages:{name}")
        except NoReverseMatch:
            return None
        return url + (f"#{fragment}" if fragment else "")
    if target.startswith(("https://", "http://", "mailto:", "#")):
        return target
    if target.startswith("/") and not target.startswith("//"):
        return target
    return None


def _inline(text, values):
    """One already-escaped line with inline markup applied."""
    for key, value in values.items():
        text = text.replace("{" + key + "}", escape(value))

    links = []

    def keep_link(match):
        label, target = match.group(1), match.group(2).replace("&amp;", "&")
        href = _resolve(target)
        if href is None:
            return label
        external = href.startswith(("http://", "https://"))
        attrs = ' target="_blank" rel="noopener"' if external else ""
        links.append(f'<a href="{escape(href)}"{attrs}>{label}</a>')
        return f"\x00{len(links) - 1}\x00"

    # Links first, parked behind placeholders so the email rule can't
    # re-link an address that is already inside one.
    text = _LINK.sub(keep_link, text)
    text = _EMAIL.sub(r'<a href="mailto:\1">\1</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], text)


def _kind(line):
    if line.startswith("### "):
        return "h"
    if line.startswith("- ") or line == "-":
        return "ul"
    if _NUMBERED.match(line):
        return "ol"
    if line.startswith("|"):
        return "table"
    if line.startswith(">"):
        return "note"
    return "p"


def _table(rows, values):
    cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    # Markdown-style "|---|---|" separator rows are just decoration.
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c or "--") for c in r)]
    if not cells:
        return ""
    head, body = cells[0], cells[1:]
    html = ['<div class="legal-table-wrap"><table class="legal-table"><thead><tr>']
    html += [f"<th>{_inline(escape(c), values)}</th>" for c in head]
    html.append("</tr></thead><tbody>")
    for row in body:
        html.append("<tr>" + "".join(f"<td>{_inline(escape(c), values)}</td>" for c in row) + "</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


def render(text, values=None):
    """`text` in the markup above, as safe HTML."""
    values = values or {}
    blocks, current, kind = [], [], None

    def flush():
        if current:
            blocks.append((kind, list(current)))
            current.clear()

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            kind = None
            continue
        this = _kind(line)
        if this != kind or this == "h":
            flush()
            kind = this
        current.append(line)
    flush()

    html = []
    for kind, lines in blocks:
        if kind == "h":
            html.append(f"<h4>{_inline(escape(lines[0][4:].strip()), values)}</h4>")
        elif kind == "ul":
            items = "".join(f"<li>{_inline(escape(l[1:].strip()), values)}</li>" for l in lines)
            html.append(f"<ul>{items}</ul>")
        elif kind == "ol":
            items = "".join(f"<li>{_inline(escape(_NUMBERED.sub('', l)), values)}</li>" for l in lines)
            html.append(f"<ol>{items}</ol>")
        elif kind == "table":
            html.append(_table(lines, values))
        elif kind == "note":
            body = " ".join(l.lstrip(">").strip() for l in lines)
            html.append(
                '<div class="legal-note"><i class="bi bi-info-circle" aria-hidden="true"></i>'
                f"<p>{_inline(escape(body), values)}</p></div>"
            )
        else:
            html.append(f"<p>{_inline(escape(' '.join(lines)), values)}</p>")
    return mark_safe("".join(html))


def render_inline(text, values=None):
    """A single line (a section's summary) -- inline markup only."""
    return mark_safe(_inline(escape(" ".join((text or "").split())), values or {}))


def word_count(text):
    return len(re.findall(r"\w+", text or ""))
