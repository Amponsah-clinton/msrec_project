from .models import SiteSettings


def site_settings(request):
    """Makes the one SiteSettings row available as `site_settings` in
    every template -- the public site's logo/footer (templates/base.html)
    and the dashboard sidebar's logo (templates/dashboards/base.html)
    both read it this way instead of each view having to fetch and pass
    it down, the same idea as accounts.context_processors.profile_avatar
    just above this in TEMPLATES' context_processors list.
    """
    return {"site_settings": SiteSettings.get_solo()}


def maintenance(request):
    """Two small flags for templates while maintenance is on:
      maintenance_locked -- the site is locked right now (login page notice)
      maintenance_admin_bar -- show an administrator the "maintenance is ON" bar
    Cheap: the state is cached for a few seconds (see pages/maintenance.py)."""
    from . import maintenance as m

    try:
        current = m.state()
    except Exception:
        return {}
    if not current["active"]:
        return {}
    user = getattr(request, "user", None)
    return {
        "maintenance_locked": True,
        "maintenance_end": current["end"],
        "maintenance_admin_bar": m.is_bypass_user(user),
    }
