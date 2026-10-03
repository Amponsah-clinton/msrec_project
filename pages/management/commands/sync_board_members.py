"""Backfill the public Board & Committee page (/board-committee/) with every
account that already holds an auto-published standing: an approved Reviewer
or Committee member, or a Secretariat account.

New approvals / role changes publish themselves automatically (see
admin_dashboard.views._handle_role_decision and _handle_edit ->
pages.committee_services.sync_governance_member_from_user); this command is
the one-off catch-up for accounts that reached that standing beforehand.

Idempotent: a card already exists per account (keyed on the OneToOne user),
so re-running only publishes the ones still missing and moves any card whose
account's standing has since changed (e.g. Reviewer -> Committee/Secretariat).

Usage: python manage.py sync_board_members
"""

from django.core.management.base import BaseCommand

from accounts.models import User
from pages.committee_services import sync_governance_member_from_user


class Command(BaseCommand):
    help = "Publish all approved reviewers/committee members and Secretariat accounts on the Board & Committee page."

    def handle(self, *args, **options):
        approved = User.RequestStatus.APPROVED
        members = (
            User.objects.filter(reviewer_status=approved)
            | User.objects.filter(committee_status=approved)
            | User.objects.filter(role=User.Role.SECRETARIAT)
        )
        members = members.distinct()

        published = 0
        for user in members:
            card = sync_governance_member_from_user(user)
            if card is not None:
                published += 1
                self.stdout.write(f"  {card.get_group_display():10} {card.full_name}")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. {published} approved member(s) published on the Board & Committee page.")
        )
