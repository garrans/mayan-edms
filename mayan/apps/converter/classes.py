from __future__ import unicode_literals

import logging
import io
import os
import subprocess
from tempfile import mkstemp

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from PIL import Image

from django.utils.encoding import smart_str
from django.utils.module_loading import import_string
from django.utils.translation import ugettext_lazy as _

from common.settings import TEMPORARY_DIRECTORY
from common.utils import fs_cleanup
from mimetype.api import get_mimetype

from .exceptions import OfficeConversionError, UnknownFileFormat
from .literals import (
    DEFAULT_PAGE_NUMBER, DEFAULT_ZOOM_LEVEL, DEFAULT_ROTATION,
    DEFAULT_FILE_FORMAT, TRANSFORMATION_CHOICES, TRANSFORMATION_RESIZE,
    TRANSFORMATION_ROTATE, TRANSFORMATION_ZOOM, DIMENSION_SEPARATOR
)
from .settings import GRAPHICS_BACKEND, LIBREOFFICE_PATH

CONVERTER_OFFICE_FILE_MIMETYPES = [
    'application/msword',
    'application/mswrite',
    'application/mspowerpoint',
    'application/msexcel',
    'application/pgp-keys',
    'application/vnd.ms-excel',
    'application/vnd.ms-excel.addin.macroEnabled.12',
    'application/vnd.ms-excel.sheet.binary.macroEnabled.12',
    'application/vnd.ms-powerpoint',
    'application/vnd.oasis.opendocument.chart',
    'application/vnd.oasis.opendocument.chart-template',
    'application/vnd.oasis.opendocument.formula',
    'application/vnd.oasis.opendocument.formula-template',
    'application/vnd.oasis.opendocument.graphics',
    'application/vnd.oasis.opendocument.graphics-template',
    'application/vnd.oasis.opendocument.image',
    'application/vnd.oasis.opendocument.image-template',
    'application/vnd.oasis.opendocument.presentation',
    'application/vnd.oasis.opendocument.presentation-template',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
    'application/vnd.openxmlformats-officedocument.presentationml.template',
    'application/vnd.openxmlformats-officedocument.presentationml.slideshow',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.openxmlformats-officedocument.presentationml.slide',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.template',
    'application/vnd.oasis.opendocument.spreadsheet',
    'application/vnd.oasis.opendocument.spreadsheet-template',
    'application/vnd.oasis.opendocument.text',
    'application/vnd.oasis.opendocument.text-master',
    'application/vnd.oasis.opendocument.text-template',
    'application/vnd.oasis.opendocument.text-web',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-office',
    'application/xml',
    'text/x-c',
    'text/x-c++',
    'text/x-pascal',
    'text/x-msdos-batch',
    'text/x-python',
    'text/x-shellscript',
    'text/plain',
    'text/rtf',
]
logger = logging.getLogger(__name__)


