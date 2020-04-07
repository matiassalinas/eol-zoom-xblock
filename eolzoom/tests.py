# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from openedx.core.lib.tests.tools import assert_true
from mock import patch, Mock

from collections import namedtuple

import json

from django.test import TestCase, Client
from django.urls import reverse

from util.testing import UrlResetMixin
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase

from xmodule.modulestore.tests.factories import CourseFactory
from student.tests.factories import UserFactory, CourseEnrollmentFactory
from xblock.field_data import DictFieldData
from student.roles import CourseStaffRole

from .eolzoom import EolZoomXBlock

import views
from models import EolZoomAuth

import logging
logger = logging.getLogger(__name__)


class TestRequest(object):
    # pylint: disable=too-few-public-methods
    """
    Module helper for @json_handler
    """
    method = None
    body = None
    success = None
    params = None


class TestEolZoomAPI(UrlResetMixin, ModuleStoreTestCase):
    def setUp(self):

        super(TestEolZoomAPI, self).setUp()

        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            uname = 'student'
            email = 'student@edx.org'
            password = 'test'

            # Create the user
            self.user = UserFactory(
                username=uname, password=password, email=email)

            # Log the user in
            self.client = Client()
            assert_true(self.client.login(username=uname, password=password))

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
            "join_url": 'join_url_example'
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
            'duration': '40'
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
            'meeting_id': 'meeting_id'
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
            'redirect': 'https://eol.uchile.cl/'
        }
        response = self.client.get(reverse('zoom_api'), get_data)
        self.assertEqual(response.status_code, 302)


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
        )
        scope_ids = Mock()
        field_data = DictFieldData(kw)
        xblock = EolZoomXBlock(runtime, field_data, scope_ids)
        xblock.xmodule_runtime = runtime
        xblock.location = course.id  # Example of location
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
            assert_true(self.client.login(username=uname, password=password))

            # Log the user staff in
            self.staff_client = Client()
            assert_true(
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
        self.assertEqual(self.xblock.description, None)
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
            1. Staff user
            2. Student user
        """
        self.xblock.meeting_id = 'meeting_id'
        self.xblock.date = '2020-12-26'
        self.xblock.time = '23:32'
        self.xblock.description = 'description'
        self.xblock.duration = 120
        self.xblock.created_by = self.staff_user.id
        self.xblock.created_location = self.xblock.location._to_string()
        self.xblock.start_url = "start_url_example"
        self.xblock.join_url = "join_url_example"

        # 1. Staff user
        self.xblock.runtime.user_is_staff = True
        student_staff_view = self.xblock.student_view()
        student_staff_view_html = student_staff_view.content
        self.assertNotIn('class="eolzoom_error"', student_staff_view_html)
        self.assertIn('class="button button-green"',
                      student_staff_view_html)  # 'Iniciar Transmision' button
        self.assertIn('class="button button-blue"',
                      student_staff_view_html)  # 'Ingresar a la sala' button

        # 2. Student user
        self.xblock.runtime.user_is_staff = False
        student_view = self.xblock.student_view()
        student_view_html = student_view.content
        self.assertNotIn('class="eolzoom_error"', student_view_html)
        self.assertNotIn('class="button button-green"',
                         student_view_html)  # 'Iniciar Transmision' button
        self.assertIn('class="button button-blue"',
                      student_view_html)  # 'Ingresar a la sala' button

    def test_author_view(self):
        """
            Test author view:
            1. Without Configurations
            2. Load correct html
            3. With Configurations
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
        self.xblock.created_by = self.staff_user.id
        self.xblock.created_location = self.xblock.location._to_string()
        self.xblock.start_url = "start_url_example"
        self.xblock.join_url = "join_url_example"

        author_view = self.xblock.student_view()
        author_view_html = author_view.content
        self.assertNotIn('class="eolzoom_error"', author_view_html)
        self.assertIn('class="button button-green"',
                      author_view_html)  # 'Iniciar Transmision' button
        self.assertIn('class="button button-blue"',
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
            'created_by': self.staff_user.id,
            'created_location': self.xblock.location._to_string(),
            'start_url': 'start_url_example',
            'join_url': 'join_url_example'
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
        self.assertEqual(self.xblock.created_by, self.staff_user.id)
        self.assertEqual(
            self.xblock.created_location,
            self.xblock.location._to_string())
