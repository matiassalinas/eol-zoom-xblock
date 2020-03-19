# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User

from django.urls import reverse
from django.http import HttpResponse
from django.conf import settings

import requests
import json
import urllib

from models import EolZoomAuth

import logging
logger = logging.getLogger(__name__)


def zoom_api(request):
    """
        GET REQUEST
        Generate refresh token from Zoom Api
        Update refresh token in models
        Redirect to Studio EOL
    """
    # check method and params
    if request.method != "GET":
        return HttpResponse(status=400)
    if 'code' not in request.GET or 'redirect' not in request.GET:
        return HttpResponse(status=400)

    user = request.user
    authorization_code = request.GET.get('code')
    redirect = request.GET.get('redirect') # Studio EOL URL
    redirect_uri = request.build_absolute_uri().split('&code')[0] # build uri without code param

    token = get_refresh_token(authorization_code, redirect_uri)
    if 'error' in token:
        logger.error("ERROR " + token['error']) # invalid request
        return HttpResponse(status=400)

    _update_auth(user, token['refresh_token'])

    # TODO: Redirect to Studio
    return HttpResponse(status=200)

def user_profile(request):
    """
        GET REQUEST
        Check if user already have a refresh token in Models
        Get access token from Zoom Api (and update refresh token in Models)
        Get User Profile from Zoom Api
    """
    # check method
    if request.method != "GET":
        return HttpResponse(status=400)

    user = request.user
    refresh_token = _get_refresh_token(user)
    # check if refresh token exists
    if refresh_token:
        token = get_access_token(user,refresh_token)
        if 'error' in token:
            return HttpResponse(status=400)
        access_token = token['access_token']

        user_profile = get_user_profile(access_token)
        if 'code' in user_profile:
            return HttpResponse(status=400)

        # TODO: Send user_profile data
        return HttpResponse(status=200)
    else:
        return HttpResponse(status=401)

def get_access_token(user, refresh_token):
    """
        Get Access Token from Zoom Api
        IMPORTANT: REFRESH TOKEN WILL BE UPDATED.
    """
    params = {
        'grant_type': 'refresh_token',
        'refresh_token':  refresh_token
    }
    url = 'https://zoom.us/oauth/token?{}'.format(urllib.urlencode(params))
    headers = {
        'Authorization' : 'Basic {}'.format(settings.EOLZOOM_AUTHORIZATION)
    }
    r = requests.post(url, headers=headers)
    token = r.json()
    if 'error' not in token:
        _update_auth(user, token['refresh_token']) # Update refresh_token
    return token

def _get_refresh_token(user):
    """
        Get refresh token from models
    """
    try:
        zoom_auth = EolZoomAuth.objects.get(
            user=user
        )
        return zoom_auth.zoom_refresh_token
    except EolZoomAuth.DoesNotExist:
        return None

def get_refresh_token(authorization_code, redirect_uri):
    """
        Get refresh token from Zoom Api
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

def _update_auth(user, refresh_token):
    """
        Update refresh token
    """
    try:
        zoom_auth = EolZoomAuth.objects.get(
            user=user
        )
        zoom_auth.zoom_refresh_token = refresh_token
        zoom_auth.save()
    except EolZoomAuth.DoesNotExist:
        zoom_auth = EolZoomAuth.objects.create(
            user=user,
            zoom_refresh_token=refresh_token
        )

def get_user_profile(access_token):
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
    return data