# Generated by Django 3.2.6 on 2021-08-20 21:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sys01_web', '0002_entity01_att_2_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='entity01',
            name='att_3_text',
            field=models.CharField(max_length=200, null=True),
        ),
    ]
