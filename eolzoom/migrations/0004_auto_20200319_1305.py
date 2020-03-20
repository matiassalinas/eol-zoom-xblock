# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-03-19 13:05
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('eolzoom', '0003_auto_20200319_1249'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eolzoomauth',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eolzoom_user', to=settings.AUTH_USER_MODEL),
        ),
    ]