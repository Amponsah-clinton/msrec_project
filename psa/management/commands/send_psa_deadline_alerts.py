"""Alerts the CEO about agreements whose completion date is five, three
or one day away -- see psa.deadlines for the logic and for why this
project normally fires it from a page load instead of a scheduled job.

This command is for anyone who does have a way to schedule it (cron, or a
platform's own scheduled-job feature, once a day):

    python manage.py send_psa_deadline_alerts

It is a thin wrapper, not a second implementation, so it can never drift
from what the page-load calls already do. Running it twice in a day sends
nothing the second time.
"""
from django.core.management.base import BaseCommand

from psa.deadlines import send_due_soon_alerts


class Command(BaseCommand):
    help = "Emails the CEO about PSA work due in 5, 3 or 1 days."

    def handle(self, *args, **options):
        sent = send_due_soon_alerts()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} PSA deadline alert(s)."))
