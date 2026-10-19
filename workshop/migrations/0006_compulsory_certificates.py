from django.db import migrations, models


class Migration(migrations.Migration):
    """Compulsory certificates: a per-workshop switch, plus the record on
    each registration of whether the certificate was compulsory when that
    person signed up."""

    dependencies = [
        ("workshop", "0005_workshop_title_font_size"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="certificate_required",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="workshopregistration",
            name="certificate_required_at_signup",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="workshopregistration",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("not_required", "Nothing to pay"),
                    ("pending", "Payment pending"),
                    ("success", "Paid"),
                    ("failed", "Payment failed"),
                ],
                default="not_required",
                max_length=20,
            ),
        ),
    ]
