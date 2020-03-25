import pkg_resources

from django.template import Context, Template
from django.urls import reverse
from django.conf import settings as DJANGO_SETTINGS

from webob import Response


import logging
logger = logging.getLogger(__name__)

import requests
import json

from xblock.core import XBlock
from xblock.fields import Integer, Scope, String, DateTime
from xblock.fragment import Fragment
from xblockutils.studio_editable import StudioEditableXBlockMixin


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
        "Indica la hora de la videollamada (en formato HH:MM. Ejemplo: 14:30)"))

    description = String(
        display_name=_("Descripcion"),
        scope=Scope.settings,
        help=_("Indica una breve descripcion de la videollamada")
    )

    duration = Integer(
        display_name=_("Duracion"),
        default=40,
        scope=Scope.settings,
        help=_("Duracion de la videollamada")
    )

    created_by = String(
        display_name=_("Created By"),
        scope=Scope.settings,
    )

    has_author_view = True

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        context_html = self.get_context()
        template = self.render_template(
            'static/html/eolzoom.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/eolzoom.js"))
        frag.initialize_js('EolZoomXBlock')
        return frag

    def studio_view(self, context=None):
        context_html = self.get_context()
        template = self.render_template(
            'static/html/studio.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))

        settings = {
            'meeting_id': self.meeting_id,
            'created_by': self.created_by,
            'url_is_logged_zoom': reverse('is_logged_zoom'),
            'url_login': reverse('zoom_api'),
            'url_zoom_api': 'https://zoom.us/oauth/authorize?response_type=code&client_id={}&redirect_uri='.format(
                DJANGO_SETTINGS.EOLZOOM_CLIENT_ID),
            'url_new_meeting': reverse('new_scheduled_meeting'),
            'url_update_meeting': reverse('update_scheduled_meeting'),
        }
        frag.initialize_js('EolZoomStudioXBlock', json_args=settings)
        return frag

    def author_view(self, context=None):
        context_html = self.get_context()
        template = self.render_template(
            'static/html/author_view.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        return frag

    def get_context(self):
        # Status: false (at least one attribute is empty), true (all attributes
        # have content)
        status = self.get_status()
        return {
            'xblock': self,
            'zoom_logo_path': self.runtime.local_resource_url(
                self,
                "static/images/ZoomLogo.png"),
            'status': status,
            'is_course_staff': getattr(self.xmodule_runtime, 'user_is_staff', False),
        }

    def render_template(self, template_path, context):
        template_str = self.resource_string(template_path)
        template = Template(template_str)
        return template.render(Context(context))

    @XBlock.handler
    def studio_submit(self, request, suffix=''):
        self.display_name = request.params['display_name']
        self.description = request.params['description']
        self.date = request.params['date']
        self.time = request.params['time']
        self.duration = request.params['duration']
        self.created_by = request.params['created_by']
        self.meeting_id = request.params['meeting_id']
        return Response(json.dumps({'result': 'success'}),
                        content_type='application/json')

    def get_status(self):
        """
            Return false if at least one attribute is empty
        """
        return not (
            is_empty(self.display_name) or
            is_empty(self.meeting_id) or
            is_empty(self.date) or
            is_empty(self.time) or
            is_empty(self.description) or
            is_empty(self.duration) or
            is_empty(self.created_by)
        )

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
