# -*- coding: utf-8 -*-


from django.contrib.auth.models import User

from django.urls import reverse
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings

import requests
import json
import urllib.request
import urllib.parse
import urllib.error
import base64
from django.views.generic.base import View
from celery import task
import time
import threading

from lms.djangoapps.instructor_task.tasks_base import BaseInstructorTask
from lms.djangoapps.instructor_task.api_helper import submit_task
from lms.djangoapps.instructor_task.api_helper import AlreadyRunningError
from lms.djangoapps.instructor_task.tasks_helper.runner import run_main_task
from functools import partial
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils.translation import ugettext_noop
from django.shortcuts import render
from .email_tasks import meeting_start_email
from .models import EolZoomAuth, EolZoomRegistrant, EolGoogleAuth, EolZoomMappingUserMeet
from opaque_keys.edx.keys import CourseKey, UsageKey
from opaque_keys import InvalidKeyError
from six import text_type

from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers

import httplib2
import os
import sys
from datetime import datetime as dt
import datetime
import random
import string

import logging
logger = logging.getLogger(__name__)


MAX_REGISTRANT_STATUS = 30  # Max possible (API)


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
    redirect = base64.b64decode(request.GET.get('redirect')).decode(
        'utf-8')  # decode Studio EOL URL
    redirect_uri = request.build_absolute_uri().split(
        '&code')[0]  # build uri without code param
    #redirect_uri = redirect_uri.replace('http', 'https')
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
    if 'email_notification' not in request.POST or 'block_id' not in request.POST or 'course_id' not in request.POST or 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'restricted_access' not in request.POST or 'google_access' not in request.POST:
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
    if 'email_notification' not in request.POST or 'block_id' not in request.POST or 'course_id' not in request.POST or 'display_name' not in request.POST or 'description' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'meeting_id' not in request.POST or 'restricted_access' not in request.POST or 'google_access' not in request.POST:
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
    try:
        course_id = CourseKey.from_string(request.POST['course_id'])
        block_id = UsageKey.from_string(request.POST['block_id'])
    except InvalidKeyError:
        logger.error("EolZoom: Error with course_id or usage_key, course_id {}, usage_key: {}".format(request.POST['course_id'], request.POST['block_id']))
        return HttpResponse(status=400)
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
        "settings": {
            'use_pmi': False,  # Use Personal Meeting ID: False
        }
    }
    # Restricted access:
    # 1. True: Register users
    # 2. False: Meeting with password
    if request.POST['restricted_access'] == 'true':  # string boolean from javascript
        body['settings']['approval_type'] = 1  # Manually Approve (registrants)
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
            # issue: start_url is giving a unique url to start the meeting
            # (anybody with this url start the meeting with the same username)
            start_url = create_start_url(data['id'])
            response = {
                'meeting_id': data['id'],
                #'start_url': data['start_url'],
                'start_url': start_url,
                'join_url': data['join_url'],
                'meeting_password': body['password']
            }
            google_access = request.POST['google_access'] == 'true'
            EolZoomMappingUserMeet.objects.create(
                meeting_id=data['id'], 
                user=user, 
                title=topic, 
                is_enabled=google_access,
                course_key=course_id,
                restricted_access=request.POST['restricted_access'] == 'true',
                email_notification=request.POST['email_notification'] == 'true',
                usage_key=block_id
                )
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
            google_access = request.POST['google_access'] == 'true'
            EolZoomMappingUserMeet.objects.update_or_create(
                meeting_id=meeting_id, user=user,
                defaults={
                    'title': topic, 
                    'is_enabled': google_access,
                    'course_key': course_id,
                    'restricted_access': request.POST['restricted_access'] == 'true',
                    'email_notification': request.POST['email_notification'] == 'true',
                    'usage_key': block_id
                    })
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
    url = 'https://zoom.us/oauth/token?{}'.format(
        urllib.parse.urlencode(params))
    headers = {
        'Authorization': 'Basic {}'.format(settings.EOLZOOM_AUTHORIZATION)
    }
    r = requests.post(url, headers=headers)
    try:
        token = r.json()
        if 'error' not in token:
            _update_auth(user, token['refresh_token'])  # Update refresh_token
        return token
    except BaseException:
        return {'error': 'json response error'}


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
    url = 'https://zoom.us/oauth/token?{}'.format(
        urllib.parse.urlencode(params))
    headers = {
        'Authorization': 'Basic {}'.format(settings.EOLZOOM_AUTHORIZATION)
    }
    r = requests.post(url, headers=headers)
    try:
        return r.json()
    except BaseException:
        return {'error': 'json response error'}


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
    if request.user.is_anonymous:
        logger.error("EolZoom: User is Anonymous")
        return HttpResponse(status=400)
    if 'code' not in request.GET or 'data' not in request.GET:
        return HttpResponse(status=400)

    user = request.user
    authorization_code = request.GET.get('code')
    # data with meeting_id and course_id (BASE64)
    data = base64.b64decode(request.GET.get('data'))
    args = json.loads(data.decode("utf-8"))
    aux = ['block_id', 'course_id', 'meeting_id', 'restricted_access', 'email_notification']
    if not all([x in args for x in aux]):
        logger.error("EolZoom: Error with data: {}".format(args))
        return HttpResponse(status=400)
    try:
        usage_key = UsageKey.from_string(args['block_id'])
        course_key = CourseKey.from_string(args['course_id'])
    except InvalidKeyError:
        logger.error("EolZoom: Error with course_id or usage_key, data: {}".format(args))
        return HttpResponse(status=400)
    if type(args['restricted_access']) is not bool or type(args['email_notification']) is not bool:
        logger.error("EolZoom: Error with data(restricted_access or email_notification): {}".format(args))
        return HttpResponse(status=400)
    try:
        meeting_id = args['meeting_id']
        zoom_mapp = EolZoomMappingUserMeet.objects.get(meeting_id=meeting_id)
        if user != zoom_mapp.user:
            logger.error("EolZoom: Error in start_meeting, request.user != user_model.user, request.user: {}, user_model.user: {}".format(user, zoom_mapp.user))
            return HttpResponse(status=400)
        zoom_mapp.course_key = usage_key.course_key
        zoom_mapp.restricted_access = args['restricted_access']
        zoom_mapp.email_notification = args['email_notification']
        zoom_mapp.usage_key = usage_key
        zoom_mapp.save()
    except EolZoomMappingUserMeet.DoesNotExist:
        logger.error("EolZoom: Error with EolZoomMappingUserMeet dont exists, meeting_id: {}".format(meeting_id))
        return HttpResponse(status=400)
    redirect_uri = request.build_absolute_uri().split(
        '&code')[0]  # build uri without code param
    #redirect_uri = redirect_uri.replace('http', 'https')
    token = get_refresh_token(authorization_code, redirect_uri)
    if 'error' in token:
        logger.error("Error get_refresh_token {}".format(token['error']))
        return HttpResponse(status=400)
    _update_auth(user, token['refresh_token'])

    return HttpResponseRedirect(create_start_url(args['meeting_id']))

