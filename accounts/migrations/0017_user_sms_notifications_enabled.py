from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_user_suspended_until'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='sms_notifications_enabled',
            field=models.BooleanField(default=True),
        ),
    ]
