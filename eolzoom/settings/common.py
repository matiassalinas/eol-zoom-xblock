""" Common settings for eol zoom. """
import base64

def plugin_settings(settings):
    settings.EOLZOOM_ROOT = None
    settings.EOLZOOM_CLIENT_ID = 'zc2c98XCRSvPejJtUf8OQ'
    settings.EOLZOOM_CLIENT_SECRET = 'U7159FQsZYkZyPCi5O5qoy0p21HyDoCy'
    settings.EOLZOOM_AUTHORIZATION = base64.b64encode('{}:{}'.format(settings.EOLZOOM_CLIENT_ID, settings.EOLZOOM_CLIENT_SECRET))