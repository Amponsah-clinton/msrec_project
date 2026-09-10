import re
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# (url_name, source_html, css_basename_or_None, js_basename_or_None)
PAGES = [
    ("about", "about.html", "about", "about"),
    ("applicants", "applicants.html", "applicants", "applicants"),
    ("ethics_review", "ethics-review.html", "ethics-review", "ethics-review"),
    ("resources", "resources.html", "resources", "resources"),
    ("governance", "governance.html", "governance", "governance"),
    ("board_committee", "board-committee.html", "board-committee", "board-committee"),
    ("verify", "verify.html", "verify", "verify"),
    ("contact", "contact.html", "contact", "contact"),
    ("apply", "apply.html", "apply", "apply"),
    ("login", "login.html", "login", "login"),
    ("signup", "signup.html", "signup", "signup"),
]

# href in source -> url tag replacement (without quotes)
LINK_MAP = {
    "index.html#hero": "{% url 'pages:index' %}#hero",
    "index.html": "{% url 'pages:index' %}",
    "about.html": "{% url 'pages:about' %}",
    "applicants.html": "{% url 'pages:applicants' %}",
    "ethics-review.html": "{% url 'pages:ethics_review' %}",
    "ethics-review.html#er-meetings": "{% url 'pages:ethics_review' %}#er-meetings",
    "resources.html": "{% url 'pages:resources' %}",
    "governance.html": "{% url 'pages:governance' %}",
    "board-committee.html": "{% url 'pages:board_committee' %}",
    "board-committee.html#bc-meetings": "{% url 'pages:board_committee' %}#bc-meetings",
    "verify.html": "{% url 'pages:verify' %}",
    "contact.html": "{% url 'pages:contact' %}",
    "apply.html": "{% url 'pages:apply' %}",
    "login.html": "{% url 'pages:login' %}",
    "signup.html": "{% url 'pages:signup' %}",
}


def rewrite_links(html: str) -> str:
    # Longer/more-specific keys first so "board-committee.html#bc-meetings"
    # is matched before the bare "board-committee.html".
    for href, repl in sorted(LINK_MAP.items(), key=lambda kv: -len(kv[0])):
        html = html.replace(f'href="{href}"', f'href="{repl}"')
    # Static assets
    html = re.sub(
        r'src="assets/([^"]+)"',
        lambda m: 'src="{%% static \'assets/%s\' %%}"' % m.group(1),
        html,
    )
    html = re.sub(
        r'href="assets/([^"]+)"',
        lambda m: 'href="{%% static \'assets/%s\' %%}"' % m.group(1),
        html,
    )
    return html


def extract(src_path: str):
    with open(src_path, "r", encoding="utf-8") as f:
        html = f.read()

    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
    desc_m = re.search(r'<meta name="description" content="(.*?)">', html, re.S)
    description = desc_m.group(1).strip() if desc_m else ""

    body_class_m = re.search(r'<body class="([^"]*)">', html)
    body_class = body_class_m.group(1) if body_class_m else ""

    uses_fraunces = "family=Fraunces" in html

    main_m = re.search(r"<main[^>]*class=\"([^\"]*)\"[^>]*>(.*?)</main>", html, re.S)
    main_class = main_m.group(1).strip()
    main_inner = main_m.group(2)

    return {
        "title": title,
        "description": description,
        "body_class": body_class,
        "uses_fraunces": uses_fraunces,
        "main_class": main_class,
        "main_inner": rewrite_links(main_inner),
    }


BASE_TEMPLATE = '''{{% extends "base.html" %}}
{{% load static %}}

{{% block title %}}{title}{{% endblock %}}
{{% block description %}}{description}{{% endblock %}}
{{% block body_class %}}{body_class}{{% endblock %}}
{{% block fonts %}}{fonts_block}{{% endblock %}}
{{% block extra_css %}}
<link href="{{% static 'assets/css/{css}.css' %}}" rel="stylesheet">
{{% endblock %}}

{{% block content %}}
  <main class="{main_class}">
{main_inner}
  </main>
{{% endblock %}}

{{% block extra_js %}}
<script src="{{% static 'assets/js/{js}.js' %}}"></script>
{{% endblock %}}
'''

FRAUNCES_LINK = '<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
DEFAULT_LINK = '<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,100;0,300;0,400;0,500;0,700;0,900&family=Montserrat:wght@500;600;700;800&display=swap" rel="stylesheet">'

out_dir = os.path.join(ROOT, "templates", "pages")
os.makedirs(out_dir, exist_ok=True)

for url_name, src_file, css, js in PAGES:
    data = extract(os.path.join(ROOT, src_file))
    fonts_block = FRAUNCES_LINK if data["uses_fraunces"] else DEFAULT_LINK
    content = BASE_TEMPLATE.format(
        title=data["title"],
        description=data["description"],
        body_class=data["body_class"],
        fonts_block=fonts_block,
        css=css,
        main_class=data["main_class"],
        main_inner=data["main_inner"],
        js=js,
    )
    out_path = os.path.join(out_dir, f"{url_name}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("wrote", out_path)
