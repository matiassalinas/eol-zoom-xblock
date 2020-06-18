# -*- coding: utf-8 -*-


from django.apps import AppConfig
from openedx.core.djangoapps.plugins.constants import PluginSettings, PluginURLs, ProjectType, SettingsType


class EolZoomConfig(AppConfig):
    name = 'eolzoom'

    plugin_app = {
        PluginURLs.CONFIG: {
            ProjectType.LMS: {
                PluginURLs.NAMESPACE: '',
                PluginURLs.REGEX: r'^',
                PluginURLs.RELATIVE_PATH: 'urls',
            },
            ProjectType.CMS: {
                PluginURLs.NAMESPACE: '',
                PluginURLs.REGEX: r'^',
                PluginURLs.RELATIVE_PATH: 'urls_cms',
            }
        },
        PluginSettings.CONFIG: {
            ProjectType.CMS: {
                SettingsType.COMMON: {
                    PluginSettings.RELATIVE_PATH: 'settings.common'},
            },
            ProjectType.LMS: {
                SettingsType.COMMON: {
                    PluginSettings.RELATIVE_PATH: 'settings.common'},
            },
        }}

    def ready(self):
        pass
