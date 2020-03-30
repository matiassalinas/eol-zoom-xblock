# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from openedx.core.lib.tests.tools import assert_true
from mock import patch, Mock


from django.test import TestCase, Client
from django.urls import reverse

from util.testing import UrlResetMixin
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase

from xmodule.modulestore.tests.factories import CourseFactory
from student.tests.factories import UserFactory, CourseEnrollmentFactory

import views
from models import EolZoomAuth

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

            # Create the student
            self.student = UserFactory(username=uname, password=password, email=email)

            # Enroll the student in the course
            CourseEnrollmentFactory(user=self.student, course_id=self.course.id)

            # Log the student in
            self.client = Client()
            assert_true(self.client.login(username=uname, password=password))

            # Create refresh_token
            EolZoomAuth.objects.create(
                user=self.student,
                zoom_refresh_token='test_refresh_token'
            )
    
    def test_get_refresh_token_from_models(self):
        """
            Test get refresh token with two student
            First student with refresh token
            Second student without refresh token
        """
        refresh_token = views._get_refresh_token(self.student)
        self.assertEqual(refresh_token, 'test_refresh_token')

        new_student = UserFactory(username='test_student', password='test_password', email='test_email@email.email')
        new_refresh_token = views._get_refresh_token(new_student)
        self.assertEqual(new_refresh_token, None)