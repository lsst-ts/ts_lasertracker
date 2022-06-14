"""Sphinx configuration file for an LSST telescope and site package.

This configuration only affects single-package Sphinx documentation builds.
"""

from documenteer.conf.pipelinespkg import *  # type: ignore # noqa
import lsst.ts.MTAlignment  # noqa

project = "ts_MTAlignment"
html_theme_options["logotext"] = project  # type: ignore # noqa
html_title = project
html_short_title = project
doxylink = {}  # Avoid warning: Could not find tag file _doxygen/doxygen.tag

intersphinx_mapping["ts_xml"] = ("https://ts-xml.lsst.io", None)  # type: ignore # noqa
intersphinx_mapping["ts_salobj"] = ("https://ts-salobj.lsst.io", None)  # type: ignore # noqa
intersphinx_mapping["ts_tcpip"] = ("https://ts-ts_tcpip.lsst.io", None)  # type: ignore # noqa
