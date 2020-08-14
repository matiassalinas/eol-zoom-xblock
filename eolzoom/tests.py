# -*- coding: utf-8 -*-


from mock import patch, Mock,PropertyMock
from collections import namedtuple

import json
import base64

from django.test import TestCase, Client
from django.urls import reverse

from util.testing import UrlResetMixin
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase

from xmodule.modulestore.tests.factories import CourseFactory
from student.tests.factories import UserFactory, CourseEnrollmentFactory
from xblock.field_data import DictFieldData
from student.roles import CourseStaffRole
from django.test.utils import override_settings
from .eolzoom import EolZoomXBlock

from six import text_type
import urllib.parse
from urllib.parse import parse_qs
from . import views, youtube_views
from .models import EolZoomAuth, EolZoomRegistrant, EolGoogleAuth, EolZoomMappingUserMeet
from datetime import datetime as dt
import datetime
import logging
logger = logging.getLogger(__name__)

XBLOCK_RUNTIME_USER_ID = 99

class TestRequest(object):
    # pylint: disable=too-few-public-methods
    """
    Module helper for @json_handler
    """
    method = None
    body = None
    success = None
    params = None
    headers = None


class TestEolZoomAPI(UrlResetMixin, ModuleStoreTestCase):
    def setUp(self):

        super(TestEolZoomAPI, self).setUp()

        # create a course
        self.course = CourseFactory.create(org='mss', course='999',
                                           display_name='eolzoom tests')

        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            uname = 'student'
            email = 'student@edx.org'
            password = 'test'

            # Create the user
            self.user = UserFactory(
                username=uname, password=password, email=email)
            CourseEnrollmentFactory(
                user=self.user,
                course_id=self.course.id)

            # Log the user in
            self.client = Client()
            self.assertTrue(self.client.login(username=uname, password=password))

            # Create refresh_token
            self.zoom_auth = EolZoomAuth.objects.create(
                user=self.user,
                zoom_refresh_token='test_refresh_token'
            )

    def test_update_auth_in_models(self):
        """
            Create and check; update and check refresh token
        """
        new_student = UserFactory(
            username='test_student',
            password='test_password',
            email='test_email@email.email')
        views._update_auth(new_student, 'new_token')
        refresh_token = views._get_refresh_token(new_student)
        self.assertEqual(refresh_token, 'new_token')

        views._update_auth(new_student, 'update_token')
        refresh_token = views._get_refresh_token(new_student)
        self.assertEqual(refresh_token, 'update_token')

    def test_get_refresh_token_from_models(self):
        """
            Test get refresh token with two student
            First student with refresh token
            Second student without refresh token
        """
        refresh_token = views._get_refresh_token(self.user)
        self.assertEqual(refresh_token, 'test_refresh_token')

        new_student = UserFactory(
            username='test_student',
            password='test_password',
            email='test_email@email.email')
        new_refresh_token = views._get_refresh_token(new_student)
        self.assertEqual(new_refresh_token, None)

    @patch("requests.post")
    def test_get_refresh_token_from_zoom_api(self, post):
        """
            Test post request to zoom api (get refresh token)
        """
        authorization_code = 'authorization_code'
        redirect_uri = 'REDIRECT_URI'
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        new_refresh_token = views.get_refresh_token(
            authorization_code, redirect_uri)
        self.assertEqual(new_refresh_token, response)

    @patch("requests.post")
    def test_get_access_token_from_zoom_api(self, post):
        """
            Test post request to zoom api (get access token)
            Check if refresh token is updated
        """
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjIwNTMxODczOTQsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDczOTQsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI2fQ.DwuqOzywRrQO2a6yp0K_6V-hR_i_mOB62flkr0_NfFdYsSqahIRRGk1GlUTQnFzHd896XDKf_FnSSvoJg_tzuQ",
            "expires_in": 3599,
            "scope": "user:read"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        new_token = views.get_access_token(
            self.user, self.zoom_auth.zoom_refresh_token)
        self.assertEqual(new_token, response)

        zoom_auth = EolZoomAuth.objects.get(
            user=self.user
        )
        self.assertEqual(
            zoom_auth.zoom_refresh_token,
            response['refresh_token'])

    @patch("requests.get")
    def test_get_user_profile_from_zoom_api(self, get):
        """
            Test get request to zoom api (get user profile)
        """
        access_token = 'access_token'
        response = {
            'id': 'user_id',
            'first_name': 'first_name',
            'last_name': 'last_name',
            'email': 'email@email.email',
            'type': 'type',
        }
        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        user_profile = views.get_user_profile(access_token)
        self.assertEqual(user_profile, response)

    @patch("requests.post")
    @patch("requests.get")
    def test_get_user_profile(self, get, post):
        """
            Test function that generate tokens and call get_user_profile from zoom api
        """
        # POST Access Token
        access_token_response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjIwNTMxODczOTQsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDczOTQsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI2fQ.DwuqOzywRrQO2a6yp0K_6V-hR_i_mOB62flkr0_NfFdYsSqahIRRGk1GlUTQnFzHd896XDKf_FnSSvoJg_tzuQ",
            "expires_in": 3599,
            "scope": "user:read"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:access_token_response), ]
        # GET User Profile
        user_profile_response = {
            'id': 'user_id',
            'first_name': 'first_name',
            'last_name': 'last_name',
            'email': 'email@email.email',
            'type': 'type',
        }
        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:user_profile_response), ]

        user_profile = views._get_user_profile(self.user)
        self.assertEqual(user_profile, user_profile_response)

    @patch("requests.post")
    def test_new_scheduled_meeting(self, post):
        """
            Test create a new scheduled meeting
        """
        # POST Access Token
        access_token_response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjIwNTMxODczOTQsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDczOTQsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI2fQ.DwuqOzywRrQO2a6yp0K_6V-hR_i_mOB62flkr0_NfFdYsSqahIRRGk1GlUTQnFzHd896XDKf_FnSSvoJg_tzuQ",
            "expires_in": 3599,
            "scope": "user:read"
        }
        # POST Create Meeting
        create_meeting_response = {
            "topic": 'topic',
            "type": 2,
            "start_time": '2020-10-10T10:10:00',
            "duration": 40,
            "timezone": 'America/Santiago',
            "agenda": 'agenda',
            "id": 'meeting_id',
            "start_url": 'start_url_example',
            "join_url": 'join_url_example',
            "password": 'password'
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:access_token_response), namedtuple(
                    "Request", [
                        "status_code", "json"])(
                            201, lambda:create_meeting_response), ]

        post_data = {
            'display_name': 'display_name',
            'description': 'description',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'restricted_access': 'false'
        }
        response = self.client.post(
            reverse('new_scheduled_meeting'), post_data)
        data = response.json()
        self.assertEqual(data['meeting_id'], create_meeting_response['id'])

    @patch("requests.post")
    @patch("requests.patch")
    def test_update_scheduled_meeting(self, patch, post):
        """
            Test update a new scheduled meeting
        """
        # POST Access Token
        access_token_response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjIwNTMxODczOTQsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDczOTQsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI2fQ.DwuqOzywRrQO2a6yp0K_6V-hR_i_mOB62flkr0_NfFdYsSqahIRRGk1GlUTQnFzHd896XDKf_FnSSvoJg_tzuQ",
            "expires_in": 3599,
            "scope": "user:read"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:access_token_response), ]

        # Patch Updated Meeting
        update_meeting_response = {
        }
        patch.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                204, lambda:update_meeting_response), ]

        post_data = {
            'display_name': 'display_name',
            'description': 'description',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'meeting_id': 'meeting_id',
            'restricted_access': 'false'
        }
        response = self.client.post(
            reverse('update_scheduled_meeting'), post_data)
        data = response.json()
        self.assertEqual(data['meeting_id'], post_data['meeting_id'])

    @patch("requests.post")
    @patch("requests.get")
    def test_is_logged_zoom(self, get, post):
        """
            Check response status code at is_logged_zoom
        """
        # POST Access Token
        access_token_response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjIwNTMxODczOTQsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDczOTQsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI2fQ.DwuqOzywRrQO2a6yp0K_6V-hR_i_mOB62flkr0_NfFdYsSqahIRRGk1GlUTQnFzHd896XDKf_FnSSvoJg_tzuQ",
            "expires_in": 3599,
            "scope": "user:read"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:access_token_response), ]
        # GET User Profile
        user_profile_response = {
            'id': 'user_id',
            'first_name': 'first_name',
            'last_name': 'last_name',
            'email': 'email@email.email',
            'type': 'type',
        }
        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:user_profile_response), ]
        response = self.client.get(reverse('is_logged_zoom'))
        self.assertEqual(response.status_code, 200)

    @patch("requests.post")
    def test_zoom_api(self, post):
        """
            Check response status code at zoom_api
        """
        # POST Refresh Token
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        get_data = {
            'code': 'authorization_code',
            'redirect': base64.b64encode('https://eol.uchile.cl/'.encode("utf-8"))
        }
        response = self.client.get(reverse('zoom_api'), get_data)
        self.assertEqual(response.status_code, 302)

    def test_get_students(self):
        """
            Test if get_students is giving the correct enrolled students
        """
        students = views.get_students(self.user, text_type(self.course.id))
        self.assertEqual(len(students), 0)

        new_student = UserFactory(
            username='test_student',
            password='test_password',
            email='test_email@email.email')
        CourseEnrollmentFactory(
            user=new_student,
            course_id=self.course.id)
        students = views.get_students(self.user, text_type(self.course.id))
        self.assertEqual(len(students), 1)

    @patch("requests.post")
    def test_get_meeting_registrant(self, post):
        """
            Test creating a meeting registrant for a student.
            1. Registration Success
            2. Registration Error
        """
        access_token = "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA"

        registrants_response = {
            "id": 85746065,
            "registrant_id": "a",
            "start_time": "culpa mollit",
            "topic": "reprehenderit ea ut ex Excepteur"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                201, lambda:registrants_response), ]

        student_info = {
            'email': "email",
            'first_name': "first_name",
            'last_name': "platform_name"
        }

        meeting_registrant = views.get_meeting_registrant(
            'meeting_id', self.user, student_info, access_token)
        self.assertEqual(meeting_registrant, registrants_response)

        registrants_response = "error"
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "text"])(
                300, registrants_response), ]

        meeting_registrant = views.get_meeting_registrant(
            'meeting_id', self.user, student_info, access_token)
        self.assertEqual(meeting_registrant, {'error': 'Registration fail'})

    @patch("requests.put")
    def test_set_meeting_status(self, put):
        """
            Test set meeting for a set of students
            1. Approval success
            2. Error
        """
        access_token = "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA"
        status_response = "Meeting updated."
        put.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "text"])(
                204, status_response),
        ]
        students = [
            {
                'id': "id1",
                'email': "email1",
            },
            {
                'id': "id2",
                'email': "email2",
            },
        ]
        meeting_status = views.set_registrant_status(
            'meeting_id', self.user, students, access_token)
        self.assertEqual(meeting_status, {'success': 'approved'})

        put.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "text"])(
                400, status_response),
        ]
        meeting_status = views.set_registrant_status(
            'meeting_id', self.user, students, access_token)
        self.assertEqual(
            meeting_status, {
                'error': 'Set registrant status fail'})

    @patch("eolzoom.views.get_meeting_registrant")
    @patch("eolzoom.views.set_registrant_status")
    def test_meeting_registrant(
            self,
            set_registrant_status,
            get_meeting_registrant):
        """
            Test all meeting registrant process. Get > Set registrant status
            1. Success
            2. Fail
        """
        new_student = UserFactory(
            username='test_student',
            password='test_password',
            email='test_email@email.email')
        CourseEnrollmentFactory(
            user=new_student,
            course_id=self.course.id)

        students = views.get_students(self.user, text_type(self.course.id))

        access_token = "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA"

        get_meeting_registrant.side_effect = [
            {'registrant_id': 'registrant_id_1'}, {'registrant_id': 'registrant_id_2'}]
        set_registrant_status.side_effect = [{'success': 'approved'}]
        meeting_registrant = views.meeting_registrant(
            self.user, 'meeting_id', students, access_token)
        self.assertEqual(meeting_registrant, True)

        get_meeting_registrant.side_effect = [
            {'registrant_id': 'registrant_id_1'}, {'registrant_id': 'registrant_id_2'}]
        set_registrant_status.side_effect = [
            {'error': 'Set registrant status fail'}]
        meeting_registrant = views.meeting_registrant(
            self.user, 'meeting_id', students, access_token)
        self.assertEqual(meeting_registrant, False)

    def test_submit_join_url(self):
        """
            Test submit join url into model
            1. Without students
            2. With students
            3. Check no duplicity
        """
        students = []
        meeting_id = 'meeting_id'
        views._submit_join_url(students, meeting_id)
        registrants = EolZoomRegistrant.objects.filter(meeting_id=meeting_id)
        self.assertEqual(registrants.count(), 0)

        students = [
            {
                'email': "email1",
                'join_url': "join_url_1"
            },
            {
                'email': "email2",
                'join_url': "join_url_2"
            },
            {
                'email': "email3",
                'join_url': "join_url_3"
            },
            {
                'email': "email4",
                'join_url': "join_url_4"
            },
        ]
        views._submit_join_url(students, meeting_id)
        registrants = EolZoomRegistrant.objects.filter(meeting_id=meeting_id)
        self.assertEqual(registrants.count(), 4)

        views._submit_join_url(students, meeting_id)
        registrants = EolZoomRegistrant.objects.filter(meeting_id=meeting_id)
        self.assertEqual(registrants.count(), 4)

    @patch("requests.get")
    def test_get_join_url(self, get):
        """
            Test get join url (set of registrants with their url).
            Success and Fail
        """
        access_token = "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA"
        join_url_response = {
            "page_count": 1,
            "page_number": 1,
            "page_size": 1,
            "total_records": 2,
            "registrants": [
                {
                    "email": "email1",
                    "join_url": "join_url1"
                },
                {
                    "email": "email2",
                    "join_url": "join_url2"
                }
            ],
        }
        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:join_url_response), ]

        registrants = views.get_join_url(
            self.user, 'meeting_id', text_type(
                self.course.id), access_token)
        self.assertEqual(registrants, join_url_response['registrants'])

        get.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "text"])(
                400, ["error"]), ]
        registrants = views.get_join_url(
            self.user, 'meeting_id', text_type(
                self.course.id), access_token)
        self.assertEqual(registrants, [])

    @patch("eolzoom.views.get_join_url")
    @patch("eolzoom.views.meeting_registrant")
    @patch("eolzoom.views.get_refresh_token")
    def test_start_meeting(
            self,
            get_refresh_token,
            meeting_registrant,
            get_join_url):
        """
            Test start meeting GET request
        """
        get_refresh_token.side_effect = [{
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjE1ODAxNTA5OTQsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0NzM5NCwianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjZ9.5c58p0PflZJdlz4Y7PgMIVCrQpHDnbM565iCKlrtajZ5HHmy00P5FCcoMwHb9LxjsUgbJ7653EfdeX5NEm6RoA",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ3Mzk0LCJleHAiOjIwNTMxODczOTQsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDczOTQsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI2fQ.DwuqOzywRrQO2a6yp0K_6V-hR_i_mOB62flkr0_NfFdYsSqahIRRGk1GlUTQnFzHd896XDKf_FnSSvoJg_tzuQ",
            "expires_in": 3599,
            "scope": "user:read"
        }]
        meeting_registrant.side_effect = [True]
        get_join_url.side_effect = [{
            "page_count": 1,
            "page_number": 1,
            "page_size": 1,
            "total_records": 2,
            "registrants": [
                {
                    "email": "email1",
                    "join_url": "join_url1"
                },
                {
                    "email": "email2",
                    "join_url": "join_url2"
                }
            ],
        }]
        data = {
            "meeting_id": "meeting_id",
            "course_id": text_type(self.course.id)
        }
        get_data = {
            "code": "code",
            "data": base64.b64encode(json.dumps(data).encode("utf-8"))
        }
        response = self.client.get(reverse('start_meeting'), get_data)
        self.assertEqual(response.status_code, 302)

    def test_get_student_join_url(self):
        """
            Test join url:
            1. Meeting not started/created
            2. User not registered
            3. User registered
        """
        get_data = {
            'meeting_id': 'meeting_id'
        }
        response = self.client.get(reverse('get_student_join_url'), get_data)
        self.assertEqual(
            response.json(), {
                'status': False, 'error_type': 'NOT_STARTED'})

        EolZoomRegistrant.objects.get_or_create(
            meeting_id='meeting_id',
            email='email1',
            join_url='url1'
        )
        response = self.client.get(reverse('get_student_join_url'), get_data)
        self.assertEqual(
            response.json(), {
                'status': False, 'error_type': 'NOT_FOUND'})

        EolZoomRegistrant.objects.get_or_create(
            meeting_id='meeting_id',
            email=self.user.email,
            join_url='url2'
        )
        response = self.client.get(reverse('get_student_join_url'), get_data)
        self.assertEqual(response.json(), {'status': True, 'join_url': 'url2'})


