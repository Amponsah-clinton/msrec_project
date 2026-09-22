"""Sends the "3 days left" deadline reminder to reviewers whose open
assignment is due soon -- see reviewer_dashboard.reminders for the actual
logic and why this project normally fires it opportunistically from a
page load instead of a scheduled job.

This command exists for anyone who *does* have a way to schedule it
(cron, a platform's own scheduled-job feature, e.g. `python manage.py
send_review_deadline_reminders` once a day) -- it's a thin wrapper, not a
second implementation, so it can never drift from what the opportunistic
calls already do.

    python manage.py send_review_deadline_reminders
"""
from django.core.management.base import BaseCommand

from reviewer_dashboard.reminders import send_due_soon_reminders


class Command(BaseCommand):
    help = "Emails reviewers whose open (not yet completed) assignment is due within the next few days."

    def handle(self, *args, **options):
        sent = send_due_soon_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} review deadline reminder(s)."))
