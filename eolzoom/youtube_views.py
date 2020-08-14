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

from apiclient.errors import HttpError
from google.auth.exceptions import RefreshError
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from datetime import datetime as dt
import datetime

import logging
logger = logging.getLogger(__name__)


def google_is_logged(request):
    """
        GET REQUEST
        Get if user is logged in google and permission data
    """
    # check method
    if request.method != "GET":
        logger.info("Request method is not GET")
        return HttpResponse(status=400)
    user = request.user
    credentials, data = _get_user_credentials_google(user)
    return JsonResponse(data, safe=False)


def _get_user_credentials_google(user):
    """
        Get user credentials
        Return user_credentials, and permission in youtube
    """
    credentials = None
    data = {'channel': False, 'livestream': False, 'credentials': False}
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
    except EolGoogleAuth.DoesNotExist:
        pass
    return credentials, data


def get_user_credentials_google(credentials_json):
    """
        Verify if credentials is expiry
    """
    credentials_dict = json.loads(credentials_json)
    # Verificar status credenciales
    if dt.now() >= dt.strptime(
            credentials_dict["expiry"],
            "%Y-%m-%d %H:%M:%S.%f"):
        data = refresh_access_token_oauth2(
            credentials_dict["refresh_token"],
            credentials_dict["token_uri"])
        if data:
            credentials_dict["token"] = data['access_token']
            new_expiry = dt.now() + \
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


def auth_google(request):
    """
        Set the url to authenticate with google
    """
    if request.method != "GET":
        return HttpResponse(status=400)
    # Client configuration for an OAuth 2.0 web server application
    # (cf. https://developers.google.com/identity/protocols/OAuth2WebServer)
    CLIENT_CONFIG = create_client_config()
    # This scope will allow the application to manage your calendars
    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    # Use the client_secret.json file to identify the application requesting
    # authorization. The client ID (from that file) and access scopes are
    # required.
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=SCOPES)

    # Indicate where the API server will redirect the user after the user completes
    # the authorization flow. The redirect URI is required. The value must exactly
    # match one of the authorized redirect URIs for the OAuth 2.0 client, which you
    # configured in the API Console. If this value doesn't match an authorized URI,
    # you will get a 'redirect_uri_mismatch' error.
    url_aux = request.build_absolute_uri(reverse('callback_google_auth'))
    flow.redirect_uri = url_aux.replace("http://", "https://")
    redirect = request.GET.get('redirect')
    # Generate URL for request to Google's OAuth 2.0 server.
    # Use kwargs to set optional request parameters.
    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server
        # apps.
        access_type='offline',
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes='true',
        # New refresh token
        prompt='consent',
        state=redirect)
    return HttpResponseRedirect(authorization_url)


def callback_google_auth(request):
    """
        Check if params is correct, get user credentials and return the redirect url
    """
    if request.method != "GET":
        logger.info("Request method is not GET")
        return HttpResponse(status=400)
    if 'state' not in request.GET or 'code' not in request.GET or 'scope' not in request.GET:
        logger.error("State, Code or Scope not found in request.GET")
        return HttpResponse(status=400)
    state = request.GET.get('state')
    CLIENT_CONFIG = create_client_config()

    # This scope will allow the application to manage your calendars
    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    # Use the client_secret.json file to identify the application requesting
    # authorization. The client ID (from that file) and access scopes are
    # required.
    try:
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            client_config=CLIENT_CONFIG,
            scopes=SCOPES,
            state=state)
        url_aux = request.build_absolute_uri(reverse('callback_google_auth'))
        flow.redirect_uri = url_aux.replace("http://", "https://")

        url_aux = request.build_absolute_uri()
        authorization_response = url_aux.replace("http://", "https://")
        flow.fetch_token(authorization_response=authorization_response)
        next_url = base64.b64decode(state).decode(
            'utf-8')  # decode Studio EOL URL
        # Store the credentials in the session.
        # ACTION ITEM for developers:
        #     Store user's access and refresh tokens in your data store if
        #     incorporating this code into your real app.
        credentials = flow.credentials
    except InvalidGrantError:
        logger.error(
            "Error with Exchange authorization code for refresh and access tokens")
        return HttpResponse(status=400)
    # Load credentials from the session.
    credentials_dict = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'scopes': credentials.scopes,
        'expiry': str(credentials.expiry)}
    data = check_permission_youtube(credentials_dict)
    credentials_model, created = EolGoogleAuth.objects.update_or_create(
        user=request.user,
        credentials=json.dumps(credentials_dict),
        channel_enabled=data['channel'],
        livebroadcast_enabled=data['livestream'])
    return HttpResponseRedirect(next_url)


