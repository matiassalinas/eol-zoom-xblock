# -*- coding: utf-8 -*-


from django.contrib import admin

from .models import EolZoomAuth, EolZoomRegistrant, EolGoogleAuth, EolZoomMappingUserMeet

admin.site.register(EolZoomAuth)
admin.site.register(EolGoogleAuth)
admin.site.register(EolZoomMappingUserMeet)
admin.site.register(EolZoomRegistrant)
