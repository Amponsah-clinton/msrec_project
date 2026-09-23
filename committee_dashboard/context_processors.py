def reviewer_workload(request):
    """Feeds the "My Reviews" sidebar badge on every Committee page.

    Every approved Committee member is automatically an approved Reviewer
    too (accounts.models.User.approve_role grants reviewer_status=APPROVED
    the moment a Committee request is approved) and can be assigned
    applications to review the same way any other reviewer can
    (secretariat_dashboard.views.reviewer_assignment filters candidates by
    reviewer_status, not by role). The two dashboards are otherwise
    separate apps/URL namespaces, so without this a Committee member could
    have open review assignments sitting untouched with no signal of that
    from the Committee dashboard they actually log into.

    Scoped to role == committee so it's a no-op (and does no extra query)
    for every other dashboard, even though it's registered globally in
    settings.py -- same pattern as applicant_dashboard.context_processors.
    notif_bell and secretariat_dashboard.context_processors.unread_messages.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role != user.Role.COMMITTEE:
        return {}
    if user.reviewer_status != user.RequestStatus.APPROVED:
        return {}

    from reviewer_dashboard.models import ReviewAssignment

    open_review_count = (
        ReviewAssignment.objects.filter(reviewer=user)
        .exclude(status__in=[ReviewAssignment.Status.DECLINED, ReviewAssignment.Status.COMPLETED])
        .count()
    )
    return {"nav_open_review_count": open_review_count}
