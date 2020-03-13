from __future__ import absolute_import

from django.conf.urls import url
from django.conf import settings

from .views import zoom_api

from django.contrib.auth.decorators import login_required

urlpatterns = (
    url(
        r'zoom/api',
        login_required(zoom_api),
        name='zoom_api',
    ),
)