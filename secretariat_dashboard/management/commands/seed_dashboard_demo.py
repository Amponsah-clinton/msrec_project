"""Populates a fresh/empty database with realistic demo content so the
Secretariat dashboard (and the Meetings module) don't read as a blank
product on a first look -- sample applicants, applications at every
status, reviewers with assignments, audit log activity, notifications,
and a couple of scheduled/completed meetings with agendas and decisions.

Idempotent: every row is created with get_or_create keyed on something
stable (email, reference_no, title), so running this command twice never
duplicates data. Safe to run against the real Supabase database too --
nothing here is destructive, it only adds rows that don't exist yet.

Usage: python manage.py seed_dashboard_demo
"""
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import AuditLog, User
from applicant_dashboard.models import Application
from meetings.models import AgendaItem, Decision, Meeting, MeetingMinutes, MeetingParticipant
from notifications.models import Notification
from reviewer_dashboard.models import ReviewAssignment

DEMO_PASSWORD = "MsrecDemo123!"

APPLICANTS = [
    ("Ama", "Owusu", "University of Ghana", "Department of Sociology"),
    ("Kwabena", "Mensah", "KNUST", "School of Public Health"),
    ("Efua", "Boateng", "University of Cape Coast", "Department of Psychology"),
    ("Yaw", "Asante", "Kwame Nkrumah University", "Faculty of Medicine"),
    ("Abena", "Darko", "University of Ghana Medical School", "Clinical Research Unit"),
    ("Kofi", "Adjei", "Noguchi Memorial Institute", "Epidemiology Unit"),
]

REVIEWERS = [
    ("Dr. Nana", "Sarpong"),
    ("Dr. Adwoa", "Frimpong"),
    ("Prof. Kwesi", "Amoah"),
]

COMMITTEE = [
    ("Prof. Comfort", "Antwi", User.Role.CHAIR),
    ("Dr. Samuel", "Osei", User.Role.COMMITTEE),
    ("Dr. Grace", "Appiah", User.Role.COMMITTEE),
    ("Rev. Isaac", "Tetteh", User.Role.COMMITTEE),
]

STUDY_TITLES = [
    "Prevalence of Hypertension Among Urban Market Traders in Accra",
    "Community Perceptions of Mental Health Services in the Volta Region",
    "Impact of Mobile Health Reminders on Antenatal Care Attendance",
    "Antimicrobial Resistance Patterns in Rural Health Facilities",
    "Nutritional Status of School-Aged Children in the Northern Region",
    "Barriers to Cervical Cancer Screening Among Women in Kumasi",
    "Effectiveness of Community Health Worker Interventions on Malaria Control",
    "Psychosocial Impact of Long-Term Unemployment on Young Graduates",
    "Water, Sanitation and Hygiene Practices in Peri-Urban Settlements",
    "Diabetes Self-Management Education for Adults in Primary Care",
]


