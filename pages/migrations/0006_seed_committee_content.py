"""Seeds a starter set of committee meetings and policy documents so the
Reviewer dashboard's Upcoming Meetings / Meeting Documents / Policies &
Guidance pages aren't blank on first load -- ordinary rows from here on,
manageable (including file uploads) from Django admin at /admin/."""
from datetime import timedelta

from django.db import migrations
from django.utils import timezone

MEETINGS = [
    # (title, days_from_now, location, meeting_link, agenda)
    (
        "Full Committee Review Meeting - October",
        14, "MSREC Boardroom, Metascholar House",
        "https://meet.google.com/msrec-full-review",
        "1. Review of new full-committee applications\n"
        "2. Continuing review reports\n"
        "3. Adverse event summaries\n"
        "4. Any other business",
    ),
    (
        "Expedited Review Panel - November",
        35, "", "https://meet.google.com/msrec-expedited-panel",
        "1. Expedited applications since last panel\n"
        "2. Minor amendments for ratification",
    ),
]

POLICIES = [
    # (category, title, description, version, display_order)
    (
        "sop", "SOP 01: Application Intake & Screening",
        "Standard operating procedure for how new applications are logged, "
        "screened for completeness and routed to a review pathway.",
        "v2.1", 0,
    ),
    (
        "sop", "SOP 04: Conflict of Interest Management",
        "Procedure for declaring, recording and managing conflicts of "
        "interest for reviewers and committee members.",
        "v1.3", 1,
    ),
    (
        "guidance", "Reviewer Handbook",
        "A practical walkthrough of the reviewer's role, timelines, and "
        "how to use the Ethical Review Assessment Form.",
        "v3.0", 0,
    ),
    (
        "guidance", "Assessing Risk in Vulnerable Populations",
        "Guidance notes for evaluating studies involving children, "
        "prisoners, or other vulnerable participant groups.",
        "v1.0", 1,
    ),
    (
        "ethics", "MSREC Code of Research Ethics",
        "The Committee's foundational ethics code, aligned to national "
        "and international human-subjects research standards.",
        "v4.2", 0,
    ),
    (
        "ethics", "Informed Consent Guidelines",
        "Requirements and model language for informed consent documents "
        "across study types.",
        "v2.0", 1,
    ),
]


def seed_content(apps, schema_editor):
    CommitteeMeeting = apps.get_model("pages", "CommitteeMeeting")
    PolicyDocument = apps.get_model("pages", "PolicyDocument")
    now = timezone.now()

    if not CommitteeMeeting.objects.exists():
        CommitteeMeeting.objects.bulk_create([
            CommitteeMeeting(
                title=title, scheduled_at=now + timedelta(days=days),
                location=location, meeting_link=link, agenda=agenda,
            )
            for title, days, location, link, agenda in MEETINGS
        ])

    if not PolicyDocument.objects.exists():
        PolicyDocument.objects.bulk_create([
            PolicyDocument(
                category=category, title=title, description=description,
                version=version, display_order=order,
            )
            for category, title, description, version, order in POLICIES
        ])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0005_committeemeeting_policydocument_meetingdocument"),
    ]

    operations = [
        migrations.RunPython(seed_content, noop_reverse),
    ]
