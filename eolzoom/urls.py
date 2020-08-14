

from django.conf.urls import url
from django.conf import settings

from .views import zoom_api, new_scheduled_meeting, is_logged_zoom, update_scheduled_meeting, start_meeting, get_student_join_url
from .youtube_views import google_is_logged, auth_google, callback_google_auth, create_livebroadcast, youtube_validate, update_livebroadcast, event_zoom_youtube

from django.contrib.auth.decorators import login_required

urlpatterns = (
    url(
        r'^zoom/api',
        login_required(zoom_api),
        name='zoom_api',
    ),
    url(
        r'^zoom/is_logged',
        login_required(is_logged_zoom),
        name='is_logged_zoom',
    ),
    url(
        r'^zoom/new_scheduled_meeting$',
        login_required(new_scheduled_meeting),
        name='new_scheduled_meeting',
    ),
    url(
        r'^zoom/update_scheduled_meeting$',
        login_required(update_scheduled_meeting),
        name='update_scheduled_meeting',
    ),
    url(
        r'^zoom/start_meeting',
        login_required(start_meeting),
        name='start_meeting',
    ),
    url(
        r'^zoom/get_student_join_url',
        login_required(get_student_join_url),
        name='get_student_join_url',
    ),    
    url(
        r'^zoom/new_scheduled_meeting$',
        login_required(new_scheduled_meeting),
        name='new_scheduled_meeting',
    ),
    url(
        r'^zoom/update_scheduled_meeting$',
        login_required(update_scheduled_meeting),
        name='update_scheduled_meeting',
    ),
    url(
        r'^zoom/start_meeting',
        login_required(start_meeting),
        name='start_meeting',
    ),
    url(
        r'^zoom/get_student_join_url',
        login_required(get_student_join_url),
        name='get_student_join_url',
    ),
    url(
        r'^zoom/google_is_logged',
        login_required(google_is_logged),
        name='google_is_logged',
    ),
    url(
        r'^zoom/auth_google',
        login_required(auth_google),
        name='auth_google',
    ),
    url(
        r'^zoom/callback_google_auth',
        login_required(callback_google_auth),
        name='callback_google_auth',
    ),
    url(
        r'^zoom/create_livebroadcast',
        login_required(create_livebroadcast),
        name='url_new_livebroadcast',
    ),
    url(
        r'^zoom/livebroadcast_update',
        login_required(update_livebroadcast),
        name='url_update_livebroadcast',
    ),
    url(
        r'^zoom/youtube_validate',
        login_required(youtube_validate),
        name='youtube_validate',
    ),
    url(
        r'^zoom/event_zoom_youtube',
        event_zoom_youtube,
        name='event_zoom_youtube',
    ),
)
