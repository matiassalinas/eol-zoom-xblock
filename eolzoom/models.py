# -*- coding: utf-8 -*-


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

class EolGoogleAuth(models.Model):
    """
        Model with user Google credentials
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="google_user")
    credentials = models.TextField()
    channel_enabled = models.BooleanField(default=False)
    livebroadcast_enabled =models.BooleanField(default=False)

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

class EolZoomMappingUserMeet(models.Model):
    """
        Model with meeting id and host user
    """
    class Meta:
        index_together = [
            ["meeting_id", "user"],
        ]
        unique_together = [
            ["meeting_id", "user"],
        ]
    meeting_id = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return '(%s) -> %s' % (self.user.username, self.meeting_id)