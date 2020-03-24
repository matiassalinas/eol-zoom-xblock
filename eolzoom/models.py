# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class EolZoomAuth(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="eolzoom_user")
    zoom_refresh_token = models.TextField()
