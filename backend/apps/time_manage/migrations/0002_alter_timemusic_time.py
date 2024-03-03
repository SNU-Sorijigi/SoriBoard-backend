# Generated by Django 5.0.2 on 2024-03-03 05:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("time_manage", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="timemusic",
            name="time",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timeplaylist",
                to="time_manage.timeinfo",
            ),
        ),
    ]