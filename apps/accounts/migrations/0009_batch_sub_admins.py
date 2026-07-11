from django.conf import settings
from django.db import migrations, models


def copy_primary_supervisors(apps, schema_editor):
    Batch = apps.get_model("accounts", "Batch")
    through = Batch.sub_admins.through
    rows = []
    for batch in Batch.objects.exclude(sub_admin_id__isnull=True).only("id", "sub_admin_id"):
        rows.append(through(batch_id=batch.id, user_id=batch.sub_admin_id))
    through.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_alter_batch_number_batch_unique_batch_name_per_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="batch",
            name="sub_admins",
            field=models.ManyToManyField(
                blank=True,
                related_name="managed_batches",
                to=settings.AUTH_USER_MODEL,
                verbose_name="المشرفون",
            ),
        ),
        migrations.RunPython(copy_primary_supervisors, migrations.RunPython.noop),
    ]
