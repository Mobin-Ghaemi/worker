from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0008_position_employeeprofile_position'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='allowed_pages',
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name='صفحات مجاز',
                help_text='لیست نام URL‌هایی که این سمت مجاز به دسترسی است. خالی = همه صفحات.',
            ),
        ),
    ]