@transaction.non_atomic_requests
def event_zoom(request):
    """
        -Start a meeting with registrants (only hoster can do)
        -Start a meeting WITHOUT registrants
            It will send an email to all enrolled students and redirect the meeting host to Zoom
        -Start livestreams in youtube if youtube livestrem is enabled
    """
    from .utils_youtube import check_event_zoom_params, start_live_youtube
    if not check_event_zoom_params(request):
        return HttpResponse(status=400)
    data = json.loads(request.body.decode())
    id_meet = data['payload']['object']['id']
    if data['event'] == "meeting.started":
        try:
            access_token = None
            user_model = EolZoomMappingUserMeet.objects.get(meeting_id=id_meet)
            if user_model.usage_key is None:
                logger.error("EolZoom - user_model(EolZoomMappingUserMeet) is not up to date, meeting_id: {}".format(id_meet))
                return HttpResponse(status=400)
            user = user_model.user
            request.user = user_model.user
            if user_model.restricted_access or user_model.is_enabled:
                refresh_token = _get_refresh_token(user)
                token = get_access_token(user, refresh_token)
                if 'error' in token:
                    logger.error("EolZoom - Error get_access_token {}, user: {}, meet_id: {}".format(token['error'],user, id_meet))
                    return HttpResponse(status=400)
                access_token = token['access_token']
            try:
                if user_model.restricted_access:
                    start_meeting_event(request, user, id_meet, str(user_model.course_key), str(user_model.usage_key), access_token, user_model.email_notification)
                else:
                    start_public_meeting_event(user, str(user_model.usage_key), user_model.email_notification, id_meet)
            except Exception as e:
                logger.error("EolZoom - Error in start_meeting_event or start_public_meeting_event, user_model {}, exception: {}".format(user_model, str(e)))
                return HttpResponse(status=400)
            if user_model.is_enabled:
                response = start_live_youtube(user_model, access_token)
                if response is None or response['live'] != 'ok':
                    return HttpResponse(status=400)
            else:
                logger.info("User {} dont have enabled youtube livestream in Xblock, meeting_id: {}".format(user_model.user, user_model.meeting_id))
            return HttpResponse(status=200)
        except EolZoomMappingUserMeet.DoesNotExist:
            logger.error("EolZoom - Dont exists mapping user-meeting, Meeting {}".format(id_meet))
            return HttpResponse(status=400)
    logger.error("EolZoom - Event is not Started, event: {}, id_meeting: {}".format(data['event'], id_meet))
    return HttpResponse(status=400)

