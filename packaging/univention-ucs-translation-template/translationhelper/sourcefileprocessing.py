#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2013-2017 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.
from lxml import etree
import os
import pofile
import polib

from pdb import set_trace as dbg


class UnsupportedSourceType(Exception):
	pass


class SourceFileSet(object):

	def __init__(self, src_pkg_path, binary_pkg_name, files):
		self.files = files
		self.src_pkg_path = src_pkg_path
		self.binary_pkg_name = binary_pkg_name

	def process(self, new_po_path):
		if not os.path.isfile(new_po_path):
			pofile.create_empty_po(self.binary_pkg_name, new_po_path)


class SourceFilesXgettext(SourceFileSet):

	def process(self, gettext_lang, new_po_path):
		super(SourceFilesXgettext, self).process(new_po_path)
		pofile.join_existing(gettext_lang, new_po_path, self.files, cwd=self.src_pkg_path)


class SourceFilesShell(SourceFilesXgettext):

	def process(self, new_po_path):
		super(SourceFilesShell, self).process('Shell', new_po_path)


class SourceFilesPython(SourceFilesXgettext):

	def process(self, new_po_path):
		super(SourceFilesPython, self).process('Python', new_po_path)


class SourceFilesJavaScript(SourceFilesXgettext):

	def process(self, new_po_path):
		super(SourceFilesJavaScript, self).process('JavaScript', new_po_path)


class SourceFilesHTML(SourceFileSet):

	def process(self, new_po_path):
		new_po = polib.pofile(new_po_path)
		html_parser = etree.HTMLParser()
		for html_path in self.files:
			with open(html_path, 'rb') as html_file:
				tree = etree.parse(html_file, html_parser)
				for element in tree.iter():
					if 'data-i18n' in element.keys():
						new_entry = polib.POEntry(msgid=element.get('data-i18n'),
							occurrences=[(os.path.basename(html_path), element.sourceline)])
						new_po.append(new_entry)
				# Inline JavaScript may use underscorce funtion, e.g. univention/management/index.html
				if tree.xpath('//script'):
					pofile.join_existing('JavaScript', new_po_path, html_path, cwd=self.src_pkg_path)
		new_po.save(new_po_path)


class SourceFileSetFactory(object):
	process_by_type = {'text/x-shellscript': SourceFilesShell,
			'text/x-python': SourceFilesPython,
			'text/html': SourceFilesHTML,
			'application/javascript': SourceFilesJavaScript}

	@classmethod
	def from_mimetype(cls, src_pkg_path, binary_pkg_name, mimetype, files):
		try:
			obj = cls.process_by_type[mimetype](src_pkg_path, binary_pkg_name, files)
		except KeyError:
			raise UnsupportedSourceType(files)
		else:
			return obj


def from_mimetype(src_pkg_path, binary_pkg_name, mimetype, files):
	return SourceFileSetFactory.from_mimetype(src_pkg_path, binary_pkg_name, mimetype, files)