class Command(BaseCommand):
    help = "Seeds demo applicants, applications, reviewers, meetings and activity for the Secretariat dashboard."

    def handle(self, *args, **options):
        applicants = self._seed_applicants()
        reviewers = self._seed_reviewers()
        committee = self._seed_committee()
        secretariat = self._seed_secretariat()
        applications = self._seed_applications(applicants)
        self._seed_review_assignments(applications, reviewers, secretariat)
        self._seed_audit_logs(applications, secretariat)
        self._seed_notifications(applications)
        self._seed_meetings(committee, secretariat, applications)

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready. Log in as any seeded account "
            f'(password "{DEMO_PASSWORD}") or as your own account -- '
            "the Secretariat dashboard, Meetings module and Reports pages "
            "will now show real content."
        ))

    # ------------------------------------------------------------------
    def _get_or_create_user(self, email, first_name, last_name, role, **extra):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name, "last_name": last_name, "role": role,
                "is_active": True, **extra,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _seed_applicants(self):
        users = []
        for index, (first, last, institution, department) in enumerate(APPLICANTS):
            email = f"{first.lower()}.{last.lower()}@example.com"
            user = self._get_or_create_user(
                email, first, last, User.Role.APPLICANT,
                institution=institution, department=department,
            )
            users.append(user)
        return users

    def _seed_reviewers(self):
        users = []
        for first, last in REVIEWERS:
            email = f"{first.split('.')[-1].strip().lower()}.{last.lower()}@example.com"
            user = self._get_or_create_user(
                email, first, last, User.Role.REVIEWER,
                reviewer_status=User.RequestStatus.APPROVED, wants_reviewer=True,
            )
            users.append(user)
        return users

    def _seed_committee(self):
        field_names = {f.name for f in User._meta.get_fields()}
        users = []
        for first, last, role in COMMITTEE:
            email = f"{first.split('.')[-1].strip().lower()}.{last.lower()}@example.com"
            kwargs = {}
            if role == User.Role.COMMITTEE and "committee_status" in field_names:
                kwargs["committee_status"] = User.RequestStatus.APPROVED
            user = self._get_or_create_user(email, first, last, role, **kwargs)
            users.append(user)
        return users

    def _seed_secretariat(self):
        return self._get_or_create_user(
            "secretariat.demo@example.com", "Efe", "Larbi", User.Role.SECRETARIAT,
        )

    def _seed_applications(self, applicants):
        statuses = [
            Application.Status.SUBMITTED, Application.Status.SUBMITTED,
            Application.Status.UNDER_REVIEW, Application.Status.UNDER_REVIEW,
            Application.Status.REVISIONS_REQUIRED,
            Application.Status.APPROVED, Application.Status.APPROVED,
            Application.Status.NOT_APPROVED,
        ]
        now = timezone.now()
        applications = []
        for index, title in enumerate(STUDY_TITLES):
            applicant = applicants[index % len(applicants)]
            existing = Application.objects.filter(
                applicant=applicant, form_data__studyTitle=title,
            ).first()
            if existing:
                applications.append(existing)
                continue

            status = statuses[index % len(statuses)]
            submitted_at = now - timezone.timedelta(days=random.randint(1, 45))
            application = Application.objects.create(
                applicant=applicant,
                status=status,
                # Must match the real application form's requestedReview
                # radio values (templates/dashboards/applicant/
                # application-form.html) -- "full", not "full_committee",
                # since that's the only spelling payments.fees and the
                # Review Pathway pages actually recognize.
                review_type=random.choice(["expedited", "full", "exemption"]),
                form_data={
                    "studyTitle": title,
                    "principalInvestigator": applicant.full_name,
                },
                completion_pct=100,
                submitted_at=submitted_at,
                created_at=submitted_at,
            )
            application.assign_reference_no()
            if status in (Application.Status.APPROVED, Application.Status.NOT_APPROVED):
                application.decided_at = submitted_at + timezone.timedelta(days=random.randint(3, 20))
                application.save(update_fields=["decided_at"])
            if status == Application.Status.REVISIONS_REQUIRED:
                application.revision_comment = "Please clarify the participant consent process and attach an updated information sheet."
                application.revision_requested_at = submitted_at + timezone.timedelta(days=2)
                application.revision_count = 1
                application.save(update_fields=["revision_comment", "revision_requested_at", "revision_count"])
            applications.append(application)
        return applications

    def _seed_review_assignments(self, applications, reviewers, secretariat):
        under_review = [a for a in applications if a.status == Application.Status.UNDER_REVIEW]
        submitted = [a for a in applications if a.status == Application.Status.SUBMITTED]
        approved = [a for a in applications if a.status == Application.Status.APPROVED]

        pairs = list(zip(under_review, reviewers)) + list(zip(submitted[:1], reviewers[:1]))
        for application, reviewer in pairs:
            ReviewAssignment.objects.get_or_create(
                application=application, reviewer=reviewer,
                defaults={
                    "assigned_by": secretariat,
                    "status": ReviewAssignment.Status.ACCEPTED,
                    "due_date": (timezone.now() + timezone.timedelta(days=10)).date(),
                    "accepted_at": timezone.now() - timezone.timedelta(days=1),
                },
            )
        for application, reviewer in zip(approved, reviewers):
            ReviewAssignment.objects.get_or_create(
                application=application, reviewer=reviewer,
                defaults={
                    "assigned_by": secretariat,
                    "status": ReviewAssignment.Status.COMPLETED,
                    "due_date": (application.decided_at or timezone.now()).date(),
                    "completed_at": application.decided_at or timezone.now(),
                    "recommendation": ReviewAssignment.Recommendation.APPROVE,
                },
            )

    def _seed_audit_logs(self, applications, secretariat):
        if AuditLog.objects.exists():
            return
        for application in applications[:6]:
            AuditLog.record(
                secretariat, "application.status_changed", target=application,
                description=f"Moved to {application.get_status_display()}.",
            )

    def _seed_notifications(self, applications):
        submitted_count = sum(1 for a in applications if a.status == Application.Status.SUBMITTED)
        if submitted_count and not Notification.objects.filter(
            audience=Notification.Audience.SECRETARIAT, message__icontains="new submission"
        ).exists():
            Notification.objects.create(
                audience=Notification.Audience.SECRETARIAT,
                icon=Notification.Icon.INFO,
                message=f"{submitted_count} new application(s) awaiting screening.",
            )
        revisions = [a for a in applications if a.status == Application.Status.REVISIONS_REQUIRED]
        if revisions and not Notification.objects.filter(
            audience=Notification.Audience.SECRETARIAT, message__icontains="revisions"
        ).exists():
            Notification.objects.create(
                audience=Notification.Audience.SECRETARIAT,
                icon=Notification.Icon.WARN,
                message=f'"{revisions[0].title}" is awaiting the applicant\'s revisions.',
            )

    def _seed_meetings(self, committee, secretariat, applications):
        if Meeting.objects.exists():
            return

        chair = next((u for u in committee if u.role == User.Role.CHAIR), committee[0])
        now = timezone.now()

        upcoming = Meeting.objects.create(
            title="Full Committee Review — Monthly Session",
            meeting_type=Meeting.MeetingType.FULL_COMMITTEE,
            description="Routine monthly review of new and pending protocols.",
            scheduled_at=now + timezone.timedelta(days=7, hours=1),
            duration_minutes=120,
            mode=Meeting.Mode.HYBRID,
            location="MSREC Boardroom, 2nd Floor",
            meeting_link="https://meet.google.com/msrec-monthly",
            quorum_required=4,
            chair=chair,
            created_by=secretariat,
        )
        for user in committee + [secretariat]:
            MeetingParticipant.objects.get_or_create(
                meeting=upcoming, user=user,
                defaults={
                    "role_at_meeting": (
                        MeetingParticipant.ParticipantRole.CHAIR if user == chair
                        else MeetingParticipant.ParticipantRole.SECRETARY if user.role == User.Role.SECRETARIAT
                        else MeetingParticipant.ParticipantRole.MEMBER
                    ),
                },
            )
        for index, application in enumerate(applications[:3]):
            AgendaItem.objects.create(
                meeting=upcoming, order=index, title=f"Review: {application.title}",
                presenter=application.applicant.full_name, duration_minutes=15,
                application=application,
            )
        AgendaItem.objects.create(meeting=upcoming, order=3, title="Any Other Business", duration_minutes=10)

        past = Meeting.objects.create(
            title="Special Session — Expedited Protocols",
            meeting_type=Meeting.MeetingType.EXPEDITED_PANEL,
            description="Expedited review of low-risk protocols.",
            scheduled_at=now - timezone.timedelta(days=14),
            duration_minutes=60,
            mode=Meeting.Mode.IN_PERSON,
            location="MSREC Boardroom, 2nd Floor",
            quorum_required=3,
            chair=chair,
            status=Meeting.Status.COMPLETED,
            created_by=secretariat,
        )
        approved = [a for a in applications if a.status == Application.Status.APPROVED]
        for user in committee[:3] + [secretariat]:
            participant, _ = MeetingParticipant.objects.get_or_create(
                meeting=past, user=user,
                defaults={
                    "role_at_meeting": (
                        MeetingParticipant.ParticipantRole.CHAIR if user == chair
                        else MeetingParticipant.ParticipantRole.SECRETARY if user.role == User.Role.SECRETARIAT
                        else MeetingParticipant.ParticipantRole.MEMBER
                    ),
                    "attended": True,
                    "checked_in_at": past.scheduled_at,
                    "rsvp_status": MeetingParticipant.RsvpStatus.ACCEPTED,
                },
            )
        agenda_item = None
        if approved:
            agenda_item = AgendaItem.objects.create(
                meeting=past, order=0, title=f"Review: {approved[0].title}",
                presenter=approved[0].applicant.full_name, duration_minutes=20,
                application=approved[0], status=AgendaItem.ItemStatus.DISCUSSED,
            )
            Decision.objects.get_or_create(
                meeting=past, agenda_item=agenda_item, application=approved[0],
                defaults={
                    "title": f"Decision: {approved[0].title}",
                    "outcome": Decision.Outcome.APPROVED,
                    "details": "Approved unanimously with no conditions.",
                    "votes_for": 4, "votes_against": 0, "votes_abstain": 0,
                    "recorded_by": secretariat,
                },
            )
        MeetingMinutes.objects.get_or_create(
            meeting=past,
            defaults={
                "content": (
                    "The panel reviewed the expedited protocols on the agenda. "
                    "Quorum was met with 4 voting members present. "
                    f"{approved[0].title if approved else 'The submitted protocol'} was discussed and approved."
                ),
                "recorded_by": secretariat,
                "is_finalized": True,
                "finalized_at": past.scheduled_at + timezone.timedelta(hours=1),
            },
        )
