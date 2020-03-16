# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User

from django.urls import reverse
from django.http import HttpResponse
from django.conf import settings

import requests
import json
import urllib

import logging
logger = logging.getLogger(__name__)

def zoom_api(request):
    # check method and params
    if request.method != "GET":
        return HttpResponse(status=400)
    if 'code' not in request.GET or 'redirect' not in request.GET:
        return HttpResponse(status=400)

    user = request.user
    authorization_code = request.GET.get('code')
    redirect = request.GET.get('redirect')
    redirect_uri = request.build_absolute_uri().split('&code')[0] # without code param
    data = request_access_token(authorization_code, redirect_uri)
    if 'error' in data:
        logger.error("ERROR " + data['error']) # invalid request
        return HttpResponse(status=400)
    #refresh_token = data['refresh_token']
    user = get_user_with_access_token('dsa')
    if 'code' in user:
        logger.error("ERROR %d" %(user['code']))
        return HttpResponse(status=400)

    return HttpResponse(status=200)

def request_access_token(authorization_code, redirect_uri):
    """
        Request Access Token
    """
    params = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri' : redirect_uri
    }
    url = 'https://zoom.us/oauth/token?{}'.format(urllib.urlencode(params))
    headers = {
        'Authorization' : 'Basic {}'.format(settings.EOLZOOM_AUTHORIZATION)
    }
    r = requests.post(url, headers=headers)
    return r.json()

def get_user_with_access_token(access_token):
    """
        Using an Access Token to get User profile
    """
    logger.warning(access_token)
    headers = {
        'Authorization' : 'Bearer  {}'.format(access_token)
    }
    url = 'https://api.zoom.us/v2/users/me'
    r = requests.get(url, headers=headers)
    data = r.json()
    logger.warning(data)
    return data