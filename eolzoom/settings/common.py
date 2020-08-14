""" Common settings for eol zoom. """
import base64


def plugin_settings(settings):
    settings.EOLZOOM_CLIENT_ID = ''
    settings.EOLZOOM_CLIENT_SECRET = ''
    settings.EOLZOOM_AUTHORIZATION = ''
    settings.EOLZOOM_DOMAIN = ''
    settings.GOOGLE_CLIENT_ID = '598549087302-pkunglevko6llqrqvhlhpfki2oq8845t.apps.googleusercontent.com'
    settings.GOOGLE_PROJECT_ID = 'zoom-to-youtube-eol'
    settings.GOOGLE_CLIENT_SECRET = 'F8AzN7sCDdknY2z1M-qayGBa'
    settings.GOOGLE_REDIRECT_URIS = ["https://studio.luis.msalinas.cl/zoom/callback_google_auth"]
    settings.GOOGLE_JAVASCRIPT_ORIGINS = ["https://studio.luis.msalinas.cl"]