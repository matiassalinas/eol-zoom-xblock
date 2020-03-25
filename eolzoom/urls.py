from __future__ import absolute_import

from django.conf.urls import url
from django.conf import settings

from .views import zoom_api, new_scheduled_meeting, is_logged_zoom, update_scheduled_meeting

from django.contrib.auth.decorators import login_required

urlpatterns = (
    url(
        r'zoom/api',
        login_required(zoom_api),
        name='zoom_api',
    ),
    url(
        r'zoom/is_logged',
        login_required(is_logged_zoom),
        name='is_logged_zoom',
    ),
    url(
        r'zoom/new_scheduled_meeting$',
        login_required(new_scheduled_meeting),
        name='new_scheduled_meeting',
    ),
    url(
        r'zoom/update_scheduled_meeting$',
        login_required(update_scheduled_meeting),
        name='update_scheduled_meeting',
    ),
)
