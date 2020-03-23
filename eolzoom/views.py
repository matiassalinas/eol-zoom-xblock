# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User

from django.urls import reverse
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings

import requests
import json
import urllib

from models import EolZoomAuth

import logging
logger = logging.getLogger(__name__)

#TODO: Revisar validez de un refresh token


def zoom_api(request):
    """
        GET REQUEST
        Generate refresh token from Zoom Api
        Update refresh token in models
        Redirect to Studio EOL
    """
    # check method and params
    logger.warning("LOGEANDO")
    if request.method != "GET":
        return HttpResponse(status=400)
    if 'code' not in request.GET or 'redirect' not in request.GET:
        return HttpResponse(status=400)
    
    logger.warning("LOGEANDO222")

    user = request.user
    authorization_code = request.GET.get('code')
    redirect = request.GET.get('redirect') # Studio EOL URL
    redirect_uri = request.build_absolute_uri().split('&code')[0] # build uri without code param

    token = get_refresh_token(authorization_code, redirect_uri)
    if 'error' in token:
        return HttpResponse(status=400)

    _update_auth(user, token['refresh_token'])

    logger.warning("REDIRECT " + redirect)
    logger.warning("DECODE " + urllib.unquote(redirect))
    logger.warning("pow(decode,2) " + urllib.unquote(urllib.unquote(redirect)))
    return HttpResponseRedirect(redirect.replace(' ', '+'))

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

        logger.warning(user_profile)
        # TODO: Send user_profile data
        return HttpResponse(status=200)
    else:
        return HttpResponse(status=401)

def is_logged_zoom(request):
    """
        GET REQUEST
        Get if user is logged in zoom
    """
    logger.warning("IS LOGGED ZOOM")
    # check method
    if request.method != "GET":
        return HttpResponse(status=400)
    user = request.user
    is_logged = True if _get_refresh_token(user) != None else False
    return JsonResponse({
        'is_logged' : is_logged
    })

def new_scheluded_meeting(request):
    # check method and params
    if request.method != "POST":
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST:
        return HttpResponse(status=400)
    user = request.user
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user,refresh_token)
    if 'error' in token:
        return HttpResponse(status=400)
    access_token = token['access_token']
    user_id = "me"
    topic = request.POST['display_name']
    ttype = 2
    start_time = '{}T{}:00'.format(request.POST['date'], request.POST['time'])
    duration = request.POST['duration']
    timezone = "America/Santiago"
    agenda = request.POST['description']
    body = {
        "topic"     : topic,
        "type"      : ttype,
        "start_time": start_time,
        "duration"  : duration,
        "timezone"  : timezone,
        "agenda"    : agenda,
    }
    url = "https://api.zoom.us/v2/users/{}/meetings".format(user_id)
    headers = {
        "Authorization" : "Bearer {}".format(access_token),
        "Content-Type"  : "application/json"
    }
    r = requests.post(url, data=json.dumps(body), headers=headers)
    data = r.json()
    logger.warning(body)
    #return HttpResponse(status=201)
    return JsonResponse({
        'meeting_id' : data['id']
    })


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
    logger.warning(token)
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
    headers = {
        'Authorization' : 'Bearer  {}'.format(access_token)
    }
    url = 'https://api.zoom.us/v2/users/me'
    r = requests.get(url, headers=headers)
    data = r.json()
    return data