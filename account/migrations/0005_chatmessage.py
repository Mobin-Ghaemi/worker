from django.db import migrations, models
import django.db.models.deletion
import account.models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0004_employeeprofile_last_seen'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(blank=True)),
                ('file', models.FileField(blank=True, null=True, upload_to=account.models.chat_upload_path)),
                ('file_name', models.CharField(blank=True, max_length=255)),
                ('file_type', models.CharField(
                    choices=[('none', 'متن'), ('image', 'تصویر'), ('file', 'فایل')],
                    default='none', max_length=10,
                )),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sender', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sent_messages',
                    to='auth.user',
                )),
                ('receiver', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='received_messages',
                    to='auth.user',
                )),
            ],
            options={
                'verbose_name': 'پیام چت',
                'verbose_name_plural': 'پیام‌های چت',
                'ordering': ['created_at'],
            },
        ),
    ]
