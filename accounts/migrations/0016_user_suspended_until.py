from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_user_suspension_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='suspended_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