def start_meeting_event(request, user, meeting_id, course_id, block_id, access_token, email_notification):
    """
        Start a meeting with registrants (only hoster can do)
    """
    # Task register meeting users. If already running pass
    try:
        task_register_meeting_users(
            request,
            user,
            meeting_id,
            course_id,
            block_id,
            access_token,
            email_notification)
    except AlreadyRunningError:
        pass

def start_public_meeting(request, email_notification, meeting_id, block_id, restricted_access):
    # check method and params
    if request.method != "GET":
        return HttpResponse(status=400)
    if request.user.is_anonymous:
        logger.error("EolZoom: User is Anonymous")
        return HttpResponse(status=400)
    try:
        usage_key = UsageKey.from_string(block_id)
    except InvalidKeyError:
        logger.error("EolZoom: Error with usage_key: {}".format(block_id))
        return HttpResponse(status=400)
    if email_notification not in ['True', 'False'] or restricted_access not in ['True', 'False']:
        logger.error("EolZoom: Error with restricted_access: {} or email_notification: {}".format(restricted_access, email_notification))
        return HttpResponse(status=400)
    try:
        zoom_mapp = EolZoomMappingUserMeet.objects.get(meeting_id=meeting_id)
        if request.user != zoom_mapp.user:
            logger.error("EolZoom: Error in start_meeting, request.user != user_model.user, request.user: {}, user_model.user: {}".format(request.user, zoom_mapp.user))
            return HttpResponse(status=400)
        zoom_mapp.course_key = usage_key.course_key
        zoom_mapp.restricted_access = restricted_access == 'True'
        zoom_mapp.email_notification = email_notification == 'True'
        zoom_mapp.usage_key = usage_key
        zoom_mapp.save()
    except EolZoomMappingUserMeet.DoesNotExist:
        logger.error("EolZoom: Error with EolZoomMappingUserMeet dont exists, meeting_id: {}".format(meeting_id))
        return HttpResponse(status=400)
    return HttpResponseRedirect(create_start_url(meeting_id))

