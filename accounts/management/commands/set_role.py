"""Set a user's primary role from the command line.

    python manage.py set_role ceo@academicdigital.space secretariat

Run it where the database is reachable (the production server, or any
machine that can connect to the configured DATABASE_URL). Only the
primary `role` field is changed -- reviewer_status / committee_status and
the password are left untouched.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Set a user's primary role: manage.py set_role <email> <role>"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "role",
            choices=[c[0] for c in User.Role.choices],
            help="one of: " + ", ".join(c[0] for c in User.Role.choices),
        )

    def handle(self, *args, **options):
        email = options["email"]
        role = options["role"]

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f"No user with email {email!r}.")

        old = user.role
        if old == role:
            self.stdout.write(self.style.WARNING(
                f"{email} is already role={role}; nothing to change."
            ))
            return

        user.role = role
        user.save(update_fields=["role"])
        self.stdout.write(self.style.SUCCESS(
            f"{email}: role {old} -> {role}."
        ))