class ConverterBase(object):
    @staticmethod
    def soffice(file_object):
        """
        Executes libreoffice using subprocess's Popen
        """

        new_file_object, input_filepath = tempfile.mkstemp()
        new_file_object.write(file_object.read())
        file_object.seek(0)
        new_file_object.seek(0)
        new_file_object.close()

        command = []
        command.append(LIBREOFFICE_PATH)

        command.append('--headless')
        command.append('--convert-to')
        command.append('pdf')
        command.append(input_filepath)
        command.append('--outdir')
        command.append(TEMPORARY_DIRECTORY)

        logger.debug('command: %s', command)

        os.environ['HOME'] = TEMPORARY_DIRECTORY
        proc = subprocess.Popen(command, close_fds=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        return_code = proc.wait()
        logger.debug('return_code: %s', return_code)

        readline = proc.stderr.readline()
        logger.debug('stderr: %s', readline)
        if return_code != 0:
            raise OfficeBackendError(readline)

        filename, extension = os.path.splitext(os.path.basename(input_filepath))
        logger.debug('filename: %s', filename)
        logger.debug('extension: %s', extension)

        converted_output = os.path.join(TEMPORARY_DIRECTORY, os.path.extsep.join([filename, 'pdf']))
        logger.debug('converted_output: %s', converted_output)

        return converted_output

    def __init__(self, file_object, mime_type=None):
        self.file_object = file_object
        self.mime_type = mime_type or get_mimetype(file_object=file_object, mimetype_only=False)[0]
        self.soffice_file_object = None

    def seek(self, page_number):
        # Starting with #0
        self.file_object.seek(0)

        try:
            self.image = Image.open(self.file_object)
        except IOError:
            # Cannot identify image file
            self.image = self.convert(page_number=page_number)
        else:
            self.image.seek(page_number)
            self.image.load()

    def get_page(self, output_format=DEFAULT_FILE_FORMAT):
        if not self.image:
            self.seek(1)

        image_buffer = StringIO()
        self.image.save(image_buffer, format=output_format)
        image_buffer.seek(0)

        return image_buffer

    def convert(self, page_number=DEFAULT_PAGE_NUMBER):
        self.page_number = page_number

        self.mime_type = 'application/pdf'

        if self.mime_type in CONVERTER_OFFICE_FILE_MIMETYPES:
            if os.path.exists(LIBREOFFICE_PATH):
                if not self.soffice_file_object:
                    converted_output = Converter.soffice(self.file_object)
                    self.file_object.seek(0)
                    self.soffice_file_object = open(converted_output)
                    self.mime_type = 'application/pdf'
                    fs_cleanup(converted_output)
                else:
                    self.soffice_file_object.seek(0)
            else:
                # TODO: NO LIBREOFFICE FOUND ERROR
                pass

    def transform(self, transformation):
        self.image = transformation.execute_on(self.image)

    def transform_many(self, transformations):
        for transformation in transformations:
            self.image = transformation.execute_on(self.image)

    def get_page_count(self):
        raise NotImplementedError()


class BaseTransformation(object):
    name = 'base_transformation'
    arguments = ()

    _registry = {}

    @classmethod
    def get_transformations_classes(cls):
        return map(lambda name: getattr(cls, name), filter(lambda entry: entry.startswith('Transform'), dir(cls)))

    @classmethod
    def get_transformations_choices(cls):
        return [(transformation.name, transformation.label) for transformation in cls.get_transformations_classes()]

    def __init__(self, **kwargs):
        for argument_name in self.arguments:
            setattr(self, argument_name, kwargs.get(argument_name))

    def execute_on(self, image):
        self.image = image
        self.aspect = 1.0 * image.size[0] / image.size[1]


class TransformationResize(BaseTransformation):
    name = 'resize'
    arguments = ('width', 'height')
    label = _('Resize')

    def execute_on(self, *args, **kwargs):
        super(TransformationResize, self).execute_on(*args, **kwargs)
        fit = False

        width = int(self.width)
        height = int(self.height or 1.0 * width * self.aspect)

        factor = 1
        while self.image.size[0] / factor > 2 * width and self.image.size[1] * 2 / factor > 2 * height:
            factor *= 2
        if factor > 1:
            self.image.thumbnail((self.image.size[0] / factor, self.image.size[1] / factor), Image.NEAREST)

        # calculate the cropping box and get the cropped part
        if fit:
            x1 = y1 = 0
            x2, y2 = self.image.size
            wRatio = 1.0 * x2 / width
            hRatio = 1.0 * y2 / height
            if hRatio > wRatio:
                y1 = y2 / 2 - height * wRatio / 2
                y2 = y2 / 2 + height * wRatio / 2
            else:
                x1 = x2 / 2 - width * hRatio / 2
                x2 = x2 / 2 + width * hRatio / 2
            self.image = self.image.crop((x1, y1, x2, y2))

        # Resize the image with best quality algorithm ANTI-ALIAS
        self.image.thumbnail((width, height), Image.ANTIALIAS)

        return self.image


class TransformationRotate(BaseTransformation):
    name = 'rotate'
    arguments = ('degrees',)
    label = _('Rotate')

    def execute_on(self, *args, **kwargs):
        super(TransformationRotate, self).execute_on(*args, **kwargs)

        return self.image.rotate(360 - self.degrees)


class TransformationZoom(BaseTransformation):
    name = 'zoom'
    arguments = ('percent',)
    label = _('Zoom')

    def execute_on(self, *args, **kwargs):
        super(TransformationZoom, self).execute_on(*args, **kwargs)

        decimal_value = float(self.percent) / 100
        return self.image.resize((int(self.image.size[0] * decimal_value), int(self.image.size[1] * decimal_value)), Image.ANTIALIAS)