def start_public_meeting_event(user, block_id, email_notification, meeting_id):
    """
        Start a meeting WITHOUT registrants
        It will send an email to all enrolled students and redirect the meeting host to Zoom
    """
    if email_notification:
        usage_key = UsageKey.from_string(block_id)
        course_id = usage_key.course_key
        enrolled_students = get_students(user, text_type(course_id))
        for student in enrolled_students:
            meeting_start_email.delay(block_id, student.email)

def task_register_meeting_users(request, user_meeting, meeting_id, course_id, block_id, access_token, email_notification):
    """
        Task Configurations
    """
    course_key = CourseKey.from_string(course_id)
    task_type = 'EOL_ZOOM_REGISTER_MEETING_USERS'
    task_class = run_task_register_meeting_users
    task_input = {
        'user_meeting_id': user_meeting.id,
        'meeting_id': meeting_id,
        'course_id': course_id,
        'block_id': block_id,
        'access_token': access_token,
        'email_notification': email_notification}
    task_key = meeting_id
    return submit_task(
        request,
        task_type,
        task_class,
        course_key,
        task_input,
        task_key)


@task(base=BaseInstructorTask, queue='edx.lms.core.high')
def run_task_register_meeting_users(entry_id, xmodule_instance_args):
    """
        Run task at edx.lms.core.high
    """
    action_name = ugettext_noop('generated')
    task_fn = partial(register_meeting_users, xmodule_instance_args)
    return run_main_task(entry_id, task_fn, action_name)


def register_meeting_users(
        _xmodule_instance_args,
        _entry_id,
        course_id,
        task_input,
        action_name):
    """
        Register enrolled students (using Threads) and approve
    """
    user_meeting_id = task_input["user_meeting_id"]
    user_meeting = User.objects.get(id=user_meeting_id)
    meeting_id = task_input["meeting_id"]
    block_id = task_input["block_id"]
    access_token = task_input["access_token"]
    email_notification = task_input["email_notification"]
    enrolled_students = get_students(user_meeting, text_type(course_id))
    threads = []
    for i in range(0, len(enrolled_students), MAX_REGISTRANT_STATUS):
        t = threading.Thread(target=meeting_registrant,
                             args=(user_meeting,
                                   meeting_id,
                                   enrolled_students[i:i + MAX_REGISTRANT_STATUS],
                                   access_token))
        threads.append(t)
        t.start()  # instantiate thread
    for t in threads:
        t.join()  # wait until threads has completed

    # Get join url for all students and submit to model
    registrants = get_join_url(
        user_meeting,
        meeting_id,
        text_type(course_id),
        access_token)
    _submit_join_url(registrants, meeting_id, block_id, email_notification)
    logger.warning("Register Meeting Users Meeting: {}".format(meeting_id))


def _submit_join_url(registrants, meeting_id, block_id, email_notification):
    """
        Create EolZoomRegistrant with student join_url
    """
    for student in registrants:
        # get_or_create for duplicates
        eol_zoom_registrants, created = EolZoomRegistrant.objects.get_or_create(
            meeting_id=meeting_id,
            email=student['email'],
            join_url=student['join_url']
        )
        # send_mail
        if email_notification:
            meeting_start_email.delay(block_id, student['email'])


def get_join_url(user_meeting, meeting_id, course_id, access_token):
    """
        Get registrants with join url (use pagination)
    """
    headers = {
        "Authorization": "Bearer {}".format(access_token)
    }
    page_count = 1
    i = 1
    registrants = []
    while i <= page_count:
        params = {
            'status': 'approved',
            'page_size': 300,  # max 300
            'page_number': i
        }
        url = "https://api.zoom.us/v2/meetings/{}/registrants?{}".format(
            meeting_id, urllib.parse.urlencode(params))
        r = requests.get(
            url,
            headers=headers)
        if r.status_code != 200:
            logger.error('Get Join URL fail {}'.format(r.text))
        else:
            data = r.json()
            page_count = data['page_count']
            registrants.extend(data['registrants'])
        i += 1
    return registrants


