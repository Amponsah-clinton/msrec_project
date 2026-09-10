import re
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# Each dashboard app maps to its source folder and the list of pages it has.
# (url_name, source_filename, output_template_path_relative_to_templates/dashboards)
# Single-page dashboards keep exactly the output path they always had, so their
# urls.py (template_name="dashboards/<name>.html") needs no changes. The
# applicant dashboard now has multiple pages, so its extra pages are written
# into a "applicant/" subfolder and applicant_dashboard/urls.py gains matching
# routes (see the bottom of this file for the exact patterns to paste there).
DASHBOARDS = {
    "reviewer": {
        "folder": "msrec-reviewer-dashboard",
        "pages": [("home", "index.html", "reviewer.html")],
    },
    "committee": {
        "folder": "msrec-committee-dashboard",
        "pages": [("home", "index.html", "committee.html")],
    },
    "chair": {
        "folder": "msrec-chair-dashboard",
        "pages": [("home", "index.html", "chair.html")],
    },
    "secretariat": {
        "folder": "msrec-secretariat-dashboard",
        "pages": [("home", "index.html", "secretariat.html")],
    },
    "applicant": {
        "folder": "msrec-applicant-dashboard",
        "pages": [
            ("home", "index.html", "applicant.html"),
            ("application_new", "application-new.html", "applicant/application-new.html"),
            ("application_drafts", "application-drafts.html", "applicant/application-drafts.html"),
            ("application_submitted", "application-submitted.html", "applicant/application-submitted.html"),
            ("application_under_review", "application-under-review.html", "applicant/application-under-review.html"),
            ("application_revisions", "application-revisions.html", "applicant/application-revisions.html"),
            ("application_approved", "application-approved.html", "applicant/application-approved.html"),
            ("application_not_approved", "application-not-approved.html", "applicant/application-not-approved.html"),
        ],
    },
}

# Internal hrefs in the static prototype -> the Django {% url %} tag that
# replaces them. Only dashboards with more than one page (currently just
# "applicant") need one; single-page dashboards have no internal nav links
# to rewrite (every sublink on those pages is still the "#" placeholder).
LINK_MAPS = {
    "applicant": {
        "index.html": "{% url 'applicant_dashboard:home' %}",
        "application-new.html": "{% url 'applicant_dashboard:application_new' %}",
        "application-drafts.html": "{% url 'applicant_dashboard:application_drafts' %}",
        "application-submitted.html": "{% url 'applicant_dashboard:application_submitted' %}",
        "application-under-review.html": "{% url 'applicant_dashboard:application_under_review' %}",
        "application-revisions.html": "{% url 'applicant_dashboard:application_revisions' %}",
        "application-approved.html": "{% url 'applicant_dashboard:application_approved' %}",
        "application-not-approved.html": "{% url 'applicant_dashboard:application_not_approved' %}",
        "../apply.html": "{% url 'pages:apply' %}",
    },
}

TEMPLATE = '''{{% extends "dashboards/base.html" %}}

{{% block title %}}{title}{{% endblock %}}

{{% block nav_content %}}
{nav_content}
{{% endblock %}}

{{% block topbar %}}
{topbar}
{{% endblock %}}

{{% block main_content %}}
{main_content}
{{% endblock %}}
'''


def rewrite_links(html: str, link_map: dict | None) -> str:
    if not link_map:
        return html
    # Longer keys first so a more specific href (if any are ever added) can't
    # get shadowed by a shorter one that happens to be a substring.
    for href, repl in sorted(link_map.items(), key=lambda kv: -len(kv[0])):
        html = html.replace(f'href="{href}"', f'href="{repl}"')
    return html


out_root = os.path.join(ROOT, "templates", "dashboards")

for app_name, cfg in DASHBOARDS.items():
    folder = cfg["folder"]
    link_map = LINK_MAPS.get(app_name)

    for url_name, src_file, tpl_rel_path in cfg["pages"]:
        src_path = os.path.join(ROOT, folder, src_file)
        with open(src_path, "r", encoding="utf-8") as f:
            html = f.read()

        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
        nav_content = re.search(r'<nav class="nav">(.*?)</nav>', html, re.S).group(1)
        topbar = re.search(r'<header class="topbar">(.*?)</header>', html, re.S).group(1)
        main_content = re.search(r'<main class="content">(.*?)</main>', html, re.S).group(1)

        nav_content = rewrite_links(nav_content, link_map)
        topbar = rewrite_links(topbar, link_map)
        main_content = rewrite_links(main_content, link_map)

        content = TEMPLATE.format(
            title=title,
            nav_content=nav_content,
            topbar=topbar,
            main_content=main_content,
        )

        out_path = os.path.join(out_root, tpl_rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("wrote", out_path)

print()
print("NOTE: applicant_dashboard/urls.py must include a path() for every")
print("'application_*' url_name above (besides the existing 'home' route)")
print("for these new templates to actually be reachable — see that file.")
