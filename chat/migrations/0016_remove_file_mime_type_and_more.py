# Generated by Django 5.0.1 on 2025-06-10 09:09

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0015_remove_message_duration_remove_message_file_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='file',
            name='mime_type',
        ),
        migrations.AddIndex(
            model_name='file',
            index=models.Index(fields=['file_name'], name='chat_file_file_na_897679_idx'),
        ),
    ]