def get_student_join_url(request):
    """
        Get meeting join url for a specific student. Check if students is registered or meeting has started
    """
    # check method and params
    if request.method != "GET":
        return HttpResponse(status=400)
    if 'meeting_id' not in request.GET:
        return HttpResponse(status=400)

    user = request.user
    meeting_id = request.GET.get('meeting_id')
    try:
        registrant = EolZoomRegistrant.objects.get(
            email=user.email, meeting_id=meeting_id)
        return JsonResponse({'status': True, 'join_url': registrant.join_url})
    except EolZoomRegistrant.DoesNotExist:
        # IF USER IS NOT REGISTERED, CHECK IF THE MEETING HAS STARTED
        registrants = EolZoomRegistrant.objects.filter(meeting_id=meeting_id)
        if registrants.count() > 0:
            return JsonResponse({'status': False, 'error_type': 'NOT_FOUND'})
        else:
            return JsonResponse({'status': False, 'error_type': 'NOT_STARTED'})


def meeting_registrant(user_meeting, meeting_id, students, access_token):
    """
        Create meeting registrant for a set of students and approve it
    """
    students_registrant = []  # List of students registrant
    platform_name = configuration_helpers.get_value(
        'PLATFORM_NAME', settings.PLATFORM_NAME).encode('utf-8').upper()
    for student in students:
        # Student name at Zoom == 'profile_name'+' platform_name'
        student_info = {
            'email': student.email,
            'first_name': student.profile.name if student.profile.name != '' else student.username,
            'last_name': platform_name.decode('utf-8')}
        data = get_meeting_registrant(
            meeting_id, user_meeting, student_info, access_token)
        if 'registrant_id' in data and 'error' not in data:
            students_registrant.append({
                'id': data['registrant_id'],
                'email': student_info['email']
            })
    # Approve all registrant student status
    status = set_registrant_status(
        meeting_id, user_meeting, students_registrant, access_token)
    if 'error' in status:
        logger.error("Error Meeting Registrant")
        return False
    return True


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


def get_meeting_registrant(
        meeting_id,
        user,
        student,
        access_token,
        rate_limit=0):
    """
        Create a meeting registrant (without approve) for specific student
    """
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
        if r.status_code == 429 and rate_limit < 10:
            """
                When exceed the rate limits allowed for an API request wait one second and retry (max 10 times)
            """
            rate_limit += 1
            logger.warning(
                "[{}] You have reached the maximum per-second rate limit for this API. Retry ({})".format(
                    meeting_id, rate_limit))
            time.sleep(1.)
            return get_meeting_registrant(
                meeting_id, user, student, access_token, rate_limit)
        logger.error('{} Registration fail {}'.format(r.status_code, r.text))
        return {
            'error': 'Registration fail'
        }
    return r.json()


def set_registrant_status(
        meeting_id,
        user,
        registrants,
        access_token,
        rate_limit=0):
    """
        Set registrant status to 'approve' for a list of student (registrants)
    """
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    body = {
        'action': 'approve',
        'registrants': registrants
    }
    url = "https://api.zoom.us/v2/meetings/{}/registrants/status".format(
        meeting_id)
    r = requests.put(
        url,
        data=json.dumps(body),
        headers=headers)
    if r.status_code != 204:
        if r.status_code == 429 and rate_limit < 10:
            """
                When exceed the rate limits allowed for an API request wait one second and retry (max 10 times)
            """
            rate_limit += 1
            logger.warning(
                "[{}] You have reached the maximum per-second rate limit for this API. Retry ({})".format(
                    meeting_id, rate_limit))
            time.sleep(1.)
            return set_registrant_status(
                meeting_id, user, registrants, rate_limit)
        logger.error('Set registrant status fail {}'.format(r.status_code))
        return {
            'error': 'Set registrant status fail'
        }
    return {'success': 'approved'}


def create_start_url(meeting_id):
    """ Create start_url with Zoom Domain and meeting ID """
    return "{}s/{}".format(settings.EOLZOOM_DOMAIN, meeting_id)
