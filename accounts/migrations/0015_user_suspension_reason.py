from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_user_suspended_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='suspension_kind',
            field=models.CharField(blank=True, choices=[('suspend', 'Suspended'), ('ban', 'Banned')], max_length=10),
        ),
        migrations.AddField(
            model_name='user',
            name='suspension_reason',
            field=models.TextField(blank=True),
        ),
    ]
