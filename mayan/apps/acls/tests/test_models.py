from __future__ import absolute_import, unicode_literals

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.test import TestCase

from documents.models import Document, DocumentType
from documents.permissions import permission_document_view
from documents.tests import TEST_SMALL_DOCUMENT_PATH, TEST_DOCUMENT_TYPE
from permissions.classes import Permission
from permissions.models import Role

from ..models import AccessControlList


class PermissionTestCase(TestCase):
    def setUp(self):
        self.document_type_1 = DocumentType.objects.create(
            label=TEST_DOCUMENT_TYPE
        )

        ocr_settings = self.document_type_1.ocr_settings
        ocr_settings.auto_ocr = False
        ocr_settings.save()

        self.document_type_2 = DocumentType.objects.create(
            label=TEST_DOCUMENT_TYPE + '2'
        )

        ocr_settings = self.document_type_2.ocr_settings
        ocr_settings.auto_ocr = False
        ocr_settings.save()

        with open(TEST_SMALL_DOCUMENT_PATH) as file_object:
            self.document_1 = self.document_type_1.new_document(
                file_object=File(file_object), label='document 1'
            )

        with open(TEST_SMALL_DOCUMENT_PATH) as file_object:
            self.document_2 = self.document_type_1.new_document(
                file_object=File(file_object), label='document 2'
            )

        with open(TEST_SMALL_DOCUMENT_PATH) as file_object:
            self.document_3 = self.document_type_2.new_document(
                file_object=File(file_object), label='document 3'
            )

        self.user = get_user_model().objects.create(username='test user')
        self.group = Group.objects.create(name='test group')
        self.role = Role.objects.create(label='test role')
        Permission.invalidate_cache()

    def tearDown(self):
        for document_type in DocumentType.objects.all():
            document_type.delete()
        self.role.delete()
        self.group.delete()
        self.user.delete()

    def test_check_access_without_permissions(self):
        with self.assertRaises(PermissionDenied):
            AccessControlList.objects.check_access(
                permissions=(permission_document_view,),
                user=self.user, obj=self.document_1
            )

    def test_filtering_without_permissions(self):
        self.assertEqual(
            list(
                AccessControlList.objects.filter_by_access(
                    permission=permission_document_view, user=self.user,
                    queryset=Document.objects.all()
                )
            ), []
        )

    def test_check_access_with_acl(self):
        self.group.user_set.add(self.user)
        self.role.groups.add(self.group)

        acl = AccessControlList.objects.create(
            content_object=self.document_1, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        try:
            AccessControlList.objects.check_access(
                permissions=(permission_document_view,), user=self.user,
                obj=self.document_1
            )
        except PermissionDenied:
            self.fail('PermissionDenied exception was not expected.')

    def test_filtering_with_permissions(self):
        self.group.user_set.add(self.user)
        self.role.permissions.add(permission_document_view.stored_permission)
        self.role.groups.add(self.group)

        acl = AccessControlList.objects.create(
            content_object=self.document_1, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        self.assertEqual(
            list(
                AccessControlList.objects.filter_by_access(
                    permission=permission_document_view, user=self.user,
                    queryset=Document.objects.all()
                )
            ), [self.document_1]
        )

    def test_check_access_with_inherited_acl(self):
        self.group.user_set.add(self.user)
        self.role.groups.add(self.group)

        acl = AccessControlList.objects.create(
            content_object=self.document_type_1, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        try:
            AccessControlList.objects.check_access(
                permissions=(permission_document_view,), user=self.user,
                obj=self.document_1
            )
        except PermissionDenied:
            self.fail('PermissionDenied exception was not expected.')

    def test_check_access_with_inherited_acl_and_local_acl(self):
        self.group.user_set.add(self.user)
        self.role.groups.add(self.group)

        acl = AccessControlList.objects.create(
            content_object=self.document_type_1, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        acl = AccessControlList.objects.create(
            content_object=self.document_3, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        try:
            AccessControlList.objects.check_access(
                permissions=(permission_document_view,), user=self.user,
                obj=self.document_3
            )
        except PermissionDenied:
            self.fail('PermissionDenied exception was not expected.')

    def test_filtering_with_inherited_permissions(self):
        self.group.user_set.add(self.user)
        self.role.permissions.add(permission_document_view.stored_permission)
        self.role.groups.add(self.group)

        acl = AccessControlList.objects.create(
            content_object=self.document_type_1, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        result = AccessControlList.objects.filter_by_access(
            permission=permission_document_view, user=self.user,
            queryset=Document.objects.all()
        )
        self.assertTrue(self.document_1 in result)
        self.assertTrue(self.document_2 in result)
        self.assertTrue(self.document_3 not in result)

    def test_filtering_with_inherited_permissions_and_local_acl(self):
        self.group.user_set.add(self.user)
        self.role.permissions.add(permission_document_view.stored_permission)
        self.role.groups.add(self.group)

        acl = AccessControlList.objects.create(
            content_object=self.document_type_1, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        acl = AccessControlList.objects.create(
            content_object=self.document_3, role=self.role
        )
        acl.permissions.add(permission_document_view.stored_permission)

        result = AccessControlList.objects.filter_by_access(
            permission=permission_document_view, user=self.user,
            queryset=Document.objects.all()
        )
        self.assertTrue(self.document_1 in result)
        self.assertTrue(self.document_2 in result)
        self.assertTrue(self.document_3 in result)