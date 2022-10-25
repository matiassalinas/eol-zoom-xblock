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

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import render
from .models import EolZoomAuth, EolZoomRegistrant, EolGoogleAuth, EolZoomMappingUserMeet
from six import text_type
from .views import _get_refresh_token, get_access_token
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers

import httplib2
import os
import sys
from urllib.parse import urlencode
from apiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from datetime import datetime as dt
import datetime

import logging
logger = logging.getLogger(__name__)


def _get_user_credentials_google(user):
    """
        Get user credentials
        Return user_credentials, and permission in youtube
    """
    credentials = None
    data = {'channel': False, 'livestream': False, 'credentials': False, 'livestream_zoom': False}
    try:
        credentials_model = EolGoogleAuth.objects.get(user=user)
        credentials = get_user_credentials_google(
            credentials_model.credentials)
        if credentials is not None:
            credentials_model.credentials = json.dumps(credentials)
            credentials_model.save()
            data["credentials"] = True
        data['channel'] = credentials_model.channel_enabled
        data['livestream'] = credentials_model.livebroadcast_enabled
        data['livestream_zoom'] = credentials_model.custom_live_streaming_service
    except EolGoogleAuth.DoesNotExist:
        pass
    return credentials, data


def get_user_credentials_google(credentials_json):
    """
        Verify if credentials is expiry
    """
    credentials_dict = json.loads(credentials_json)
    # Verificar status credenciales
    if dt.utcnow() >= dt.strptime(
            credentials_dict["expiry"],
            "%Y-%m-%d %H:%M:%S.%f"):
        data = refresh_access_token_oauth2(
            credentials_dict["refresh_token"],
            credentials_dict["token_uri"])
        if data:
            credentials_dict["token"] = data['access_token']
            new_expiry = dt.utcnow() + \
                datetime.timedelta(seconds=data['expires_in'])
            credentials_dict["expiry"] = str(new_expiry)
        else:
            return None
    return credentials_dict


def create_client_config():
    """
        Set the Client Config
    """
    CLIENT_CONFIG = {
        'web': {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'project_id': settings.GOOGLE_PROJECT_ID,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://www.googleapis.com/oauth2/v3/token',
            'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uris': settings.GOOGLE_REDIRECT_URIS,
            'javascript_origins': settings.GOOGLE_JAVASCRIPT_ORIGINS}}
    return CLIENT_CONFIG

def refresh_access_token_oauth2(refresh_token, token_uri):
    """
        Get new google token
    """    
    query = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }
    response = requests.post(token_uri, params=urlencode(query))
    if response.status_code != 200:
        logger.error('Error in refresh token, response: {}'.format(response.text))
        return None
    data = json.loads(response.text)
    return data


def create_live_in_youtube(youtube, start_time, title):
    """
        Create a broadcast, stream in youtube and return a dict with stream params
    """
    try:
        broadcast_id = insert_broadcast(youtube, start_time, title)
        stream_dict = insert_stream(youtube)
        stream_dict['broadcast_id'] = broadcast_id
        bind_broadcast(youtube, broadcast_id, stream_dict["id"])
        return stream_dict
    except HttpError as e:
        # https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/insert#errors
        logger.error(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
        if e.resp.status == 500:
            return False
        return None
    except RefreshError:
        logger.error("An error occurred with token user in create_live_in_youtube()")
        return None


def insert_broadcast(youtube, start_time, title):
    """
        Create a liveBroadcast resource and set its title, scheduled start time,
        and privacy status.
    """
    from django.utils import timezone
    now = timezone.now()
    start_time_utc = dt.fromisoformat(start_time)
    if start_time_utc < now:
        start_time = dt.now().strftime("%Y-%m-%dT%H:%M:%S%z") + '+00:00'

    insert_broadcast_response = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body=dict(
            snippet=dict(
                title=title,
                scheduledStartTime=start_time
            ),
            status=dict(
                privacyStatus="unlisted",
                selfDeclaredMadeForKids=False
            ),
            contentDetails=dict(
                enableAutoStart=True,
                enableAutoStop=True
            )
        )
    ).execute()

    snippet = insert_broadcast_response["snippet"]
    logger.info("Broadcast '{}' with title '{}' was published at '{}'." .format(
        insert_broadcast_response["id"], snippet["title"], snippet["publishedAt"]))
    return insert_broadcast_response["id"]

