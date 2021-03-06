# -*- coding: utf-8 -*-
"""
Testing utilities for ObsPy.

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (http://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA
from future.utils import native_str, PY2

from obspy.core.util.misc import get_untracked_files_from_git, CatchOutput
from obspy.core.util.base import getMatplotlibVersion, NamedTemporaryFile

import fnmatch
import inspect
import os
import io
import re
import difflib
import glob
import unittest
import doctest
import shutil
import warnings
from lxml import etree


def add_unittests(testsuite, module_name):
    """
    Function to add all available unittests of the module with given name
    (e.g. "obspy.core") to the given unittest TestSuite.
    All submodules in the "tests" directory whose names are starting with
    ``test_`` are added.

    :type testsuite: unittest.TestSuite
    :param testsuite: testsuite to which the tests should be added
    :type module_name: str
    :param module_name: name of the module of which the tests should be added

    .. rubric:: Example

    >>> import unittest
    >>> suite = unittest.TestSuite()
    >>> add_unittests(suite, "obspy.core")
    """
    MODULE_NAME = module_name
    MODULE_TESTS = __import__(MODULE_NAME + ".tests",
                              fromlist=[native_str("obspy")])
    filename_pattern = os.path.join(MODULE_TESTS.__path__[0], "test_*.py")
    files = glob.glob(filename_pattern)
    names = (os.path.basename(file).split(".")[0] for file in files)
    module_names = (".".join([MODULE_NAME, "tests", name]) for name in names)
    for module_name in module_names:
        module = __import__(module_name,
                            fromlist=[native_str("obspy")])
        testsuite.addTest(module.suite())


def add_doctests(testsuite, module_name):
    """
    Function to add all available doctests of the module with given name
    (e.g. "obspy.core") to the given unittest TestSuite.
    All submodules in the module's root directory are added.
    Occurring errors are shown as warnings.

    :type testsuite: unittest.TestSuite
    :param testsuite: testsuite to which the tests should be added
    :type module_name: str
    :param module_name: name of the module of which the tests should be added

    .. rubric:: Example

    >>> import unittest
    >>> suite = unittest.TestSuite()
    >>> add_doctests(suite, "obspy.core")
    """
    MODULE_NAME = module_name
    MODULE = __import__(MODULE_NAME, fromlist=[native_str("obspy")])
    MODULE_PATH = MODULE.__path__[0]
    MODULE_PATH_LEN = len(MODULE_PATH)

    for root, _dirs, files in os.walk(MODULE_PATH):
        # skip directories without __init__.py
        if '__init__.py' not in files:
            continue
        # skip tests directories
        if root.endswith('tests'):
            continue
        # skip scripts directories
        if root.endswith('scripts'):
            continue
        # skip lib directories
        if root.endswith('lib'):
            continue
        # loop over all files
        for file in files:
            # skip if not python source file
            if not file.endswith('.py'):
                continue
            # get module name
            parts = root[MODULE_PATH_LEN:].split(os.sep)[1:]
            module_name = ".".join([MODULE_NAME] + parts + [file[:-3]])
            try:
                module = __import__(module_name,
                                    fromlist=[native_str("obspy")])
                testsuite.addTest(doctest.DocTestSuite(module))
            except ValueError:
                pass


def checkForMatplotlibCompareImages():
    try:
        # trying to stay inside 80 char line
        import matplotlib.testing.compare as _compare
        compare_images = _compare.compare_images  # NOQA @UnusedVariable
    except:
        return False
    # matplotlib's (< 1.2) compare_images() uses PIL internally
    if getMatplotlibVersion() < [1, 2, 0]:
        try:
            import PIL  # NOQA @UnusedImport
        except ImportError:
            return False
    return True


HAS_COMPARE_IMAGE = checkForMatplotlibCompareImages()


class ImageComparisonException(unittest.TestCase.failureException):
    pass


class ImageComparison(NamedTemporaryFile):
    """
    Handles the comparison against a baseline image in an image test.

    .. note::
        Baseline images are created using matplotlib version `1.3.1`.

    :type image_path: str
    :param image_path: Path to directory where the baseline image is located
    :type image_name: str
    :param image_name: Filename (with suffix, without directory path) of the
        baseline image
    :type reltol: float, optional
    :param reltol: Multiplier that is applied to the default tolerance
        value (i.e. 10 means a 10 times harder to pass test tolerance).

    The class should be used with Python's "with" statement. When setting up,
    the matplotlib rcdefaults are set to ensure consistent image testing.
    After the plotting is completed, the :meth:`ImageComparison.compare`
    method is called automatically at the end of the "with" block, comparing
    against the previously specified baseline image. This raises an exception
    (if the test fails) with the message string from
    :func:`matplotlib.testing.compare.compare_images`. Afterwards all
    temporary files are deleted automatically.

    .. note::
        If images created during the testrun should be kept after the test, set
        environment variable `OBSPY_KEEP_IMAGES` to any value before executing
        the test (e.g. with `$ OBSPY_KEEP_IMAGES= obspy-runtests` or `$
        OBSPY_KEEP_IMAGES= python test_sometest.py`). For `obspy-runtests` the
        option "--keep-images" can also be used instead of setting an
        environment variable. Created images and diffs for failing tests are
        then stored in a subfolder "testrun" under the baseline image's
        directory.
        To only keep failed images and the corresponding diff image,
        additionally set environment variable `OBSPY_KEEP_ONLY_FAILED_IMAGES`
        to any value before executing the test.

    .. rubric:: Example

    >>> from obspy import read
    >>> with ImageComparison("/my/baseline/folder", 'plot.png') as ic:
    ...     st = read()  # doctest: +SKIP
    ...     st.plot(outfile=ic.name)  # doctest: +SKIP
    ...     # image is compared against baseline image automatically
    """
    def __init__(self, image_path, image_name, reltol=1, *args, **kwargs):
        self.suffix = "." + image_name.split(".")[-1]
        super(ImageComparison, self).__init__(suffix=self.suffix, *args,
                                              **kwargs)
        self.image_name = image_name
        self.baseline_image = os.path.join(image_path, image_name)
        self.keep_output = "OBSPY_KEEP_IMAGES" in os.environ
        self.keep_only_failed = "OBSPY_KEEP_ONLY_FAILED_IMAGES" in os.environ
        self.output_path = os.path.join(image_path, "testrun")
        self.diff_filename = "-failed-diff.".join(self.name.rsplit(".", 1))
        self.tol = get_matplotlib_defaul_tolerance() * reltol

    def __enter__(self):
        """
        Set matplotlib defaults.
        """
        from matplotlib import get_backend, rcParams, rcdefaults
        import locale

        try:
            locale.setlocale(locale.LC_ALL, native_str('en_US.UTF-8'))
        except:
            try:
                locale.setlocale(locale.LC_ALL,
                                 native_str('English_United States.1252'))
            except:
                msg = "Could not set locale to English/United States. " + \
                      "Some date-related tests may fail"
                warnings.warn(msg)

        if get_backend().upper() != 'AGG':
            import matplotlib
            try:
                matplotlib.use('AGG', warn=False)
            except TypeError:
                msg = "Image comparison requires matplotlib backend 'AGG'"
                warnings.warn(msg)

        # set matplotlib builtin default settings for testing
        rcdefaults()
        rcParams['font.family'] = 'Bitstream Vera Sans'
        try:
            rcParams['text.hinting'] = False
        except KeyError:
            warnings.warn("could not set rcParams['text.hinting']")
        try:
            rcParams['text.hinting_factor'] = 8
        except KeyError:
            warnings.warn("could not set rcParams['text.hinting_factor']")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # @UnusedVariable
        """
        Remove tempfiles and store created images if OBSPY_KEEP_IMAGES
        environment variable is set.
        """
        msg = ""
        try:
            # only compare images if no exception occurred in the with
            # statement. this avoids masking previously occurred exceptions (as
            # an exception may occur in compare()). otherwise we only clean up
            # and the exception gets re-raised at the end of __exit__.
            if exc_type is None:
                msg = self.compare()
        # we can still upload images if comparison fails on two different sized
        # images
        except ValueError as e:
            failed = True
            msg = str(e)
            if "operands could not be broadcast together" in msg:
                msg = self._upload_and_append_message(msg)
                raise ImageComparisonException(msg)
            raise
        # simply reraise on any other unhandled exceptions
        except:
            failed = True
            raise
        # if image comparison not raises by itself, the test failed if we get a
        # message back or the test passed if we get an empty message
        else:
            if msg:
                msg = self._upload_and_append_message(msg)
                failed = True
                raise ImageComparisonException(msg)
            failed = False
        # finally clean up after the image test, whether failed or not.
        # if specified move generated output to source tree
        finally:
            import matplotlib.pyplot as plt
            self.close()
            plt.close()
            if self.keep_output:
                if not (self.keep_only_failed and not failed):
                    self._copy_tempfiles()
            # delete temporary files
            os.remove(self.name)
            if os.path.exists(self.diff_filename):
                os.remove(self.diff_filename)

    def compare(self, reltol=1):  # @UnusedVariable
        """
        Run :func:`matplotlib.testing.compare.compare_images` and raise an
        unittest.TestCase.failureException with the message string given by
        matplotlib if the comparison exceeds the allowed tolerance.
        """
        from matplotlib.testing.compare import compare_images
        if os.stat(self.name).st_size == 0:
            msg = "Empty output image file."
            raise ImageComparisonException(msg)
        msg = compare_images(native_str(self.baseline_image),
                             native_str(self.name), tol=self.tol)
        return msg

    def _copy_tempfiles(self):
        """
        Copies created images from tempfiles to a subfolder of baseline images.
        """
        directory = self.output_path
        if os.path.exists(directory) and not os.path.isdir(directory):
            msg = "Could not keep output image, target directory exists:" + \
                  directory
            warnings.warn(msg)
            return
        if not os.path.exists(directory):
            os.mkdir(directory)
        if os.path.isfile(self.diff_filename):
            diff_filename_new = \
                "-failed-diff.".join(self.image_name.rsplit(".", 1))
            shutil.copy(self.diff_filename, os.path.join(directory,
                                                         diff_filename_new))
        shutil.copy(self.name, os.path.join(directory, self.image_name))

    def _upload_and_append_message(self, msg):
        """
        Takes an error message from image comparison, uploads any output images
        and appends the corresponding imgur links to the original error
        message.
        """
        msg_ = self._upload_images()
        if msg_:
            msg = "\n".join([msg, msg_])
        return msg

    def _upload_images(self):
        """
        Uploads images to imgur.
        """
        # try to import pyimgur
        try:
            import pyimgur
        except ImportError:
            msg = ("Upload to imgur not possible (python package "
                   "'pyimgur' not installed).")
            warnings.warn(msg)
            return ""
        # requests package should be installed since it is a dependency of
        # pyimgur
        import requests
        # try to get imgur client id from environment
        imgur_clientid = os.environ.get("OBSPY_IMGUR_CLIENTID", None)
        if imgur_clientid is None:
            msg = ("Upload to imgur not possible (environment "
                   "variable OBSPY_IMGUR_CLIENTID not set).")
            warnings.warn(msg)
            return ""
        # upload images and return urls
        imgur = pyimgur.Imgur(imgur_clientid)
        msg = []
        try:
            if os.path.exists(self.baseline_image):
                up = imgur.upload_image(self.baseline_image, title=self.name)
                msg.append("Baseline image: " + up.link)
            if os.path.exists(self.name):
                up = imgur.upload_image(self.name, title=self.name)
                msg.append("Failed image:   " + up.link)
            if os.path.exists(self.diff_filename):
                up = imgur.upload_image(self.diff_filename,
                                        title=self.diff_filename)
                msg.append("Diff image:     " + up.link)
        except requests.exceptions.SSLError as e:
            msg = ("Upload to imgur not possible (caught SSLError: %s).")
            warnings.warn(msg % str(e))
            return ""
        return "\n".join(msg)


def get_matplotlib_defaul_tolerance():
    """
    The two test images ("ok", "fail") result in the following rms values:
    matplotlib v1.3.x (git rev. 26b18e2): 0.8 and 9.0
    matplotlib v1.2.1: 1.7e-3 and 3.6e-3
    """
    # Baseline images are created with 1.3.1,
    # be very generous when testing other matplotlib versions.
    if getMatplotlibVersion() == [1, 3, 1]:
        return 2
    else:
        return 20


FLAKE8_EXCLUDE_FILES = [
    "*/__init__.py",
    ]

try:
    import flake8
except ImportError:
    HAS_FLAKE8 = False
else:
    # Only accept flake8 version >= 2.0
    HAS_FLAKE8 = flake8.__version__ >= '2'


def check_flake8():
    if not HAS_FLAKE8:
        raise Exception('flake8 is required to check code formatting')

    # pyflakes autodetection of PY2 does not work with the future library.
    # Therefore, overwrite the pyflakes autodetection manually
    if PY2:
        import pyflakes.checker  # @UnusedImport
        pyflakes.checker.PY2 = True
    import flake8.main
    from flake8.engine import get_style_guide

    test_dir = os.path.abspath(inspect.getfile(inspect.currentframe()))
    obspy_dir = os.path.dirname(os.path.dirname(os.path.dirname(test_dir)))
    untracked_files = get_untracked_files_from_git() or []
    files = []
    for dirpath, _, filenames in os.walk(obspy_dir):
        filenames = [_i for _i in filenames if
                     os.path.splitext(_i)[-1] == os.path.extsep + "py"]
        if not filenames:
            continue
        for py_file in filenames:
            py_file = os.path.join(dirpath, py_file)
            # ignore untracked files
            if os.path.abspath(py_file) in untracked_files:
                continue

            # exclude *.py files in obspy/lib
            try:
                tmp_dir, _ = os.path.split(py_file)
                _, tmp_dir = os.path.split(tmp_dir)
                if tmp_dir == "lib":
                    continue
            except:
                pass
            # Check files that do not match any exclusion pattern
            for exclude_pattern in FLAKE8_EXCLUDE_FILES:
                if fnmatch.fnmatch(py_file, exclude_pattern):
                    break
            else:
                files.append(py_file)
    flake8_style = get_style_guide(parse_argv=False,
                                   config_file=flake8.main.DEFAULT_CONFIG)
    flake8_style.options.ignore = tuple(set(flake8_style.options.ignore))

    with CatchOutput() as out:
        files = [native_str(f) for f in files]
        report = flake8_style.check_files(files)

    return report, out.stdout


# this dictionary contains the locations of checker routines that determine
# whether the module's tests can be executed or not (e.g. because test server
# is unreachable, necessary ports are blocked, etc.).
# A checker routine should return either an empty string (tests can and will
# be executed) or a message explaining why tests can not be executed (all
# tests of corresponding module will be skipped).
MODULE_TEST_SKIP_CHECKS = {
    'seishub': 'obspy.seishub.tests.test_client._check_server_availability',
    }


def compare_xml_strings(doc1, doc2):
    """
    Simple helper function to compare two XML strings.

    :type doc1: str
    :type doc2: str
    """
    # Compat py2k and py3k
    try:
        doc1 = doc1.encode()
        doc2 = doc2.encode()
    except:
        pass
    obj1 = etree.fromstring(doc1).getroottree()
    obj2 = etree.fromstring(doc2).getroottree()

    buf = io.BytesIO()
    obj1.write_c14n(buf)
    buf.seek(0, 0)
    str1 = buf.read().decode()
    str1 = [_i.strip() for _i in str1.splitlines()]

    buf = io.BytesIO()
    obj2.write_c14n(buf)
    buf.seek(0, 0)
    str2 = buf.read().decode()
    str2 = [_i.strip() for _i in str2.splitlines()]

    unified_diff = difflib.unified_diff(str1, str2)

    err_msg = "\n".join(unified_diff)
    if err_msg:  # pragma: no cover
        raise AssertionError("Strings are not equal.\n" + err_msg)


def remove_unique_IDs(xml_string, remove_creation_time=False):
    """
    Removes unique ID parts of e.g. 'publicID="..."' attributes from xml
    strings.

    :type xml_string: str
    :param xml_string: xml string to process
    :type remove_creation_time: bool
    :param xml_string: controls whether to remove 'creationTime' tags or not.
    :rtype: str
    """
    prefixes = ["id", "publicID", "pickID", "originID", "preferredOriginID",
                "preferredMagnitudeID", "preferredFocalMechanismID",
                "referenceSystemID", "methodID", "earthModelID",
                "triggeringOriginID", "derivedOriginID", "momentMagnitudeID",
                "greensFunctionID", "filterID", "amplitudeID",
                "stationMagnitudeID", "earthModelID", "slownessMethodID",
                "pickReference", "amplitudeReference"]
    if remove_creation_time:
        prefixes.append("creationTime")
    for prefix in prefixes:
        xml_string = re.sub("%s='.*?'" % prefix, '%s=""' % prefix, xml_string)
        xml_string = re.sub('%s=".*?"' % prefix, '%s=""' % prefix, xml_string)
        xml_string = re.sub("<%s>.*?</%s>" % (prefix, prefix),
                            '<%s/>' % prefix, xml_string)
    return xml_string


if __name__ == '__main__':
    doctest.testmod(exclude_empty=True)
