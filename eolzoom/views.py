# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User

from django.urls import reverse
from django.http import HttpResponse


import logging
logger = logging.getLogger(__name__)

def zoom_api(request):
    logger.warning("API OK")
    return HttpResponse(status=200)