# EOL Zoom XBlock

![https://github.com/eol-uchile/eol-zoom-xblock/actions](https://github.com/eol-uchile/eol-zoom-xblock/workflows/Python%20application/badge.svg)

XBlock and API to integrate zoom with the Open edX LMS. Editable within Open edx Studio.

# Install

    docker-compose exec cms pip install -e /openedx/requirements/eol-zoom-xblock
    docker-compose exec lms pip install -e /openedx/requirements/eol-zoom-xblock
    docker-compose exec lms python manage.py lms --settings=tutor.production makemigrations
    docker-compose exec lms python manage.py lms --settings=tutor.production migrate

# Configuration

To enable [Zoom API](https://marketplace.zoom.us/docs/guides) Edit *production.py* in *lms and cms settings* and add your own keys.

    import base64
    EOLZOOM_CLIENT_ID = AUTH_TOKENS.get('EOLZOOM_CLIENT_ID', '')
    EOLZOOM_CLIENT_SECRET = AUTH_TOKENS.get('EOLZOOM_CLIENT_SECRET', '')
    EOLZOOM_AUTHORIZATION = base64.b64encode('{}:{}'.format(EOLZOOM_CLIENT_ID, EOLZOOM_CLIENT_SECRET))

# Screenshots
*Last Update 26/03/2020*

## CMS - Studio Edit
<p align="center">
<img width="600" src="examples/studio_edit_01.png">
</p>
<p align="center">
<img width="600" src="examples/studio_edit_02.png">
</p>

## CMS - Author View
<p align="center">
<img width="600" src="examples/author_view_01.png">
</p>

## LMS - Staff View
<p align="center">
<img width="400" src="examples/staff_view_lms_01.png">
</p>

## LMS - Student View
<p align="center">
<img width="400" src="examples/student_view_lms_01.png">
</p>