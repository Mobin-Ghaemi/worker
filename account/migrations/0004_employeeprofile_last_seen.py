from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0003_add_sitesettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='last_seen',
            field=models.DateTimeField(blank=True, null=True, verbose_name='آخرین فعالیت'),
        ),
    ]