class TestEolZoomXBlock(UrlResetMixin, ModuleStoreTestCase):

    def make_an_xblock(self, **kw):
        """
        Helper method that creates a EolZoom XBlock
        """
        course = self.course
        runtime = Mock(
            course_id=course.id,
            user_is_staff=True,
            service=Mock(
                return_value=Mock(_catalog={}),
            ),
            user_id=XBLOCK_RUNTIME_USER_ID,
        )
        scope_ids = Mock()
        field_data = DictFieldData(kw)
        xblock = EolZoomXBlock(runtime, field_data, scope_ids)
        xblock.xmodule_runtime = runtime
        xblock.location = course.id  # Example of location
        xblock._edited_by = XBLOCK_RUNTIME_USER_ID
        return xblock

    def setUp(self):

        super(TestEolZoomXBlock, self).setUp()

        # create a course
        self.course = CourseFactory.create(org='mss', course='999',
                                           display_name='eolzoom tests')

        # create eolzoom Xblock
        self.xblock = self.make_an_xblock()
        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            uname = 'student'
            email = 'student@edx.org'
            password = 'test'

            # Create and enroll student
            self.student = UserFactory(
                username=uname, password=password, email=email)
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course.id)

            # Create and Enroll staff user
            self.staff_user = UserFactory(
                username='staff_user',
                password='test',
                email='staff@edx.org',
                is_staff=True)
            CourseEnrollmentFactory(
                user=self.staff_user,
                course_id=self.course.id)
            CourseStaffRole(self.course.id).add_users(self.staff_user)

            # Log the student in
            self.client = Client()
            self.assertTrue(self.client.login(username=uname, password=password))

            # Log the user staff in
            self.staff_client = Client()
            self.assertTrue(
                self.staff_client.login(
                    username='staff_user',
                    password='test'))

            # Create refresh_token
            self.zoom_auth = EolZoomAuth.objects.create(
                user=self.staff_user,
                zoom_refresh_token='test_refresh_token'
            )

    def test_workbench_scenarios(self):
        """
            Checks workbench scenarios title and basic scenario
        """
        result_title = 'EolZoomXBlock'
        basic_scenario = "<eolzoom/>"
        test_result = self.xblock.workbench_scenarios()
        self.assertEqual(result_title, test_result[0][0])
        self.assertIn(basic_scenario, test_result[0][1])

    def test_validate_default_field_data(self):
        """
            Validate that xblock is created successfully
        """
        self.assertEqual(self.xblock.display_name, 'Videollamada Zoom')
        self.assertEqual(self.xblock.meeting_id, None)
        self.assertEqual(self.xblock.date, None)
        self.assertEqual(self.xblock.time, None)
        self.assertEqual(self.xblock.description, "")
        self.assertEqual(self.xblock.duration, 40)
        self.assertEqual(self.xblock.created_by, None)
        self.assertEqual(self.xblock.created_location, None)
        self.assertEqual(self.xblock.start_url, None)
        self.assertEqual(self.xblock.join_url, None)

    def test_student_view_without_configuration(self):
        """
            Check if error message is triggered when a meeting is not configured
        """
        student_view = self.xblock.student_view()
        student_view_html = student_view.content
        self.assertIn('class="eolzoom_error"', student_view_html)

    def test_student_view_with_configuration(self):
        """
            Check if error message is not triggered when a meeting is successfully configured
            Have two cases of page render:
            1. Staff user (host)
            2. Staff user (not host)
            3. Student user
        """
        self.xblock.meeting_id = 'meeting_id'
        self.xblock.date = '2020-12-26'
        self.xblock.time = '23:32'
        self.xblock.description = 'description'
        self.xblock.duration = 120
        self.xblock.created_by = self.staff_user.email
        self.xblock.created_location = self.xblock.location._to_string()
        self.xblock.start_url = "start_url_example"
        self.xblock.join_url = "join_url_example"

        # 1. Staff user host
        self.xblock.edx_created_by = XBLOCK_RUNTIME_USER_ID
        self.xblock.runtime.user_is_staff = True
        student_staff_view = self.xblock.student_view()
        student_staff_view_html = student_staff_view.content
        self.assertNotIn('class="eolzoom_error"', student_staff_view_html)
        self.assertIn('class="button button-green start_meeting-btn"',
                      student_staff_view_html)  # 'Iniciar Transmision' button
        self.assertNotIn(
            'class="button button-blue join_meeting-btn"',
            student_staff_view_html)  # 'Ingresar a la sala' button

        # 2. Staff user not host
        self.xblock.edx_created_by = XBLOCK_RUNTIME_USER_ID - 1
        self.xblock.runtime.user_is_staff = True
        student_staff_view = self.xblock.student_view()
        student_staff_view_html = student_staff_view.content
        self.assertNotIn('class="eolzoom_error"', student_staff_view_html)
        self.assertNotIn(
            'class="button button-green start_meeting-btn"',
            student_staff_view_html)  # 'Iniciar Transmision' button
        self.assertIn('class="button button-blue join_meeting-btn"',
                      student_staff_view_html)  # 'Ingresar a la sala' button

        # 3. Student user
        self.xblock.edx_created_by = XBLOCK_RUNTIME_USER_ID - 1
        self.xblock.runtime.user_is_staff = False
        student_view = self.xblock.student_view()
        student_view_html = student_view.content
        self.assertNotIn('class="eolzoom_error"', student_view_html)
        self.assertNotIn('class="button button-green start_meeting-btn"',
                         student_view_html)  # 'Iniciar Transmision' button
        self.assertIn('class="button button-blue join_meeting-btn"',
                      student_view_html)  # 'Ingresar a la sala' button

    def test_author_view(self):
        """
            Test author view:
            1. Without Configurations
            2. Load correct html
            3. With Configurations
            3.a Author is host (edx_created_by)
            3.b Author is not host (edx_created_by)
        """
        # 1. Without Configurations
        author_view = self.xblock.author_view()
        author_view_html = author_view.content

        self.assertIn('class="eolzoom_error"', author_view_html)

        # 2. Load correct html
        self.assertIn('class="eolzoom_author"', author_view_html)

        # 3. With Configurations
        self.xblock.meeting_id = 'meeting_id'
        self.xblock.date = '2020-12-26'
        self.xblock.time = '23:32'
        self.xblock.description = 'description'
        self.xblock.duration = 120
        self.xblock.created_by = self.staff_user.email
        self.xblock.created_location = self.xblock.location._to_string()
        self.xblock.start_url = "start_url_example"
        self.xblock.join_url = "join_url_example"

        # 3.a Author is host
        self.xblock.edx_created_by = XBLOCK_RUNTIME_USER_ID
        author_view = self.xblock.author_view()
        author_view_html = author_view.content
        self.assertNotIn('class="eolzoom_error"', author_view_html)
        self.assertIn('class="button button-green start_meeting-btn"',
                      author_view_html)  # 'Iniciar Transmision' button
        self.assertNotIn('class="button button-blue join_meeting-btn"',
                         author_view_html)  # 'Ingresar a la sala' button

        # 3.b Author is not host
        self.xblock.edx_created_by = 'another'
        author_view = self.xblock.author_view()
        author_view_html = author_view.content
        self.assertNotIn('class="eolzoom_error"', author_view_html)
        self.assertNotIn('class="button button-green start_meeting-btn"',
                         author_view_html)  # 'Iniciar Transmision' button
        self.assertIn('class="button button-blue join_meeting-btn"',
                      author_view_html)  # 'Ingresar a la sala' button

    def test_studio_submit(self):
        request = TestRequest()
        request.method = 'POST'
        post_data = {
            'display_name': 'new_display_name',
            'description': 'new_description',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': 80,
            'meeting_id': 'new_meeting_id',
            'created_by': self.staff_user.email,
            'created_location': self.xblock.location._to_string(),
            'start_url': 'start_url_example',
            'join_url': 'join_url_example',
            'restricted_access': False,
            'meeting_password': 'meeting_password',
            'google_access': False,
            'broadcast_id': 'new_live_yt',
        }
        data = json.dumps(post_data)
        request.body = data
        request.params = post_data
        response = self.xblock.studio_submit(request)
        self.assertEqual(self.xblock.display_name, 'new_display_name')
        self.assertEqual(self.xblock.description, 'new_description')
        self.assertEqual(self.xblock.date, '2020-10-10')
        self.assertEqual(self.xblock.time, '10:10')
        self.assertEqual(self.xblock.duration, 80)
        self.assertEqual(self.xblock.meeting_id, 'new_meeting_id')
        self.assertEqual(self.xblock.start_url, 'start_url_example')
        self.assertEqual(self.xblock.join_url, 'join_url_example')
        self.assertEqual(self.xblock.meeting_password, 'meeting_password')
        self.assertEqual(self.xblock.restricted_access, False)
        self.assertEqual(self.xblock.created_by, self.staff_user.email)
        self.assertEqual(
            self.xblock.created_location,
            self.xblock.location._to_string())

