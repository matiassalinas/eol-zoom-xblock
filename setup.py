"""Setup for eolzoom XBlock."""


import os

from setuptools import setup


def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}


setup(
    name='eolzoom-xblock',
    version='0.2',
    description='Zoom integration with EOL (OpenEdx)',
    license='AGPL v3',
    packages=[
        'eolzoom',
    ],
    install_requires=[
        'XBlock',
        "google-api-python-client>=1.10.0",
        "google-auth<2.0dev,>=1.25.0",
        "google-auth-httplib2>=0.0.3",
        "google-auth-oauthlib==0.4.1"],
    entry_points={
        'xblock.v1': [
            'eolzoom = eolzoom:EolZoomXBlock',
        ],
        "lms.djangoapp": [
            "eolzoom = eolzoom.apps:EolZoomConfig",
        ],
        "cms.djangoapp": [
            "eolzoom = eolzoom.apps:EolZoomConfig",
        ]
    },
    package_data=package_data("eolzoom", ["static", "public"]),
)
