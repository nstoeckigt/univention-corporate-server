#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Univention Installer
#  installer module: language selection
#
# Copyright (C) 2004, 2005, 2006 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# Binary versions of this file provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

#
# Results of previous modules are placed in self.all_results (dictionary)
# Results of this module need to be stored in the dictionary self.result (variablename:value[,value1,value2])
#

import objects, string
from objects import *
from local import _

class object(content):
	def checkname(self):
		return ['language']

	def profile_complete(self):
		if self.check('language') | self.check('locales'):
			return False
		if self.all_results.has_key('language') or self.all_results.has_key('locales'):
			return True
		else:
			if self.ignore('locales') or self.ignore('language'):
				return True
			return False
	def run_profiled(self):
		if self.all_results.has_key('locales'):
			return {'locales': self.all_results['locales']}

	def layout(self):
		self.elements.append(textline(_('Choose your system languages:'),self.minY-1,self.minX+2)) #2
		try:
			file=open('/usr/share/i18n/SUPPORTED')
		except:
			file=open('/usr/share/locale/SUPPORTED')

		locales=file.readlines()
		dict={}
		sortlist=[]
		default_position=[]
		default_values=[]
		if self.all_results.has_key('locales'):
			for val in self.all_results['locales'].split(' '):
				default_values.append(val.split(':')[0])
		else:
			default_values=['de_DE@euro']
		for line in range(len(locales)):
			sortlist.append(locales[line].strip().split(' '))
		sortlist.sort()
		count=0
		for entry in sortlist:
			dict[string.join(entry,' ')]=[string.join(entry,':'), count]
			if entry[0] in default_values:
				default_position.append(count)
			count+=1
		self.elements.append(checkbox(dict,self.minY,self.minX+2,33,18,default_position)) #3
		self.elements[3].current=default_position[0]


	def input(self,key):
		if key in [ 10, 32 ] and self.btn_next():
			return 'next'
		elif key in [ 10, 32 ] and self.btn_back():
			return 'prev'
		else:
			return self.elements[self.current].key_event(key)

	def incomplete(self):
		if string.join(self.elements[3].result(), ' ').strip(' ') == '':
			return _('Please select a valid language')
		return 0

	def helptext(self):
		return _('Language \n \n Choose system languages.')

	def modheader(self):
		return _('Language')

	def result(self):
		result={}
		result['locales']=string.join(self.elements[3].result(), ' ')
		return result