class TestEolYouTubeAPI(UrlResetMixin, ModuleStoreTestCase):
    def setUp(self):

        super(TestEolYouTubeAPI, self).setUp()

        # create a course
        self.course = CourseFactory.create(org='mss', course='999',
                                           display_name='eolzoom tests')

        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            uname = 'student'
            email = 'student@edx.org'
            password = 'test'

            # Create the user
            self.user = UserFactory(
                username=uname, password=password, email=email)
            CourseEnrollmentFactory(
                user=self.user,
                course_id=self.course.id)

            # Log the user in
            self.client = Client()
            self.assertTrue(self.client.login(username=uname, password=password))
    
    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_PROJECT_ID = 'test-project')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @override_settings(GOOGLE_REDIRECT_URIS = ["https://studio.test.cl/zoom/callback_google_auth"])
    @override_settings(GOOGLE_JAVASCRIPT_ORIGINS = ["https://studio.test.cl"])
    def test_auth_google(self):
        """
            Test auth_google normal process    
        """
        result = self.client.get(
            reverse('auth_google'),
            data={'redirect': 'Lw=='})
        request = urllib.parse.urlparse(result.url)
        args = urllib.parse.parse_qs(request.query)
        self.assertEqual(request.netloc, 'accounts.google.com')
        self.assertEqual(request.path, '/o/oauth2/auth')
        self.assertEqual(args['scope'], ["https://www.googleapis.com/auth/youtube.force-ssl"])
        self.assertEqual(args['access_type'][0], "offline")
        self.assertEqual(args['include_granted_scopes'][0], 'true')
        self.assertEqual(args['state'][0], "Lw==")
        self.assertEqual(args['redirect_uri'][0], "https://testserver/zoom/callback_google_auth")
        self.assertEqual(args['response_type'][0], "code")
        self.assertEqual(args['client_id'][0], 'test-client-id.apps.googleusercontent.com')
    
    def test_auth_google_post(self):
        """
            Test auth_google if request is post   
        """
        result = self.client.post(reverse('auth_google'),
            data={'redirect': 'Lw=='})
        self.assertEqual(result.status_code, 400)

    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_PROJECT_ID = 'test-project')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @override_settings(GOOGLE_REDIRECT_URIS = ["https://studio.test.cl/zoom/callback_google_auth"])
    @override_settings(GOOGLE_JAVASCRIPT_ORIGINS = ["https://studio.test.cl"])
    @patch('eolzoom.youtube_views.check_permission_live')
    @patch('eolzoom.youtube_views.check_permission_channels')
    @patch('google_auth_oauthlib.flow.Flow.fetch_token')
    def test_callback_google_auth(self, flow, channel, live):
        """
            Test callback_google_auth normal process    
        """
        with patch('google_auth_oauthlib.flow.Flow.credentials', new_callable=PropertyMock) as mock_foo:
            channel.return_value = {'channel':True,'livestream':False,'credentials': True}
            live.return_value = {'channel':True,'livestream':True,'credentials': True}
            mock_foo.return_value = namedtuple("Flow", ["token", "refresh_token", 'token_uri','scopes','expiry'])("this-is-a-token", "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI","https://www.googleapis.com/oauth2/v3/token",["https://www.googleapis.com/auth/youtube.force-ssl"],dt.now())
            data = {'state': 'Lw==', 'code': 'asdf', 'scope': 'https://www.googleapis.com/auth/youtube.force-ssl'}
            self.assertFalse(EolGoogleAuth.objects.filter(user=self.user).exists())
            result = self.client.get(reverse('callback_google_auth'), data=data)
            self.assertTrue(EolGoogleAuth.objects.filter(user=self.user).exists())
    
    def test_callback_google_auth_not_state(self):
        """
            Test callback_google_auth if state params not exists   
        """
        result = self.client.get(reverse('callback_google_auth'), 
            data={
            'code': 'asdf', 
            'scope': 'https://www.googleapis.com/auth/youtube.force-ssl'})
        self.assertEqual(result.status_code, 400)
    
    def test_callback_google_auth_not_code(self):
        """
            Test callback_google_auth if code params not exists   
        """
        result = self.client.get(reverse('callback_google_auth'), 
            data={'state': 'Lw==', 
            'scope': 'https://www.googleapis.com/auth/youtube.force-ssl'})
        self.assertEqual(result.status_code, 400)
    
    def test_callback_google_auth_not_scope(self):
        """
            Test callback_google_auth if state scope not exists   
        """
        result = self.client.get(reverse('callback_google_auth'), 
            data={'state': 'Lw==', 
            'code': 'asdf'})
        self.assertEqual(result.status_code, 400)
    
    def test_callback_google_post(self):
        """
            Test callback_google_auth if resquest is post   
        """
        result = self.client.post(reverse('callback_google_auth'), 
            data={'state': 'Lw==', 
            'code': 'asdf'})
        self.assertEqual(result.status_code, 400)
    
    @patch("requests.post")
    def test_google_is_logged(self, post):
        """
            Test google_is_logged normal process  
        """
        response = {
            "access_token": "1/fFAGRNJru1FTz70BzhT3Zg",
            "expires_in": 3599,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/youtube.force-ssl",
            "refresh_token": "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI"
            }
        post.side_effect = [namedtuple("Request", ["status_code", "text"])(200, json.dumps(response))]
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  "2020-08-06 17:59:09.103542"}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.get(reverse('google_is_logged'))
        aux_credential = EolGoogleAuth.objects.get(user=self.user)
        new_credentials = json.loads(aux_credential.credentials)
        data = json.loads(result.content.decode())
        self.assertEqual(data['livestream'],False)
        self.assertEqual(data['credentials'],True)
        self.assertEqual(data['channel'],False)
        self.assertNotEqual(new_credentials['expiry'], credentials['expiry'])
        self.assertEqual(new_credentials['token'], '1/fFAGRNJru1FTz70BzhT3Zg')
    
    def test_google_is_logged_not_credentials(self): 
        """
            Test google_is_logged if credential not exists  
        """       
        result = self.client.get(reverse('google_is_logged'))
        data = json.loads(result.content.decode())
        self.assertEqual(data['livestream'],False)
        self.assertEqual(data['credentials'],False)
        self.assertEqual(data['channel'],False)

    @patch("requests.post")
    def test_google_is_logged_error_refresh_token(self, post):
        """
            Test google_is_logged if occur error in get refresh token
        """
        response = {
            "access_token": "1/fFAGRNJru1FTz70BzhT3Zg",
            "expires_in": 3599,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/youtube.force-ssl",
            "refresh_token": "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI"
            }
        post.side_effect = [namedtuple("Request", ["status_code", "text"])(400, json.dumps(response))]
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  "2020-08-06 17:59:09.103542"}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.get(reverse('google_is_logged'))
        aux_credential = EolGoogleAuth.objects.get(user=self.user)
        new_credentials = json.loads(aux_credential.credentials)
        data = json.loads(result.content.decode())
        self.assertEqual(data['livestream'],False)
        self.assertEqual(data['credentials'],False)
        self.assertEqual(data['channel'],False)
        self.assertEqual(new_credentials, credentials)
    
    def test_google_is_logged_datetime_now(self):
        """
            Test google_is_logged with credentials.expiry is not expired
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry': str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.get(reverse('google_is_logged'))
        aux_credential = EolGoogleAuth.objects.get(user=self.user)
        new_credentials = json.loads(aux_credential.credentials)
        data = json.loads(result.content.decode())
        self.assertEqual(data['livestream'],False)
        self.assertEqual(data['credentials'],True)
        self.assertEqual(data['channel'],False)
        self.assertEqual(new_credentials, credentials)

    @patch("requests.post")
    def test_google_is_logged_post(self, post):
        """
            Test google_is_logged if request if post  
        """
        result = self.client.post(reverse('google_is_logged'))
        self.assertEqual(result.status_code, 400)

    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.check_permission_live')
    @patch('eolzoom.youtube_views.check_permission_channels')
    def test_youtube_validate(self, channel, live):
        """
            Test youtube_validate normal process  
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)        
        channel.return_value = {'channel':True,'livestream':False,'credentials': True}
        live.return_value = {'channel':True,'livestream':True,'credentials': True}
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.get(reverse('youtube_validate'))
        data = json.loads(result.content.decode())
        self.assertEqual(data['credentials'],True)
        self.assertEqual(data['channel'],True)
        self.assertEqual(data['livestream'],True)
    
    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.check_permission_live')
    @patch('eolzoom.youtube_views.check_permission_channels')
    def test_youtube_validate_not_channel_live(self, channel, live):
        """
            Test youtube_validate if user dont have channel or live permission  
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        channel.return_value = {'channel':False,'livestream':False,'credentials': True}
        live.return_value = {'channel':False,'livestream':False,'credentials': True}
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.get(reverse('youtube_validate'))
        data = json.loads(result.content.decode())
        self.assertEqual(data['credentials'],True)
        self.assertEqual(data['channel'],False)
        self.assertEqual(data['livestream'],False)
    
    def test_youtube_validate_wrong_token(self):
        """
            Test youtube_validate if credentials.token is wrong 
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.get(reverse('youtube_validate'))
        data = json.loads(result.content.decode())
        self.assertEqual(data['credentials'],False)
        self.assertEqual(data['channel'],False)
        self.assertEqual(data['livestream'],False)
    
    def test_youtube_validate_post(self):
        """
            Test youtube_validate if request is post  
        """
        result = self.client.post(reverse('youtube_validate'))
        self.assertEqual(result.status_code, 400)

    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.update_live_in_youtube')
    def test_update_livebroadcast(self, updt_yt):
        """
            Test update_livebroadcast normal process  
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials), channel_enabled=True, livebroadcast_enabled=True)
        updt_yt.return_value = "09876"
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '12345',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'broadcast_id': '09876'
        }
        result = self.client.post(reverse('url_update_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['id_broadcast'], '09876')
    
    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.update_live_in_youtube')
    def test_update_livebroadcast_wrong_credentials(self, updt_yt):
        """
            Test update_livebroadcast if credential is wrong
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        updt_yt.return_value = None
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '12345',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'broadcast_id': '09876'
        }
        result = self.client.post(reverse('url_update_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')
    
    def test_update_livebroadcast_no_params(self):
        """
            Test update_livebroadcast if request dont have params  
        """
        result = self.client.post(reverse('url_update_livebroadcast'))
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')
    
    def test_update_livebroadcast_no_yt(self):
        """
            Test update_livebroadcast if fail create youtube objects
        """
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '12345',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'broadcast_id': '09876'
        }
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.post(reverse('url_update_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')

    def test_update_livebroadcast_no_yt_no_credential(self):
        """
            Test update_livebroadcast if creadentails is not setted 
        """
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '12345',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'broadcast_id': '09876'
        }     
        result = self.client.post(reverse('url_update_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')    
    
    def test_update_livebroadcast_get(self):
        """
            Test update_livebroadcast if request is get  
        """
        result = self.client.get(reverse('url_update_livebroadcast'))
        self.assertEqual(result.status_code, 400)
    
    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.create_live_in_youtube')
    @patch("requests.patch")
    @patch("requests.post")
    def test_create_livebroadcast(self, post, patch, stream_dict):
        """
            Test create_livebroadcast normal process  
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials), channel_enabled=True, livebroadcast_enabled=True)
        EolZoomAuth.objects.create(user=self.user, zoom_refresh_token='test_refresh_token')
        stream_dict.return_value = {
            "id":"09876",
            "stream_key": "this-is-a-stream-key",
            "stream_server": "a-stream-server",
            'broadcast_id': "12345"
        }
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        patch.side_effect = [namedtuple("Request", ["status_code",])(204,), ]
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '676767',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'restricted_access': 'false'
        }
        result = self.client.post(reverse('url_new_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['id_broadcast'], '12345')
    
    def test_create_livebroadcast_no_params(self):
        """
            Test create_livebroadcast if request dont have params  
        """
        result = self.client.post(reverse('url_new_livebroadcast'))
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')
    
    def test_create_livebroadcast_no_yt(self):
         """
            Test create_livebroadcast if fail create youtube objects
        """
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '676767',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'restricted_access': 'false'
        }
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        result = self.client.post(reverse('url_new_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')

    def test_create_livebroadcast_no_yt_no_credential(self):
        """
            Test create_livebroadcast if creadentails is not setted 
        """
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '676767',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'restricted_access': 'false'
        }
        result = self.client.post(reverse('url_new_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')
    
    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.create_live_in_youtube')
    def test_create_livebroadcast_fail_live(self, stream_dict):
        """
            Test create_livebroadcast if fail in create live on youtube  
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        EolZoomAuth.objects.create(user=self.user, zoom_refresh_token='test_refresh_token')
        stream_dict.return_value = None
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '676767',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'restricted_access': 'false'
        }
        result = self.client.post(reverse('url_new_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')
    
    @override_settings(GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com')
    @override_settings(GOOGLE_CLIENT_SECRET = '1234567890asdfgh')
    @patch('eolzoom.youtube_views.create_live_in_youtube')
    @patch("requests.patch")
    @patch("requests.post")
    def test_create_livebroadcast_fail_update_meeting_zoom(self, post, patch, stream_dict):
        """
            Test create_livebroadcast if fail update status livestream in zoom meeting 
        """
        new_expiry = dt.now() + datetime.timedelta(seconds=3600)
        credentials = {
            'token': "this-is-a-token",
            'refresh_token': "1//xEoDL4iW3cxlI7yDbSRFYNG01kVKM2C-259HOF2aQbI",
            'token_uri': "https://www.googleapis.com/oauth2/v3/token",
            'scopes': ["https://www.googleapis.com/auth/youtube.force-ssl"],
            'expiry':  str(new_expiry)}
        EolGoogleAuth.objects.create(user=self.user,credentials=json.dumps(credentials))
        EolZoomAuth.objects.create(user=self.user, zoom_refresh_token='test_refresh_token')
        stream_dict.return_value = {
            "id":"09876",
            "stream_key": "this-is-a-stream-key",
            "stream_server": "a-stream-server",
            'broadcast_id': "12345"
        }
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        patch.side_effect = [namedtuple("Request", ["status_code",])(400,), ]
        post_data = {
            'display_name': 'display_name',
            'meeting_id': '676767',
            'date': '2020-10-10',
            'time': '10:10',
            'duration': '40',
            'restricted_access': 'false'
        }
        result = self.client.post(reverse('url_new_livebroadcast'), post_data)
        data = json.loads(result.content.decode())
        self.assertEqual(data['status'], 'error')
    
    def test_create_livebroadcast_get(self):
        """
            Test create_livebroadcast if request is get
        """
        result = self.client.get(reverse('url_new_livebroadcast'))        
        self.assertEqual(result.status_code, 400)
    
    @override_settings(EOLZOOM_AUTHORIZATION = '1234567890asdfgh')
    @patch("requests.patch")
    @patch("requests.post")
    def test_event_zoom_youtube(self, post, patch):
        """
            Test event_zoom_youtube normal process  
        """
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        patch.side_effect = [namedtuple("Request", ["status_code",])(204,), ]
        headers={'Authorization': 'Bearer 1234567890asdfgh'}
        post_data = {
            "event": "meeting.started",
            "payload": {
                "account_id": "o8KK_AAACq6BBEyA70CA",
                "object": {
                    "id": "1234",
                    "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
                    }
                }
            }
        EolZoomAuth.objects.create(user=self.user, zoom_refresh_token='test_refresh_token')
        EolZoomMappingUserMeet.objects.create(meeting_id="1234", user=self.user)
        request = TestRequest()
        request.method = 'POST'
        data = json.dumps(post_data)
        request.body = data
        request.headers = headers
        request.params = post_data
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 200)
    
    @override_settings(EOLZOOM_AUTHORIZATION = '1234567890asdfgh')
    def test_event_zoom_youtube_wrong_authorization(self):
        """
            Test event_zoom_youtube if authorization is wrong  
        """
        headers={'Authorization': 'Bearer wrong1234567890asdfgh'}
        post_data = {
            "event": "meeting.started",
            "payload": {
                "account_id": "o8KK_AAACq6BBEyA70CA",
                "object": {
                    "id": "1234",
                    "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
                    }
                }
            }
        request = TestRequest()
        request.method = 'POST'
        data = json.dumps(post_data)
        request.body = data
        request.headers = headers
        request.params = post_data
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 400)
    
    @override_settings(EOLZOOM_AUTHORIZATION = '1234567890asdfgh')
    def test_event_zoom_youtube_wrong_event(self):
        """
            Test event_zoom_youtube if event is not 'meeting.started'
        """
        headers={'Authorization': 'Bearer 1234567890asdfgh'}
        post_data = {
            "event": "meeting.ended",
            "payload": {
                "account_id": "o8KK_AAACq6BBEyA70CA",
                "object": {
                    "id": "1234",
                    "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
                    }
                }
            }
        request = TestRequest()
        request.method = 'POST'
        data = json.dumps(post_data)
        request.body = data
        request.headers = headers
        request.params = post_data
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 400)
    
    @override_settings(EOLZOOM_AUTHORIZATION = '1234567890asdfgh')
    def test_event_zoom_youtube_meet_not_exists(self):
        """
            Test event_zoom_youtube if meeting dont exists  
        """
        headers={'Authorization': 'Bearer 1234567890asdfgh'}
        post_data = {
            "event": "meeting.started",
            "payload": {
                "account_id": "o8KK_AAACq6BBEyA70CA",
                "object": {
                    "id": "1234",
                    "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
                    }
                }
            }
        EolZoomMappingUserMeet.objects.create(meeting_id="098765", user=self.user)
        request = TestRequest()
        request.method = 'POST'
        data = json.dumps(post_data)
        request.body = data
        request.headers = headers
        request.params = post_data
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 400)
    
    @override_settings(EOLZOOM_AUTHORIZATION = '1234567890asdfgh')
    @patch("requests.post")
    def test_event_zoom_youtube_fail_access_token(self, post):
        """
            Test event_zoom_youtube if fail get access token from zoom
        """
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                400, lambda:response), ]
        patch.side_effect = [namedtuple("Request", ["status_code",])(204,), ]
        headers={'Authorization': 'Bearer 1234567890asdfgh'}
        post_data = {
            "event": "meeting.started",
            "payload": {
                "account_id": "o8KK_AAACq6BBEyA70CA",
                "object": {
                    "id": "1234",
                    "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
                    }
                }
            }
        EolZoomAuth.objects.create(user=self.user, zoom_refresh_token='test_refresh_token')
        EolZoomMappingUserMeet.objects.create(meeting_id="1234", user=self.user)
        request = TestRequest()
        request.method = 'POST'
        data = json.dumps(post_data)
        request.body = data
        request.headers = headers
        request.params = post_data
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 400)

    @override_settings(EOLZOOM_AUTHORIZATION = '1234567890asdfgh')
    @patch("requests.patch")
    @patch("requests.post")
    def test_event_zoom_youtube_fail_start_live(self, post, patch):
        """
            Test event_zoom_youtube if fail update status livestream in zoom meeting 
        """
        response = {
            "access_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjE1ODAxNTA1OTMsInRva2VuVHlwZSI6ImFjY2Vzc190b2tlbiIsImlhdCI6MTU4MDE0Njk5MywianRpIjoiPEpUST4iLCJ0b2xlcmFuY2VJZCI6MjV9.F9o_w7_lde4Jlmk_yspIlDc-6QGmVrCbe_6El-xrZehnMx7qyoZPUzyuNAKUKcHfbdZa6Q4QBSvpd6eIFXvjHw",
            "token_type": "bearer",
            "refresh_token": "eyJhbGciOiJIUzUxMiIsInYiOiIyLjAiLCJraWQiOiI8S0lEPiJ9.eyJ2ZXIiOiI2IiwiY2xpZW50SWQiOiI8Q2xpZW50X0lEPiIsImNvZGUiOiI8Q29kZT4iLCJpc3MiOiJ1cm46em9vbTpjb25uZWN0OmNsaWVudGlkOjxDbGllbnRfSUQ-IiwiYXV0aGVudGljYXRpb25JZCI6IjxBdXRoZW50aWNhdGlvbl9JRD4iLCJ1c2VySWQiOiI8VXNlcl9JRD4iLCJncm91cE51bWJlciI6MCwiYXVkIjoiaHR0cHM6Ly9vYXV0aC56b29tLnVzIiwiYWNjb3VudElkIjoiPEFjY291bnRfSUQ-IiwibmJmIjoxNTgwMTQ2OTkzLCJleHAiOjIwNTMxODY5OTMsInRva2VuVHlwZSI6InJlZnJlc2hfdG9rZW4iLCJpYXQiOjE1ODAxNDY5OTMsImp0aSI6IjxKVEk-IiwidG9sZXJhbmNlSWQiOjI1fQ.Xcn_1i_tE6n-wy6_-3JZArIEbiP4AS3paSD0hzb0OZwvYSf-iebQBr0Nucupe57HUDB5NfR9VuyvQ3b74qZAfA",
            "expires_in": 3599,
            "scope": "user:read:admin"
        }
        post.side_effect = [
            namedtuple(
                "Request", [
                    "status_code", "json"])(
                200, lambda:response), ]
        patch.side_effect = [namedtuple("Request", ["status_code",])(400,), ]
        headers={'Authorization': 'Bearer 1234567890asdfgh'}
        post_data = {
            "event": "meeting.started",
            "payload": {
                "account_id": "o8KK_AAACq6BBEyA70CA",
                "object": {
                    "id": "1234",
                    "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
                    }
                }
            }
        EolZoomAuth.objects.create(user=self.user, zoom_refresh_token='test_refresh_token')
        EolZoomMappingUserMeet.objects.create(meeting_id="1234", user=self.user)
        request = TestRequest()
        request.method = 'POST'
        data = json.dumps(post_data)
        request.body = data
        request.headers = headers
        request.params = post_data
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 400)
    
    def test_event_zoom_youtube_get(self):
        """
            Test event_zoom_youtube if request is get 
        """
        request = TestRequest()
        request.method = 'GET'
        result = youtube_views.event_zoom_youtube(request)
        self.assertEqual(result.status_code, 400)