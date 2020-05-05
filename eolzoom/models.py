# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class EolZoomAuth(models.Model):
    """
        Model with user Zoom refresh token
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="eolzoom_user")
    zoom_refresh_token = models.TextField()


class EolZoomRegistrant(models.Model):
    """
        Model with students join url
    """
    class Meta:
        index_together = [
            ["meeting_id", "email"],
        ]
        unique_together = [
            ["meeting_id", "email"],
        ]
    meeting_id = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    join_url = models.TextField()

    def __str__(self):
        return '(%s) %s -> %s' % (self.meeting_id, self.email, self.join_url)
