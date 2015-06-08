from __future__ import absolute_import, unicode_literals

import logging
import tempfile

from django import apps
from django.conf import settings
from django.contrib.auth import models as auth_models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_migrate, post_save
from django.utils.translation import ugettext_lazy as _

from common import settings as common_settings

from .handlers import (
    auto_admin_account_passwd_change, user_locale_profile_session_config,
    user_locale_profile_create
)
from .links import (
    link_about, link_admin_site, link_current_user_details,
    link_current_user_edit, link_current_user_locale_profile_details,
    link_current_user_locale_profile_edit, link_license,
    link_maintenance_menu, link_setup, link_tools
)
from .menus import (
    menu_facet, menu_main, menu_secondary, menu_setup, menu_tools
)
from .models import (
    AnonymousUserSingleton, AutoAdminSingleton, UserLocaleProfile
)
from .settings import (
    AUTO_ADMIN_USERNAME, AUTO_ADMIN_PASSWORD, AUTO_CREATE_ADMIN,
    TEMPORARY_DIRECTORY
)
from .utils import validate_path

logger = logging.getLogger(__name__)


def create_superuser_and_anonymous_user(sender, **kwargs):
    """
    From https://github.com/lambdalisue/django-qwert/blob/master/qwert/autoscript/__init__.py
    From http://stackoverflow.com/questions/1466827/ --

    Prevent interactive question about wanting a superuser created. (This code
    has to go in this otherwise empty "models" module so that it gets processed by
    the "syncdb" command during database creation.)

    Create our own admin super user automatically.
    """
    if kwargs['app_config'].__class__ == CommonApp:
        AutoAdminSingleton.objects.get_or_create()
        AnonymousUserSingleton.objects.get_or_create()

        if AUTO_CREATE_ADMIN:
            try:
                auth_models.User.objects.get(username=AUTO_ADMIN_USERNAME)
            except auth_models.User.DoesNotExist:
                logger.info('Creating super admin user -- login: %s, password: %s', AUTO_ADMIN_USERNAME, AUTO_ADMIN_PASSWORD)
                assert auth_models.User.objects.create_superuser(AUTO_ADMIN_USERNAME, 'autoadmin@autoadmin.com', AUTO_ADMIN_PASSWORD)
                admin = auth_models.User.objects.get(username=AUTO_ADMIN_USERNAME)
                # Store the auto admin password properties to display the first login message
                auto_admin_properties, created = AutoAdminSingleton.objects.get_or_create()
                auto_admin_properties.account = admin
                auto_admin_properties.password = AUTO_ADMIN_PASSWORD
                auto_admin_properties.password_hash = admin.password
                auto_admin_properties.save()
            else:
                logger.info('Super admin user already exists. -- login: %s', AUTO_ADMIN_USERNAME)


class CommonApp(apps.AppConfig):
    name = 'common'
    verbose_name = _('Common')

    def ready(self):
        menu_facet.bind_links(links=[link_current_user_details, link_current_user_locale_profile_details, link_tools, link_setup], sources=['common:current_user_details', 'common:current_user_edit', 'common:current_user_locale_profile_details', 'common:current_user_locale_profile_edit', 'authentication:password_change_view', 'common:setup_list', 'common:tools_list'])
        menu_main.bind_links(links=[link_about], position=-1)
        menu_secondary.bind_links(
            links=[link_about, link_license],
            sources=['common:about_view', 'common:license_view']
        )
        menu_secondary.bind_links(
            links=[
                link_current_user_edit, link_current_user_locale_profile_edit
            ],
            sources=['common:current_user_details', 'common:current_user_edit', 'common:current_user_locale_profile_details', 'common:current_user_locale_profile_edit', 'authentication:password_change_view', 'common:setup_list', 'common:tools_list']
        )
        menu_setup.bind_links(links=[link_admin_site])
        menu_tools.bind_links(links=[link_maintenance_menu])

        post_migrate.connect(create_superuser_and_anonymous_user, dispatch_uid='create_superuser_and_anonymous_user')
        post_save.connect(auto_admin_account_passwd_change, dispatch_uid='auto_admin_account_passwd_change', sender=User)
        user_logged_in.connect(user_locale_profile_session_config, dispatch_uid='user_locale_profile_session_config', sender=User)
        post_save.connect(user_locale_profile_create, dispatch_uid='user_locale_profile_create', sender=User)

        if (not validate_path(TEMPORARY_DIRECTORY)) or (not TEMPORARY_DIRECTORY):
            setattr(common_settings, 'TEMPORARY_DIRECTORY', tempfile.mkdtemp())