"""Reconcile PENDING payments against Paystack.

For every Payment still sitting PENDING, ask Paystack's verify API what
actually happened to that reference. A genuinely successful charge is marked
SUCCESS and its application is submitted (via the same race-safe
verify_and_finalize the webhook and in-page verify use); an abandoned/never-
paid checkout is left as-is.

Use it to recover charges that were taken but never confirmed because the
applicant's browser dropped the in-page verify step (before the webhook was
wired up, or if a webhook delivery was missed). Safe to run repeatedly.

Usage:
    python manage.py reconcile_payments            # all PENDING payments
    python manage.py reconcile_payments --minutes 10   # only those >10 min old
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments import paystack, services
from payments.models import Payment


class Command(BaseCommand):
    help = "Verify PENDING payments against Paystack and finalize any that actually succeeded."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes", type=int, default=0,
            help="Only reconcile payments created at least this many minutes ago (default: 0 = all).",
        )

    def handle(self, *args, **options):
        from applicant_dashboard.views import finalize_submission

        qs = Payment.objects.filter(status=Payment.Status.PENDING).select_related("application")
        if options["minutes"]:
            cutoff = timezone.now() - timedelta(minutes=options["minutes"])
            qs = qs.filter(created_at__lte=cutoff)

        pending = list(qs.order_by("created_at"))
        self.stdout.write(f"Reconciling {len(pending)} pending payment(s)...\n")

        finalized = failed = untouched = 0
        for payment in pending:
            try:
                ok, reason = services.verify_and_finalize(
                    payment, on_success=lambda app: finalize_submission(app, None)
                )
            except paystack.PaystackError as exc:
                # Reference unknown to Paystack (never paid) or a transient
                # API error -- leave it PENDING, nothing was charged to act on.
                untouched += 1
                self.stdout.write(f"  skip    {payment.reference} ({exc})")
                continue
            except Exception as exc:  # noqa: BLE001 - report, keep going
                untouched += 1
                self.stdout.write(self.style.WARNING(f"  error   {payment.reference} ({exc})"))
                continue

            payment.refresh_from_db()
            if ok:
                finalized += 1
                app_ref = payment.application.reference_no if payment.application else "-"
                self.stdout.write(self.style.SUCCESS(f"  SUCCESS {payment.reference} -> application {app_ref}"))
            elif payment.status == Payment.Status.FAILED:
                failed += 1
                self.stdout.write(f"  failed  {payment.reference} ({reason})")
            else:
                untouched += 1
                self.stdout.write(f"  pending {payment.reference} ({reason})")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {finalized} finalized, {failed} marked failed, {untouched} left pending."
        ))
