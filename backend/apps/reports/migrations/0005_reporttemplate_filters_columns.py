from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reports", "0004_customreportdatasource_reportcategory_and_more")]

    operations = [
        migrations.AddField(model_name="reporttemplate", name="filters", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="reporttemplate", name="columns", field=models.JSONField(blank=True, default=list)),
    ]
