# Generated by Django 5.0.1 on 2025-06-18 07:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0005_chatmessage_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='assistantmemory',
            name='message_history',
            field=models.JSONField(default=list),
        ),
    ]
