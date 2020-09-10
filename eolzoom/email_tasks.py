
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
from django.conf import settings
from cms.djangoapps.contentstore.utils import get_lms_link_for_item
from lms.djangoapps.courseware.courses import get_course_by_id
from opaque_keys.edx.keys import UsageKey

from celery import task
from django.core.mail import send_mail
from django.utils.html import strip_tags

from django.template.loader import render_to_string

import logging
logger = logging.getLogger(__name__)

EMAIL_DEFAULT_RETRY_DELAY = 30
EMAIL_MAX_RETRIES = 5

@task(
    queue='edx.lms.core.low',
    default_retry_delay=EMAIL_DEFAULT_RETRY_DELAY,
    max_retries=EMAIL_MAX_RETRIES)
def meeting_start_email(block_id, user_email):
    """
        Send mail to specific user at meeting start
    """
    platform_name = configuration_helpers.get_value(
            'PLATFORM_NAME', settings.PLATFORM_NAME)
    usage_key = UsageKey.from_string(block_id)
    course = get_course_by_id(usage_key.course_key)
    subject = 'Ha comenzado una sesión de Zoom en el curso: {}'.format(course.display_name_with_default)
    redirect_url = get_lms_link_for_item(usage_key)
    context = {
        "course_name": course.display_name_with_default,
        "platform_name": platform_name,
        "redirect_url": redirect_url
    }
    html_message = render_to_string(
        'emails/meeting_start.txt', context)
    plain_message = strip_tags(html_message)
    from_email = configuration_helpers.get_value(
        'email_from_address',
        settings.BULK_EMAIL_DEFAULT_FROM_EMAIL
    )
    mail = send_mail(
        subject,
        plain_message,
        from_email,
        [user_email],
        fail_silently=False,
        html_message=html_message)
    return mail