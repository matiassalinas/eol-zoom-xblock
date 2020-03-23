from __future__ import absolute_import

from django.conf.urls import url
from django.conf import settings

from .views import zoom_api, user_profile, new_scheluded_meeting, is_logged_zoom

from django.contrib.auth.decorators import login_required

urlpatterns = (
    url(
        r'zoom/api',
        login_required(zoom_api),
        name='zoom_api',
    ),
    url(
        r'zoom/user_profile$',
        login_required(user_profile),
        name='user_profile',
    ),
    url(
        r'zoom/is_logged',
        login_required(is_logged_zoom),
        name='is_logged_zoom',
    ),
    url(
        r'zoom/new_scheluded_meeting$',
        login_required(new_scheluded_meeting),
        name='new_scheluded_meeting',
    ),
)