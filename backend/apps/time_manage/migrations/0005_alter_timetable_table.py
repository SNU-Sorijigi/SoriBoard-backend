# Generated by Django 4.2.4 on 2024-06-30 05:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("time_manage", "0004_timetable_timetableunit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="timetable",
            name="table",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
