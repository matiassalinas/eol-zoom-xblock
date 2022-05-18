import pkg_resources

from django.template import Context, Template
from django.urls import reverse
from django.conf import settings as DJANGO_SETTINGS

from webob import Response


import logging
logger = logging.getLogger(__name__)

import requests
import json
from six import text_type

from xblock.core import XBlock
from xblock.fields import Integer, Scope, String, DateTime, Boolean
from xblock.fragment import Fragment
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.theming.helpers import get_current_request
# Make '_' a no-op so we can scrape strings


def _(text): return text


class EolZoomXBlock(XBlock):

    display_name = String(
        display_name=_("Titulo"),
        help=_("Ingresa un titulo para la videollamada"),
        default="Videollamada Zoom",
        scope=Scope.settings,
    )

    meeting_id = String(
        display_name=_("Meeting ID"),
        scope=Scope.settings,
    )

    start_url = String(
        display_name=_("URL Start Meeting"),
        scope=Scope.settings,
    )

    join_url = String(
        display_name=_("URL Join Meeting"),
        scope=Scope.settings,
    )

    icon_class = String(
        default="other",
        scope=Scope.settings,
    )

    date = String(
        display_name=_("Fecha"),
        scope=Scope.settings,
        help=_("Indica la fecha programada de la videollamada")
    )

    time = String(display_name=_("Hora"), scope=Scope.settings, help=_(
        "Indica la hora de la videollamada"))

    description = String(
        display_name=_("Descripcion"),
        scope=Scope.settings,
        help=_("Indica una breve descripcion de la videollamada"),
        default="",
    )

    duration = Integer(
        display_name=_("Duracion"),
        default=40,
        scope=Scope.settings,
        help=_("Duracion de la videollamada")
    )

    # Zoom e-mail
    created_by = String(
        display_name=_("Created By"),
        scope=Scope.settings,
    )

    # EDX User ID
    edx_created_by = Integer(
        display_name=_("Host Username"),
        scope=Scope.settings,
    )

    created_location = String(
        display_name=_("XBlock Location when Meet is Created"),
        scope=Scope.settings,
    )

    restricted_access = Boolean(
        display_name=_("Acceso restringido"),
        default=False,
        scope=Scope.settings,
        help=_("Solo estudiantes inscritos en el curso podran acceder a esta videollamada.")
    )

    email_notification = Boolean(
        display_name=_("Notificación por Correo"),
        default=False,
        scope=Scope.settings,
        help=_("Los estudiantes recibirán una notificación por correo electrónico al iniciar la transmisión.")
    )

    google_access = Boolean(
        display_name=_("Youtube Livestream"),
        default=False,
        scope=Scope.settings,
        help=_("Permite transmitir la reunion de zoom por Youtube")
    )
    broadcast_id = String(
        display_name=_("broadcast_id"),
        scope=Scope.settings,
        default=""
    )
    meeting_password = String(
        display_name=_("Meeting Password"),
        scope=Scope.settings,
    )

    has_author_view = True

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        context_html = self.get_context(is_lms=True)
        template = self.render_template(
            'static/html/eolzoom.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/eolzoom.js"))
        settings = {
            'meeting_id': self.meeting_id,
            'block_id': self.location,
            'course_id': text_type(
                self.xmodule_runtime.course_id),
            'email_notification' : self.email_notification,
            'url_start_public_meeting':reverse(
                'start_public_meeting',
                    kwargs={
                        'email_notification':self.email_notification,
                        'meeting_id': self.meeting_id,
                        'block_id': self.location,
                        'restricted_access': self.restricted_access
                    }
            ),
            'url_start_meeting': reverse('start_meeting'),
            'get_student_join_url': reverse('get_student_join_url'),
            'restricted_access': self.restricted_access,
            'url_zoom_api': '{}oauth/authorize?response_type=code&client_id={}&redirect_uri='.format(
                DJANGO_SETTINGS.EOLZOOM_DOMAIN,
                DJANGO_SETTINGS.EOLZOOM_CLIENT_ID),
        }
        frag.initialize_js('EolZoomXBlock', json_args=settings)
        return frag

    def studio_view(self, context=None):
        context_html = self.get_context()
        myrequest = get_current_request()
        context_html['user_id'] = myrequest.user.id
        template = self.render_template(
            'static/html/studio.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        enrolled_students = self.get_students_count(
            text_type(self.scope_ids.usage_id.course_key))

        settings = {
            'meeting_id': self.meeting_id,
            'enrolled_students': enrolled_students,
            'created_by': self.created_by,
            'edx_created_by': self.edx_created_by,
            'user_id': myrequest.user.id,
            'course_id': text_type(self.scope_ids.usage_id.course_key),
            'block_id': self.location,
            'start_url': self.start_url,
            'join_url': self.join_url,
            'restricted_access': self.restricted_access,
            'google_access': self.google_access,
            'url_google_auth': reverse('auth_google'),
            'url_is_logged_google': reverse('google_is_logged'),
            'url_youtube_validate': reverse('youtube_validate'),
            'broadcast_id': self.broadcast_id,
            'url_is_logged_zoom': reverse('is_logged_zoom'),
            'url_login': reverse('zoom_api'),
            'url_zoom_api': '{}oauth/authorize?response_type=code&client_id={}&redirect_uri='.format(
                DJANGO_SETTINGS.EOLZOOM_DOMAIN,
                DJANGO_SETTINGS.EOLZOOM_CLIENT_ID),
            'url_new_meeting': reverse('new_scheduled_meeting'),
            'url_new_livebroadcast': reverse('url_new_livebroadcast'),
            'url_update_livebroadcast': reverse('url_update_livebroadcast'),
            'url_update_meeting': reverse('update_scheduled_meeting'),
        }
        frag.initialize_js('EolZoomStudioXBlock', json_args=settings)
        return frag 

    def author_view(self, context=None):
        context_html = self.get_context()
        if self.google_access and self.broadcast_id != "":
            context_html['broadcast_id'] = self.get_broadcast_id()
        else:
            context_html['broadcast_id'] = []
        template = self.render_template(
            'static/html/author_view.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/author.js"))

        settings = {
            'meeting_id': self.meeting_id,
            'block_id': self.location,
            'course_id': text_type(
                self.xmodule_runtime.course_id),
            'email_notification': self.email_notification,
            'url_start_public_meeting':reverse(
                'start_public_meeting',
                    kwargs={
                        'email_notification':self.email_notification,
                        'meeting_id': self.meeting_id,
                        'block_id': self.location,
                        'restricted_access': self.restricted_access
                    }
            ),
            'url_start_meeting': reverse('start_meeting'),
            'get_student_join_url': reverse('get_student_join_url'),
            'restricted_access': self.restricted_access,
            'url_zoom_api': '{}oauth/authorize?response_type=code&client_id={}&redirect_uri='.format(
                DJANGO_SETTINGS.EOLZOOM_DOMAIN,
                DJANGO_SETTINGS.EOLZOOM_CLIENT_ID),
        }
        frag.initialize_js('EolZoomAuthorXBlock', json_args=settings)
        return frag

    def get_students_count(self, course_id):
        """
        Get a count of all students enrolled to course
        """
        from common.djangoapps.student.models import CourseEnrollment
        course_key = CourseKey.from_string(course_id)
        students = CourseEnrollment.objects.filter(
            course_id=course_key,
            is_active=1
        ).count()
        return students
    
    def get_broadcast_id(self):
        from .models import EolZoomMappingUserMeet
        try:
            user_model = EolZoomMappingUserMeet.objects.get(meeting_id=self.meeting_id)
            if user_model.broadcast_ids == "":
                return []
            broadcast_ids = user_model.broadcast_ids.split(" ")
            complete_url = ["https://youtu.be/{}".format(x) for x in broadcast_ids]
            return complete_url
        except EolZoomMappingUserMeet.DoesNotExist:
            return []

    def get_context(self, is_lms=False):
        # Status: false (at least one attribute is empty), true (all attributes
        # have content)
        status = self.get_status(is_lms)
        return {
            'xblock': self,
            'user_id': self.runtime.user_id,
            'EOLZOOM_DOMAIN': DJANGO_SETTINGS.EOLZOOM_DOMAIN,
            'zoom_logo_path': self.runtime.local_resource_url(
                self,
                "static/images/ZoomLogo.png"),
            'status': status,
            'is_course_staff': getattr(
                self.xmodule_runtime,
                'user_is_staff',
                False),
        }

    def render_template(self, template_path, context):
        template_str = self.resource_string(template_path)
        template = Template(template_str)
        return template.render(Context(context))

    @XBlock.handler
    def studio_submit(self, request, suffix=''):
        myrequest = get_current_request()
        self.display_name = request.params['display_name']
        self.description = request.params['description']
        self.date = request.params['date']
        self.time = request.params['time']
        self.duration = request.params['duration']
        self.created_by = request.params['created_by']
        self.meeting_id = request.params['meeting_id']
        self.start_url = request.params['start_url']
        self.join_url = request.params['join_url']
        self.restricted_access = request.params['restricted_access']
        self.email_notification = request.params['email_notification']
        self.google_access = request.params['google_access']
        self.broadcast_id = request.params['broadcast_id']
        self.meeting_password = request.params['meeting_password']
        self.created_location = self.location._to_string()
        self.edx_created_by = myrequest.user.id
        return Response({'result': 'success'})

    def get_status(self, is_lms):
        """
            Return false if at least one attribute is empty
        """
        return not (
            is_empty(self.check_location(is_lms)) or
            is_empty(self.display_name) or
            is_empty(self.start_url) or
            is_empty(self.join_url) or
            is_empty(self.meeting_id) or
            is_empty(self.date) or
            is_empty(self.time) or
            #is_empty(self.description) or
            is_empty(self.duration) or
            is_empty(self.created_by) or
            (self.google_access and is_empty(self.broadcast_id))
        )

    def check_location(self, is_lms):
        """
            Check if created_location is the same of the actual location of the XBlock
            Clear 'meeting_id', 'created_by and 'created_location'
            When re-run a course will enforce new configuration
        """
        if(self.created_location != self.location._to_string()):
            # Can't make changes in lms (only read mode)
            if is_lms:
                return None
            self.created_location = None
            self.meeting_id = None
            self.created_by = None
        return self.created_location

    @classmethod
    def parse_xml(cls, node, runtime, keys, id_generator):
        """
            Override default serialization at Course Export
            Clear 'meeting_id' and 'created_by' attributes (force to configure and start new meetings)
        """
        block = runtime.construct_xblock_from_class(cls, keys)

        for name, value in list(node.items()):  # lxml has no iteritems
            if(name != 'meeting_id' and name != 'created_by' and name != 'created_location'):
                cls._set_field_if_present(block, name, value, {})

        return block

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("EolZoomXBlock",
             """<eolzoom/>
             """),
        ]


def is_empty(attr):
    """
        check if attribute is empty or None
    """
    return attr == "" or attr is None
