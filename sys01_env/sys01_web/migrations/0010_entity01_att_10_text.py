# Generated by Django 3.2.7 on 2021-09-08 18:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sys01_web', '0009_entity01_att_9_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='entity01',
            name='att_10_text',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
