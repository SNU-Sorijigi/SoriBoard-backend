from django.db import migrations, models


def forwards_copy_timeinfo_users(apps, schema_editor):
    TimeInfo = apps.get_model("time_manage", "TimeInfo")
    for ti in TimeInfo.objects.all():
        user_id = getattr(ti, "user_id", None)
        mentee_id = getattr(ti, "mentee_id", None)
        if user_id:
            ti.users.add(user_id)
        if mentee_id:
            ti.mentees.add(mentee_id)


class Migration(migrations.Migration):

    dependencies = [
        ("time_manage", "0014_remove_timetableunit_mentee_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeinfo",
            name="users",
            field=models.ManyToManyField(
                blank=True, related_name="time", to="time_manage.user"
            ),
        ),
        migrations.AddField(
            model_name="timeinfo",
            name="mentees",
            field=models.ManyToManyField(
                blank=True, related_name="mentee_time", to="time_manage.user"
            ),
        ),
        migrations.RunPython(forwards_copy_timeinfo_users, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="timeinfo",
            name="user",
        ),
        migrations.RemoveField(
            model_name="timeinfo",
            name="mentee",
        ),
    ]
