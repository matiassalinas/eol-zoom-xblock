# -*- coding: utf-8 -*-


from django.contrib import admin

from .models import EolZoomAuth, EolZoomRegistrant

admin.site.register(EolZoomAuth)
admin.site.register(EolZoomRegistrant)
