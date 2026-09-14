"""Active-sessions support for dashboards/applicant/profile-security.html.

Django's session framework already tracks every signed-in session
(django.contrib.sessions.models.Session) -- these helpers just describe one
in human terms (device/browser, from the user-agent stashed at login by
accounts.views.login_view) and list every session that currently belongs to
a given user, so the Profile & Security page can show and revoke real
sessions instead of a hardcoded demo list. No new dependency (a proper
user-agent parser) is pulled in for two guessable labels -- this is
intentionally a light heuristic, not device fingerprinting.
"""
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def describe_user_agent(ua):
    ua = ua or ""

    if "Windows" in ua:
        os_label = "Windows"
    elif "iPhone" in ua:
        os_label = "iPhone"
    elif "iPad" in ua:
        os_label = "iPad"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        os_label = "Mac"
    elif "Android" in ua:
        os_label = "Android"
    elif "Linux" in ua:
        os_label = "Linux"
    else:
        os_label = "Unknown device"

    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"
    else:
        browser = "Browser"

    return os_label, browser


def active_sessions_for(user, *, current_session_key=None):
    """Every non-expired session belonging to `user`, newest sign-in first."""
    rows = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if data.get("_auth_user_id") != str(user.pk):
            continue
        os_label, browser = describe_user_agent(data.get("ua", ""))
        login_at = parse_datetime(data.get("login_at", "") or "")
        rows.append({
            "key": session.session_key,
            "is_current": session.session_key == current_session_key,
            "os": os_label,
            "browser": browser,
            "ip": data.get("login_ip", ""),
            "login_at": login_at,
        })
    rows.sort(key=lambda r: r["login_at"] or timezone.now(), reverse=True)
    return rows
