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

import random
import string

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
    redirect = request.GET.get('redirect')  # Studio EOL URL
    redirect_uri = request.build_absolute_uri().split(
        '&code')[0]  # build uri without code param

    token = get_refresh_token(authorization_code, redirect_uri)
    if 'error' in token:
        logger.error("Error get_refresh_token {}".format(token['error']))
        return HttpResponse(status=400)

    _update_auth(user, token['refresh_token'])

    return HttpResponseRedirect(redirect.replace(' ', '+'))


def is_logged_zoom(request):
    """
        GET REQUEST
        Get if user is logged in zoom and profile data
    """
    # check method
    if request.method != "GET":
        return HttpResponse(status=400)
    user = request.user
    user_profile = _get_user_profile(user)
    return JsonResponse(user_profile, safe=False)


def new_scheduled_meeting(request):
    """
        Generate new scheduled meeting
        https://marketplace.zoom.us/docs/api-reference/zoom-api/meetings/meetingcreate
    """
    # check method and params
    if request.method != "POST":
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST:
        return HttpResponse(status=400)

    user_id = 'me'
    url = "https://api.zoom.us/v2/users/{}/meetings".format(user_id)

    return set_scheduled_meeting(request, url, 'POST')


def update_scheduled_meeting(request):
    """
        Update scheduled meeting already created
    """

    # check method and params
    if request.method != "POST":
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'meeting_id' not in request.POST:
        return HttpResponse(status=400)

    meeting_id = request.POST['meeting_id']
    url = "https://api.zoom.us/v2/meetings/{}".format(meeting_id)

    return set_scheduled_meeting(request, url, 'PATCH')


def set_scheduled_meeting(request, url, api_method):
    """
        Set all attributes and create/update meeting
    """
    user = request.user
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user, refresh_token)
    if 'error' in token:
        logger.error("Error get_access_token {}".format(token['error']))
        return HttpResponse(status=400)
    access_token = token['access_token']
    topic = request.POST['display_name']
    ttype = 2  # Scheluded Meeting
    start_time = '{}T{}:00'.format(
        request.POST['date'],
        request.POST['time'])  # yyyy-mm-ddTHH:mm:ss
    duration = request.POST['duration']
    timezone = "America/Santiago"
    agenda = request.POST['description']
    body = {
        "topic": topic,
        "type": ttype,
        "start_time": start_time,
        "duration": duration,
        "timezone": timezone,
        "agenda": agenda,
    }
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    if api_method == 'POST':
        body['password'] = _generate_password()
        r = requests.post(
            url,
            data=json.dumps(body),
            headers=headers)  # CREATE
        if r.status_code == 201:
            data = r.json()
            response = {
                'meeting_id': data['id'],
                'start_url': data['start_url'],
                'join_url': data['join_url']
            }
        else:
            return HttpResponse(status=r.status_code)
    elif api_method == 'PATCH':
        r = requests.patch(
            url,
            data=json.dumps(body),
            headers=headers)  # UPDATE
        if r.status_code == 204:
            meeting_id = request.POST['meeting_id']
            response = {
                'meeting_id': meeting_id
            }
        else:
            return HttpResponse(status=r.status_code)
    return JsonResponse(response)


def get_access_token(user, refresh_token):
    """
        Get Access Token from Zoom Api
        IMPORTANT: REFRESH TOKEN WILL BE UPDATED.
    """
    params = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    url = 'https://zoom.us/oauth/token?{}'.format(urllib.urlencode(params))
    headers = {
        'Authorization': 'Basic {}'.format(settings.EOLZOOM_AUTHORIZATION)
    }
    r = requests.post(url, headers=headers)
    token = r.json()
    if 'error' not in token:
        _update_auth(user, token['refresh_token'])  # Update refresh_token
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
        'redirect_uri': redirect_uri
    }
    url = 'https://zoom.us/oauth/token?{}'.format(urllib.urlencode(params))
    headers = {
        'Authorization': 'Basic {}'.format(settings.EOLZOOM_AUTHORIZATION)
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


def _get_user_profile(user):
    """
        Get user profile
        Return user_profile
    """
    refresh_token = _get_refresh_token(user)
    # check if refresh token exists
    if refresh_token:
        token = get_access_token(user, refresh_token)
        if 'error' in token:
            logger.error("Error get_access_token {}".format(token['error']))
            return None
        access_token = token['access_token']

        user_profile = get_user_profile(access_token)
        if 'code' in user_profile:
            logger.error(
                "Error get_user_profile {}".format(
                    user_profile['code']))
            return None

        return user_profile
    else:
        logger.warning("Access Token Not Found")
        return None


def get_user_profile(access_token):
    """
        Using an Access Token to get User profile
    """
    headers = {
        'Authorization': 'Bearer  {}'.format(access_token)
    }
    url = 'https://api.zoom.us/v2/users/me'
    r = requests.get(url, headers=headers)
    data = r.json()
    return data


def _generate_password():
    """Generate a random string of letters and digits """
    lettersAndDigits = string.ascii_letters + string.digits
    return ''.join(random.choice(lettersAndDigits) for i in range(10))
