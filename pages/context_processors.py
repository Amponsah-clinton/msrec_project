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
