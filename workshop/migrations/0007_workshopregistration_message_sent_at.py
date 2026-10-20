from django.db import migrations, models


class Migration(migrations.Migration):
    """When staff last sent a registrant a custom email or SMS from the
    workshop's Registrations tab, so the list shows who has been messaged."""

    dependencies = [
        ("workshop", "0006_compulsory_certificates"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshopregistration",
            name="message_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
