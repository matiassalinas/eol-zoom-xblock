import pkg_resources

from django.template import Context, Template

from xblock.core import XBlock
from xblock.fields import Integer, Scope, String, DateTime
from xblock.fragment import Fragment
from xblockutils.studio_editable import StudioEditableXBlockMixin


# Make '_' a no-op so we can scrape strings
_ = lambda text: text

class EolZoomXBlock(XBlock):

    display_name = String(
        display_name=_("Titulo"),
        help=_("Ingresa un titulo para la videollamada"),
        default="Eol Zoom XBlock",
        scope=Scope.settings,
    )

    icon_class = String(
        default="other",
        scope=Scope.settings,
    )

    url = String(
        display_name=_("Enlace Zoom"),
        scope=Scope.settings,
        help=_("Indica el enlace/url de la videollamada creada en Zoom")
    )

    date = DateTime(
        display_name=_("Fecha"), 
        scope=Scope.settings,
        help=_("Indica la fecha programada de la videollamada")
    )

    time = String(
        display_name=_("Hora"),
        scope=Scope.settings,
        help=_("Indica la hora de la videollamada (en formato HH:MM. Ejemplo: 14:30)")
    )

    description = String(
        display_name=_("Descripcion"),
        scope=Scope.settings,
        help=_("Indica una breve descripcion de la videollamada")
    )

    has_author_view = True

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        context_html = self.get_context()
        template = self.render_template('static/html/eolzoom.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/eolzoom.js"))
        frag.initialize_js('EolZoomXBlock')
        return frag
        
    def studio_view(self, context=None):
        context_html = self.get_context()
        template = self.render_template('static/html/studio.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.initialize_js('EolZoomStudioXBlock')
        return frag


    def author_view(self, context=None):
        context_html = self.get_context()
        template = self.render_template('static/html/author_view.html', context_html)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/eolzoom.css"))
        return frag

    def get_context(self):
        status = self.get_status() # Status: false (at least one attribute is empty), true (all attributes have content)
        return {
            'xblock': self,
            'zoom_logo_path' : self.runtime.local_resource_url(self, "static/images/ZoomLogo.png"),
            'status' : status
        }

    def render_template(self, template_path, context):
        template_str = self.resource_string(template_path)
        template = Template(template_str)
        return template.render(Context(context))

    def get_status(self):
        """
            Return false if at least one attribute is empty
        """
        return not (
            is_empty(self.display_name) or
            is_empty(self.url) or
            is_empty(self.date) or
            is_empty(self.time) or
            is_empty(self.description)
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
    return attr == "" or attr == None