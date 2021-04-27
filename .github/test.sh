#!/bin/dash

pip install -e /openedx/requirements/eolzoom

cd /openedx/requirements/eolzoom
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/eolzoom

DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest eolzoom/tests.py

rm -rf test_root
