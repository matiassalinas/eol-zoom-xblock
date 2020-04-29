# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-04-28 19:03
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eolzoom', '0004_auto_20200319_1305'),
    ]

    operations = [
        migrations.CreateModel(
            name='EolZoomRegistrants',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('meeting_id', models.CharField(max_length=50)),
                ('email', models.CharField(max_length=100)),
                ('join_url', models.TextField()),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='eolzoomregistrants',
            unique_together=set([('meeting_id', 'email')]),
        ),
        migrations.AlterIndexTogether(
            name='eolzoomregistrants',
            index_together=set([('meeting_id', 'email')]),
        ),
    ]