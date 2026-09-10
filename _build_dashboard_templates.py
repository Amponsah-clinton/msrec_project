import re
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# (url_name, source_folder)
DASHBOARDS = [
    ("reviewer", "msrec-reviewer-dashboard"),
    ("applicant", "msrec-applicant-dashboard"),
    ("committee", "msrec-committee-dashboard"),
    ("chair", "msrec-chair-dashboard"),
    ("secretariat", "msrec-secretariat-dashboard"),
]

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

out_dir = os.path.join(ROOT, "templates", "dashboards")
os.makedirs(out_dir, exist_ok=True)

for url_name, folder in DASHBOARDS:
    src_path = os.path.join(ROOT, folder, "index.html")
    with open(src_path, "r", encoding="utf-8") as f:
        html = f.read()

    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
    nav_content = re.search(r'<nav class="nav">(.*?)</nav>', html, re.S).group(1)
    topbar = re.search(r'<header class="topbar">(.*?)</header>', html, re.S).group(1)
    main_content = re.search(r'<main class="content">(.*?)</main>', html, re.S).group(1)

    content = TEMPLATE.format(
        title=title,
        nav_content=nav_content,
        topbar=topbar,
        main_content=main_content,
    )
    out_path = os.path.join(out_dir, f"{url_name}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("wrote", out_path)
