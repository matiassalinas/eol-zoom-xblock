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
from . import utils_youtube
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers

import httplib2
import os
import sys

from apiclient.errors import HttpError
from google.auth.exceptions import RefreshError
import google.oauth2.credentials
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
        logger.error("Request method is not GET")
        return HttpResponse(status=400)
    user = request.user
    credentials, data = utils_youtube._get_user_credentials_google(user)
    return JsonResponse(data, safe=False)

def auth_google(request):
    """
        Set the url to authenticate with google
    """
    if request.method != "GET":
        logger.error("Request method is not GET")
        return HttpResponse(status=400)
    # Client configuration for an OAuth 2.0 web server application
    # (cf. https://developers.google.com/identity/protocols/OAuth2WebServer)
    CLIENT_CONFIG = utils_youtube.create_client_config()
    # This scope will allow the application to manage your calendars
    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    # Use the client_secret.json file to identify the application requesting
    # authorization. The client ID (from that file) and access scopes are
    # required.
    import google_auth_oauthlib.flow
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
        logger.error("Request method is not GET")
        return HttpResponse(status=400)
    if 'state' not in request.GET or 'code' not in request.GET or 'scope' not in request.GET:
        logger.debug("State, Code or Scope not found in request.GET")
        return HttpResponse(status=400)
    state = request.GET.get('state')
    CLIENT_CONFIG = utils_youtube.create_client_config()

    # This scope will allow the application to create and remove livestreams
    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    # Use the client_secret.json file to identify the application requesting
    # authorization. The client ID (from that file) and access scopes are
    # required.
    import google_auth_oauthlib.flow
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
            "Error with Exchange authorization code for refresh and access tokens, User {}".format(
                request.user
            ))
        return HttpResponse(status=400)
    # Load credentials from the session.
    credentials_dict = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'scopes': credentials.scopes,
        'expiry': str(credentials.expiry)}
    data = utils_youtube.check_permission_youtube(credentials_dict, request.user)
    EolGoogleAuth.objects.update_or_create(
        user=request.user,
        defaults={'credentials':json.dumps(credentials_dict),
        'channel_enabled':data['channel'],
        'livebroadcast_enabled':data['livestream'],
        'custom_live_streaming_service': data['livestream_zoom']})
    return HttpResponseRedirect(next_url)

def create_livebroadcast(request):
    """
        Create the livestream in youtube and set stream data in zoom meeting
    """
    response = {'status': 'error'}
    if request.method != "POST":
        logger.error("Request method is not POST")
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'meeting_id' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'restricted_access' not in request.POST:
        logger.debug("Params Error, user: {}, request.POST: {}".format(request.user, request.POST.__dict__))
        response['text'] = "Params Error"
        return JsonResponse(response, safe=False)

    youtube = utils_youtube.create_youtube_object(request.user)
    if youtube is None:
        response['text'] = "Error to create youtube object"
        return JsonResponse(response, safe=False)
    yt_timezone = settings.EOLZOOM_YOUTUBE_TIMEZONE or '+00:00' # yyyy-mm-ddTHH:mm:ss+00:00
    start_time = '{}T{}:00{}'.format(
        request.POST['date'],
        request.POST['time'], yt_timezone)

    livebroadcast_data = utils_youtube.create_live_in_youtube(
        youtube, start_time, request.POST['display_name'])
    if livebroadcast_data is None:
        logger.error("Error in Create live in youtube, user: {}, id_meeting: {}".format(request.user, request.POST['meeting_id']))
        response['text'] = "Error in Create live in youtube"
        return JsonResponse(response, safe=False)
    if livebroadcast_data is False:
        logger.error("Youtube have problem to create livestream, user: {}, id_meeting: {}".format(request.user, request.POST['meeting_id']))
        response['text'] = "youtube_500"
        return JsonResponse(response, safe=False)
    status = utils_youtube.update_meeting_youtube(
        request.user,
        livebroadcast_data,
        request.POST['meeting_id'])
    if status:
        save = utils_youtube.save_broadcast_id(request.POST['meeting_id'], livebroadcast_data['broadcast_id'])
        if save:
            response['status'] = "ok"
            response['id_broadcast'] = livebroadcast_data['broadcast_id']
    else:
        response['text'] = "error in update_meeting_youtube or save_broadcast_id"
    return JsonResponse(response, safe=False)

def youtube_validate(request):
    """
        Verify if user have permission in youtube
    """
    response = {'channel': False, 'livestream': False, 'credentials': False, 'livestream_zoom': False}
    if request.method != "GET":
        logger.error("Request method is not GET")
        return HttpResponse(status=400)
    try:
        credentials_model = EolGoogleAuth.objects.get(user=request.user)
        credentials_dict = utils_youtube.get_user_credentials_google(
            credentials_model.credentials)
        if credentials_dict is not None:
            data = utils_youtube.check_permission_youtube(credentials_dict, request.user)
            if data['credentials']:
                credentials_model.credentials = json.dumps(credentials_dict)
                credentials_model.channel_enabled = data['channel']
                credentials_model.livebroadcast_enabled = data['livestream']
                credentials_model.custom_live_streaming_service = data['livestream_zoom']
                credentials_model.save()
                response.update(data)
    except EolGoogleAuth.DoesNotExist:
        logger.error("User google account dont exists in database, user: {}".format(request.user))

    return JsonResponse(response, safe=False)

def update_livebroadcast(request):
    """
        Update livestreams youtube with new data
    """
    response = {'status': 'error'}
    if request.method != "POST":
        logger.error("Request method is not POST")
        return HttpResponse(status=400)
    if 'display_name' not in request.POST or 'meeting_id' not in request.POST or 'date' not in request.POST or 'time' not in request.POST or 'duration' not in request.POST or 'broadcast_id' not in request.POST:
        logger.debug("Params Error, user: {}, request.POST: {}".format(request.user, request.POST.__dict__))
        response['text'] = "Params Error"
        return JsonResponse(response, safe=False)

    youtube = utils_youtube.create_youtube_object(request.user)
    if youtube is None:
        response['text'] = "Error to create youtube object"
        return JsonResponse(response, safe=False)
    yt_timezone = settings.EOLZOOM_YOUTUBE_TIMEZONE or '+00:00' # yyyy-mm-ddTHH:mm:ss+00:00
    start_time = '{}T{}:00{}'.format(
        request.POST['date'],
        request.POST['time'], yt_timezone) 

    id_live = utils_youtube.update_live_in_youtube(
        youtube,
        start_time,
        request.POST['display_name'],
        request.POST['broadcast_id'])
    if id_live:
        response['status'] = "ok"
        response['id_broadcast'] = id_live
    else:
        response['text'] = "error in update_live_in_youtube"
    return JsonResponse(response, safe=False)
