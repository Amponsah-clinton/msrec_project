"""Seeds the 13 Board/Committee/Secretariat members that used to be
hardcoded directly in templates/pages/board_committee.html, so switching
that page over to reading from the database doesn't blank it out --
they're now ordinary rows an admin can edit, reorder, replace the photo
of, or delete from admin_dashboard's Board & Committee page."""
from django.db import migrations

MEMBERS = [
    # (full_name, role_title, tag, group, display_order)
    ("Prof. Kojo Antwi-Boateng", "Board Chairperson", "Governance & Higher Education", "board", 0),
    ("Mrs. Efua Darko-Mensah", "Board Vice-Chair", "Finance & Administration", "board", 1),
    ("Mr. Yaw Sarpong", "Independent Board Member", "Legal & Compliance", "board", 2),

    ("Prof. Michael Osei-Frimpong", "Committee Chairperson", "Health & Biomedical Science", "committee", 0),
    ("Dr. Abena Fosu-Ackah", "Committee Vice-Chairperson", "Social & Behavioral Science", "committee", 1),
    ("Dr. Samuel Nkrumah-Boateng", "Committee Member", "Methodology & Biostatistics", "committee", 2),
    ("Barr. Comfort Aidoo", "Committee Member", "Law, Data Protection & Privacy", "committee", 3),
    ("Rev. Dr. Isaac Amponsah", "Committee Member", "Ethics & Bioethics", "committee", 4),
    ("Madam Grace Tetteh", "Committee Member", "Lay / Community Representative", "committee", 5),
    ("Dr. Elorm Kudjordji", "Independent External Member", "Data Science & AI", "committee", 6),

    ("Ms. Adjoa Boakye", "Head of Secretariat / Ethics Officer", "Secretariat", "secretariat", 0),
    ("Mr. Nathaniel Quarshie", "Administrative & Records Coordinator", "Secretariat", "secretariat", 1),
    ("Ms. Priscilla Owusu-Ansah", "Applicant Support Officer", "Secretariat", "secretariat", 2),
]


def seed_members(apps, schema_editor):
    GovernanceMember = apps.get_model("pages", "GovernanceMember")
    if GovernanceMember.objects.exists():
        return
    GovernanceMember.objects.bulk_create([
        GovernanceMember(
            full_name=name, role_title=role, tag=tag, group=group, display_order=order,
        )
        for name, role, tag, group, order in MEMBERS
    ])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0002_governancemember"),
    ]

    operations = [
        migrations.RunPython(seed_members, noop_reverse),
    ]