def datetime_to_utc(start_time):
    #start_time =  yyyy-mm-ddTHH:mm:ss+00:00
    yt_timezone = start_time[-6:]
    aux_dt = dt.strptime(start_time[:-6], "%Y-%m-%dT%H:%M:%S")
    if yt_timezone[0] == '-':
        new_date = aux_dt + datetime.timedelta(hours=int(yt_timezone[1:3]), minutes=int(yt_timezone[4:6]))
    else:
        new_date = aux_dt - datetime.timedelta(hours=int(yt_timezone[1:3]), minutes=int(yt_timezone[4:6]))
    return new_date

def delete_broadcast(youtube, id_live):
    """
        Remove a broadcast in Youtube
    """
    request = youtube.liveBroadcasts().delete(
        id=id_live
    )
    request.execute()

def insert_stream(youtube):
    """
        Create a liveStream resource and set its title, format, and ingestion type.
        This resource describes the content that you are transmitting to YouTube.
    """
    insert_stream_response = youtube.liveStreams().insert(
        part="snippet,cdn",
        body={
          "cdn": {
            "resolution": "720p",
            "ingestionType": "rtmp",
            "frameRate": "30fps"
          },
          "snippet": {
            "title": "New Stream"
          }
        }
    ).execute()

    snippet = insert_stream_response["snippet"]
    stream_dict = {
        "id": insert_stream_response["id"],
        "stream_key": insert_stream_response["cdn"]["ingestionInfo"]["streamName"],
        "stream_server": insert_stream_response["cdn"]["ingestionInfo"]["rtmpsIngestionAddress"]}
    logger.info("Stream '{}' with title '{}' was inserted.".format(
        insert_stream_response["id"], snippet["title"]))
    return stream_dict


def bind_broadcast(youtube, broadcast_id, stream_id):
    """
        Bind the broadcast to the video stream. By doing so, you link the video that
        you will transmit to YouTube to the broadcast that the video is for.
    """
    bind_broadcast_response = youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id
    ).execute()

    logger.info("Broadcast '{}' was bound to stream '{}'." .format(
        bind_broadcast_response["id"],
        bind_broadcast_response["contentDetails"]["boundStreamId"]))


def update_meeting_youtube(user, stream_dict, meet_id, access_token=None):
    """
        Set livestreams youtube in zoom meeting
    """
    if access_token is None:
        refresh_token = _get_refresh_token(user)
        token = get_access_token(user, refresh_token)
        if 'error' in token:
            logger.error("Error get_access_token {}, meet_id: {}, user: {}".format(token['error'], meet_id, user))
            return None
        access_token = token['access_token']
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    url = "https://api.zoom.us/v2/meetings/{}/livestream".format(meet_id)
    body = {
        'stream_url': 'rtmp://a.rtmp.youtube.com/live2',
        "stream_key": stream_dict["stream_key"],
        "page_url": "https://youtu.be/{}".format(stream_dict['broadcast_id'])
    }
    r = requests.patch(
        url,
        data=json.dumps(body),
        headers=headers)
    if r.status_code == 204:
        return True
    else:
        logger.error("Error in update livestream in zoom meeting, meet_id: {}, user: {}".format(meet_id, user))
        return None

def check_event_zoom_params(request):
    """
        Verify if params of zoom event is correct
    """
    if request.method != "POST":
        logger.error("Request method is not POST")
        return False
    if settings.EOLZOOM_EVENT_AUTHORIZATION == "":
        logger.error("Setting EOLZOOM_EVENT_AUTHORIZATION is empty")
        return False
    auth = settings.EOLZOOM_EVENT_AUTHORIZATION
    if request.headers['Authorization'] != auth:
        logger.error("Authorization is incorrect, auth_original: {}, auth_request: {}".format(auth, request.headers['Authorization']))
        return False
    data = json.loads(request.body.decode())
    if 'event' not in data or 'payload' not in data:
        logger.error("Params error, request.body: {}".format(request.body))
        return False
    return True


