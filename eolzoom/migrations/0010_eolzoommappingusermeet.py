# Generated by Django 2.2.13 on 2020-08-13 20:04

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('eolzoom', '0009_auto_20200812_2114'),
    ]

    operations = [
        migrations.CreateModel(
            name='EolZoomMappingUserMeet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('meeting_id', models.CharField(max_length=50, unique=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('meeting_id', 'user')},
                'index_together': {('meeting_id', 'user')},
            },
        ),
    ]