def refresh_access_token_oauth2(refresh_token, token_uri):
    """
        Get new google token
    """
    from urllib.parse import urlencode
    query = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }
    response = requests.post(token_uri, params=urlencode(query))
    if response.status_code != 200:
        logger.info('Error in refresh token')
        logger.info(response.text)
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
        logger.info(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
        return None
    except RefreshError:
        logger.info("An error occurred with token user")
        return None


def insert_broadcast(youtube, start_time, title):
    """
        Create a liveBroadcast resource and set its title, scheduled start time,
        and privacy status.
    """
    insert_broadcast_response = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body=dict(
            snippet=dict(
                title=title,
                scheduledStartTime=start_time
            ),
            status=dict(
                privacyStatus="private",
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
        body=dict(
            snippet=dict(
                title="New Stream"
            ),
            cdn=dict(
                format="720p",
                ingestionType="rtmp"
            )
        )
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


def update_meeting_youtube(user, stream_dict, meet_id):
    """
        Set livestreams youtube in zoom meeting
    """
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user, refresh_token)
    if 'error' in token:
        logger.error("Error get_access_token {}".format(token['error']))
        return None
    access_token = token['access_token']
    headers = {
        "Authorization": "Bearer {}".format(access_token),
        "Content-Type": "application/json"
    }
    url = "https://api.zoom.us/v2/meetings/{}/livestream".format(meet_id)
    body = {
        "stream_url": stream_dict["stream_server"],
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
        logger.info("Error in update livestream in zoom meeting")
        return None


def event_zoom_youtube(request):
    """
        Start livestreams in youtube
    """
    if not check_event_zoom_params(request):
        return HttpResponse(status=400)
    data = json.loads(request.body)
    id_meet = data['payload']['object']['id']
    if data['event'] == "meeting.started":
        try:
            user_model = EolZoomMappingUserMeet.objects.get(meeting_id=id_meet)
            response = start_live_youtube(user_model.user, id_meet)
            if response is None or response['live'] != 'ok':
                return HttpResponse(status=400)
            return HttpResponse(status=200)
        except EolZoomMappingUserMeet.DoesNotExist:
            logger.info("Dont exists mappig user-meeting")
            return HttpResponse(status=400)
    logger.info("Event is not Started")
    return HttpResponse(status=400)


def check_event_zoom_params(request):
    """
        Verify if params of zoom event is correct
    """
    if request.method != "POST":
        logger.info("Request method is not POST")
        return False
    auth = "Bearer {}".format(settings.EOLZOOM_AUTHORIZATION)
    if request.headers['Authorization'] != auth:
        logger.info("Authorization is incorrect")
        return False
    data = json.loads(request.body)
    if 'event' not in data or 'payload' not in data:
        logger.info("Params error")
        return False
    return True


def start_live_youtube(user, meet_id):
    """
        Update status livestream in zoom meeting
    """
    refresh_token = _get_refresh_token(user)
    token = get_access_token(user, refresh_token)
    if 'error' in token:
        logger.error("Error get_access_token {}".format(token['error']))
        return None
    access_token = token['access_token']
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
        logger.info("Error to start live with zoom meeting")
        response["live"] = "error to start live with zoom meeting"
    return response


def create_livebroadcast(request):
    """
        Create the livestream in youtube and set stream data in zoom meeting
    """
    response = {'status': 'error'}
    if request.method != "POST":
        logger.info("Request method is not POST")
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'meeting_id' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'restricted_access' not in request.POST:
        logger.info("Params Error")
        return JsonResponse(response, safe=False)

    youtube = create_youtube_object(request.user)
    if youtube is None:
        return JsonResponse(response, safe=False)
    start_time = '{}T{}:00-04:00'.format(
        request.POST['date'],
        request.POST['time'])  # yyyy-mm-ddTHH:mm:ss-04:00

    livebroadcast_data = create_live_in_youtube(
        youtube, start_time, request.POST['display_name'])
    if livebroadcast_data is None:
        logger.info("Error in Create live in youtube")
        return JsonResponse(response, safe=False)
    status = update_meeting_youtube(
        request.user,
        livebroadcast_data,
        request.POST['meeting_id'])
    if status:
        response['status'] = "ok"
        response['id_broadcast'] = livebroadcast_data['broadcast_id']
    logger.info("Error in update livestream in zoom meeting")
    return JsonResponse(response, safe=False)


def create_youtube_object(user):
    """
        Create Youtube objects with user credentials
    """
    credentials_dict, data = _get_user_credentials_google(user)
    if not data['channel'] or not data['livestream'] or credentials_dict is None:
        logger.info("User dont have permission")
        return None

    credentials = cretentials_dict_to_object(credentials_dict)
    youtube = googleapiclient.discovery.build(
        'youtube', 'v3', credentials=credentials, cache_discovery=False)
    return youtube


def cretentials_dict_to_object(credentials_dict):
    """
        Return Credentials object
    """
    credentials = google.oauth2.credentials.Credentials(
        token=credentials_dict["token"],
        refresh_token=credentials_dict["refresh_token"],
        token_uri=credentials_dict["token_uri"],
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=credentials_dict["scopes"])
    return credentials


def youtube_validate(request):
    """
        Verify if user have permission in youtube
    """
    response = {'channel': False, 'livestream': False, 'credentials': False}
    if request.method != "GET":
        logger.info("Request method is not GET")
        return HttpResponse(status=400)
    try:
        credentials_model = EolGoogleAuth.objects.get(user=request.user)
        credentials_dict = get_user_credentials_google(
            credentials_model.credentials)
        if credentials_dict is not None:
            data = check_permission_youtube(credentials_dict)
            if data['credentials']:
                credentials_model.credentials = json.dumps(credentials_dict)
                credentials_model.channel_enabled = data['channel']
                credentials_model.livebroadcast_enabled = data['livestream']
                credentials_model.save()
                response.update(data)
    except EolGoogleAuth.DoesNotExist:
        logger.info("User google account dont exists in database")

    return JsonResponse(response, safe=False)


def check_permission_youtube(credentials_dict):
    """
        Verify if user have channel and live permission in Youtube
    """
    credentials = cretentials_dict_to_object(credentials_dict)
    data = {'channel': False, 'livestream': False, 'credentials': True}
    youtube = googleapiclient.discovery.build(
        'youtube', 'v3', credentials=credentials, cache_discovery=False)
    data = check_permission_channels(youtube, data)
    data = check_permission_live(youtube, data)

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
        logger.info(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
    except RefreshError:
        data['credentials'] = False
        logger.info("An error occurred with token user")
    return data


def check_permission_live(youtube, data):
    """
        Verify if user have live permission
        Create and remove a live on Youtube
    """
    try:
        id_live = insert_broadcast(youtube, str(
            dt.now()), "EOL - Validate permission")
        delete_broadcast(youtube, id_live)
        data['livestream'] = True
    except HttpError as e:
        logger.info(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
    except RefreshError:
        data['credentials'] = False
        logger.info("An error occurred with token user")
    return data


def update_livebroadcast(request):
    """
        Update livestreams youtube with new data
    """
    response = {'status': 'error'}
    if request.method != "POST":
        logger.info("Request method is not POST")
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'meeting_id' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'broadcast_id' not in request.POST:
        logger.info("Params Error")
        return JsonResponse(response, safe=False)

    youtube = create_youtube_object(request.user)
    if youtube is None:
        return JsonResponse(response, safe=False)
    start_time = '{}T{}:00-04:00'.format(
        request.POST['date'],
        request.POST['time'])  # yyyy-mm-ddTHH:mm:ss-04:00

    id_live = update_live_in_youtube(
        youtube,
        start_time,
        request.POST['display_name'],
        request.POST['broadcast_id'])
    if id_live:
        response['status'] = "ok"
        response['id_broadcast'] = id_live
    logger.info("Error in update livestream in zoom meeting")
    return JsonResponse(response, safe=False)


def update_live_in_youtube(youtube, start_time, title, id_live):
    """
        Update livestreams youtube with new data
    """
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
        logger.info(
            "An HTTP error {} occurred:\n{}".format(
                e.resp.status, e.content))
        return None
    except RefreshError:
        logger.info("An error occurred with token user")
        return None