def start_live_youtube(user_model, access_token):
    """
        Verify status livebroadcast and update status livestream in zoom meeting
    """
    meet_id = user_model.meeting_id
    user = user_model.user
    check_yt = check_status_live_youtube(user_model)
    if check_yt is None:
        return None
    if check_yt == False:
        status = create_new_live(user_model, access_token)
        if status is None:
            return None
    return patch_meeting_zoom_start(user, meet_id, access_token)

def patch_meeting_zoom_start(user, meet_id, access_token):
    """
        Update status livestream in zoom meeting
    """
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    body = {
        "action": "start",
        "settings": {
            "active_speaker_name": False,
            "display_name": "Youtube"
        }
    }
    response = {}
    url = "https://api.zoom.us/v2/meetings/{}/livestream/status".format(
        meet_id)
    r = requests.patch(
        url,
        data=json.dumps(body),
        headers=headers)
    if r.status_code == 204:
        response["live"] = "ok"
    else:
        logger.error("Error to start live with zoom meeting, user: {}, meet_id: {}".format(user, meet_id))
        response["live"] = "error to start live with zoom meeting"
    return response

def create_new_live(user_model, access_token=None):
    """
        Create new livestream in youtube and update stream data in zoom meeting
    """
    youtube = create_youtube_object(user_model.user)
    start_time = str(dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")) + "+00:00"
    title = "{} {}".format(user_model.title, start_time)
    livebroadcast_data = create_live_in_youtube(
        youtube, start_time, title)
    if livebroadcast_data is None or livebroadcast_data is False:
        logger.error("Error in Create live in youtube, user: {}, id_meeting: {}".format(user_model.user, user_model.meeting_id))
        return None
    status = update_meeting_youtube(
        user_model.user,
        livebroadcast_data,
        user_model.meeting_id,
        access_token)
    if status:
        save = save_broadcast_id(user_model.meeting_id, livebroadcast_data['broadcast_id'])
        if save:
            return True
    return None

def check_status_live_youtube(user_model):
    """
        Verify status livestream
        ready: waiting zoom meeting
        complete: live is complete
        created: livebroadcast is created, strem not setted
        live: started livebroadcast
    """
    list_broadcast_id = user_model.broadcast_ids.split(" ")
    youtube = create_youtube_object(user_model.user)
    try:
        response = youtube.liveBroadcasts().list(
            part="id, status",
            id=list_broadcast_id[-1]
        ).execute()
        item = response['items']
        if len(item) > 0:
            if item[0]["status"]['lifeCycleStatus'] == "ready":
                return True
        return False
    except HttpError as e:
        # https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/insert#errors
        logger.error(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
        return None
    except RefreshError:
        logger.error("An error occurred with token user in check_status_live_youtube(), id_broadcast: {}, user:".format(list_broadcast_id[-1], user_model.user))
        return None

def create_youtube_object(user):
    """
        Create Youtube objects with user credentials
    """
    credentials_dict, data = _get_user_credentials_google(user)
    if not data['channel'] or not data['livestream'] or credentials_dict is None:
        logger.error("User dont have youtube permission, user: {}".format(user))
        return None
    import googleapiclient.discovery
    credentials = cretentials_dict_to_object(credentials_dict)
    youtube = googleapiclient.discovery.build(
        'youtube', 'v3', credentials=credentials, cache_discovery=False)
    return youtube


def cretentials_dict_to_object(credentials_dict):
    """
        Return Credentials object
    """
    import google.oauth2.credentials
    credentials = google.oauth2.credentials.Credentials(
        token=credentials_dict["token"],
        refresh_token=credentials_dict["refresh_token"],
        token_uri=credentials_dict["token_uri"],
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=credentials_dict["scopes"])
    return credentials

def check_permission_youtube(credentials_dict, user):
    """
        Verify if user have channel and live permission in Youtube
    """
    import googleapiclient.discovery
    credentials = cretentials_dict_to_object(credentials_dict)
    data = {'channel': False, 'livestream': False, 'credentials': True, 'livestream_zoom': False}
    youtube = googleapiclient.discovery.build(
        'youtube', 'v3', credentials=credentials, cache_discovery=False)
    data = check_permission_channels(youtube, data)
    data = check_permission_live(youtube, data)
    data = check_permission_live_user_setting(user, data)
    return data

def check_permission_live_user_setting(user, data):
    """
        Verify if user have enabled custom livestream service in zoom setting
    """
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user, refresh_token)
    if 'error' in token:
        logger.error("Error get_access_token {}, user: {}".format(token['error'],user))
        return data
    access_token = token['access_token']
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    params = {
        'login_type': 101
    }
    user_id = 'me'
    url = "https://api.zoom.us/v2/users/{}/settings".format(
        user_id)
    r = requests.get(
        url,
        headers=headers)
    if r.status_code == 200:
        response = json.loads(r.content.decode("utf-8"))
        if response['in_meeting']['custom_live_streaming_service']:
            data['livestream_zoom'] = True
        else:
            logger.error("User dont have enabled custom_live_streaming_service, user: {}, response: {}".format(user, response))
    else:
        logger.error("Error to verify custom_live_streaming_service with zoom api, user: {}, response: {}".format(user, r.content))
    return data

def check_permission_channels(youtube, data):
    """
        Verify if user have channel
    """
    request_ch = youtube.channels().list(
        part="id",
        mine=True
    )
    try:
        channel = request_ch.execute()
        if channel["pageInfo"]['totalResults'] > 0:
            data['channel'] = True
    except HttpError as e:
        logger.debug(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
    except RefreshError:
        data['credentials'] = False
        logger.debug("An error occurred with token user in check_permission_channels()")
    return data


def check_permission_live(youtube, data):
    """
        Verify if user have live permission
        Create and remove a live on Youtube
    """
    try:
        start_time = str(dt.now().strftime("%Y-%m-%dT%H:%M:%S")) + "+00:00"
        id_live = insert_broadcast(youtube, start_time, "EOL - Validate permission")
        delete_broadcast(youtube, id_live)
        data['livestream'] = True
    except HttpError as e:
        logger.debug(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
    except RefreshError:
        data['credentials'] = False
        logger.debug("An error occurred with token user in check_permission_live()")
    return data

def update_live_in_youtube(youtube, start_time, title, id_live):
    """
        Update livestreams youtube with new data
    """
    from django.utils import timezone
    now = timezone.now()
    start_time_utc = dt.fromisoformat(start_time)
    if start_time_utc < now:
        start_time = dt.now().strftime("%Y-%m-%dT%H:%M:%S%z") + '+00:00'
    try:
        request = youtube.liveBroadcasts().update(
            part="id,snippet",
            body={
                "id": id_live,
                "snippet": {
                    "title": title,
                    "scheduledStartTime": start_time
                }
            }
        )
        response = request.execute()
        return response["id"]
    except HttpError as e:
        # https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/insert#errors
        logger.error(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
        return None
    except RefreshError:
        logger.error("An error occurred with token user in update_live_in_youtube(), id_broadcast: {}".format(id_live))
        return None

def save_broadcast_id(meet_id, broadcast_id):
    """
        Add new broadcast_id to EolZoomMappingUserMeet
    """
    try:
        user_model = EolZoomMappingUserMeet.objects.get(meeting_id=meet_id)
        if len(user_model.broadcast_ids) > 241:
            logger.error("User have a lot of broadcast id in one meeting, Meeting {}, user: {}, broadcast_ids: {}, miss broadcast id: {}".format(meet_id, user_model.user, user_model.broadcast_ids, broadcast_id))
            return False
        if user_model.broadcast_ids == "":
            user_model.broadcast_ids = broadcast_id
        else:
            user_model.broadcast_ids = "{} {}".format(user_model.broadcast_ids, broadcast_id)
        user_model.save()
        return True
    except EolZoomMappingUserMeet.DoesNotExist:
        logger.error("Dont exists mapping user-meeting, Meeting {}".format(meet_id))
        return False