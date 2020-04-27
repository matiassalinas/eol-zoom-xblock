# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User

from django.urls import reverse
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings

import requests
import json
import urllib
import base64

from models import EolZoomAuth
from opaque_keys.edx.keys import CourseKey

from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers

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
    redirect = base64.b64decode(request.GET.get('redirect')).decode('utf-8') # decode Studio EOL URL 
    redirect_uri = request.build_absolute_uri().split(
        '&code')[0]  # build uri without code param

    token = get_refresh_token(authorization_code, redirect_uri)
    if 'error' in token:
        logger.error("Error get_refresh_token {}".format(token['error']))
        return HttpResponse(status=400)

    _update_auth(user, token['refresh_token'])

    return HttpResponseRedirect(redirect)


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
    if 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'restricted_access' not in request.POST:
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
    if 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'meeting_id' not in request.POST or 'restricted_access' not in request.POST:
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
        "settings" : {}
    }
    # Restricted access:
    # 1. True: Register users
    # 2. False: Meeting with password
    if request.POST['restricted_access'] == 'true': # string boolean from javascript
        body['settings']['approval_type'] = 1
        body['settings']['registrants_email_notification'] = False
        body['password'] = ''
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    if api_method == 'POST':
        if request.POST['restricted_access'] != 'true':
            body['password'] = _generate_password()
        r = requests.post(
            url,
            data=json.dumps(body),
            headers=headers)  # CREATE
        if r.status_code == 201:
            data = r.json()
            # issue: start_url is giving a unique url to start the meeting (anybody with this url start the meeting with the same username)
            start_url = create_start_url(data['id'])
            response = {
                'meeting_id': data['id'],
                #'start_url': data['start_url'],
                'start_url' : start_url,
                'join_url': data['join_url'],
                'meeting_password': data['password']
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


def start_meeting(request):
    """
        Start a meeting with registrants (only hoster can do)
    """
    # check method and params
    if request.method != "GET":
        return HttpResponse(status=400)
    if 'code' not in request.GET or 'data' not in request.GET:
        return HttpResponse(status=400)

    user = request.user
    authorization_code = request.GET.get('code')
    data = base64.b64decode(request.GET.get('data')) # data with meeting_id and course_id
    args = json.loads(data)
    redirect_uri = request.build_absolute_uri().split(
        '&code')[0]  # build uri without code param
    token = get_refresh_token(authorization_code, redirect_uri)
    if 'error' in token:
        logger.error("Error get_refresh_token {}".format(token['error']))
        return HttpResponse(status=400)
    _update_auth(user, token['refresh_token'])
    # register enrolled students 
    if meeting_registrant(request.user, args['meeting_id'], args['course_id'], token['refresh_token']):
        return HttpResponseRedirect(create_start_url(args['meeting_id']))
    else: 
        return HttpResponse(status=400)

def meeting_registrant(user_meeting, meeting_id, course_id, refresh_token):
    """
        Get all enrolled students, create meeting registrant and approve
    """
    students = get_students(user_meeting, course_id)
    students_registrant = [] # List of students registrant
    platform_name = configuration_helpers.get_value(
        'PLATFORM_NAME', settings.PLATFORM_NAME).encode('utf-8').upper()
    for student in students:
        # Student name at Zoom == 'profile_name'+' platform_name'
        student_info = {
            'email' : student.email,
            'first_name' : student.profile.name,
            'last_name' : platform_name
        }
        data = get_meeting_registrant(meeting_id, user_meeting, student_info)
        if 'registrant_id' in data and 'error' not in data:
            students_registrant.append({
                'id' : data['registrant_id'],
                'email' : student_info['email']
            })
    # Approve all registrant student status
    status = set_registrant_status(meeting_id, user_meeting, students_registrant)
    return True if 'error' not in status else False

def get_students(user, course_id):
    """
        Get all students enrolled to course (without meeting host)
    """
    course_key = CourseKey.from_string(course_id)
    students = User.objects.filter(
        courseenrollment__course_id=course_key,
        courseenrollment__is_active=1
    ).exclude(id=user.id)
    return students

def get_meeting_registrant(meeting_id, user, student):
    """
        Create a meeting registrant (without approve) for specific student
    """
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user, refresh_token)
    if 'error' in token:
        logger.error("Error get_access_token {}".format(token['error']))
        return {
            'error': 'Error get_access_token'
        }
    access_token = token['access_token']
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    url = "https://api.zoom.us/v2/meetings/{}/registrants".format(meeting_id)
    r = requests.post(
        url,
        data=json.dumps(student),
        headers=headers)
    if r.status_code != 201:
        logger.error('Registration fail {}'.format(r.text))
        return {
            'error': 'Registration fail'
        }
    return r.json()

def set_registrant_status(meeting_id, user, registrants):
    """
        Set registrant status to 'approve' for a list of student (registrants)
    """
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user, refresh_token)
    if 'error' in token:
        logger.error("Error get_access_token {}".format(token['error']))
        return {
            'error': 'Error get_access_token'
        }
    access_token = token['access_token']
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    body = {
        'action' : 'approve',
        'registrants' : registrants
    }
    url = "https://api.zoom.us/v2/meetings/{}/registrants/status".format(meeting_id)
    r = requests.put(
        url,
        data=json.dumps(body),
        headers=headers)
    if r.status_code != 204:
        logger.error('Set registrant status fail {}'.format(r.status_code))
        return {
            'error': 'Set registrant status fail'
        }
    return {'success': 'approved'}

def create_start_url(meeting_id):
    """ Create start_url with Zoom Domain and meeting ID """
    return "{}s/{}".format(settings.EOLZOOM_DOMAIN, meeting_id)