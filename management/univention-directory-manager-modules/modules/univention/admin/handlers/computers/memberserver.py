# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for the memberserver hosts
#
# Copyright 2004-2017 Univention GmbH
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

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization
import univention.admin.nagios as nagios
from univention.admin.handlers.computers.base import computerBase

translation = univention.admin.localization.translation('univention.admin.handlers.computers')
_ = translation.translate

module = 'computers/memberserver'
operations = ['add', 'edit', 'remove', 'search', 'move']
docleanup = 1
childs = 0
short_description = _('Computer: Member Server')
long_description = ''
options = {
	'posix': univention.admin.option(
		short_description=_('Posix account'),
		default=1,
		objectClasses=('posixAccount', 'shadowAccount'),
	),
	'kerberos': univention.admin.option(
		short_description=_('Kerberos principal'),
		default=1,
		objectClasses=('krb5Principal', 'krb5KDCEntry'),
	),
	'samba': univention.admin.option(
		short_description=_('Samba account'),
		editable=True,
		default=1,
		objectClasses=('sambaSamAccount',),
	)
}
property_descriptions = {
	'name': univention.admin.property(
		short_description=_('Member server name'),
		long_description='',
		syntax=univention.admin.syntax.hostName,
		multivalue=False,
		include_in_default_search=True,
		options=[],
		required=True,
		may_change=False,
		identifies=True
	),
	'description': univention.admin.property(
		short_description=_('Description'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		required=False,
		may_change=True,
		identifies=False
	),
	'operatingSystem': univention.admin.property(
		short_description=_('Operating system'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		required=False,
		may_change=True,
		identifies=False
	),
	'operatingSystemVersion': univention.admin.property(
		short_description=_('Operating system version'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False
	),
	'domain': univention.admin.property(
		short_description=_('Domain'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		required=False,
		may_change=True,
		identifies=False
	),
	'mac': univention.admin.property(
		short_description=_('MAC address'),
		long_description='',
		syntax=univention.admin.syntax.MAC_Address,
		multivalue=True,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'network': univention.admin.property(
		short_description=_('Network'),
		long_description='',
		syntax=univention.admin.syntax.network,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'ip': univention.admin.property(
		short_description=_('IP address'),
		long_description='',
		syntax=univention.admin.syntax.ipAddress,
		multivalue=True,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'serverRole': univention.admin.property(
		short_description=_('System role'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'service': univention.admin.property(
		short_description=_('Service'),
		long_description='',
		syntax=univention.admin.syntax.Service,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'dnsEntryZoneForward': univention.admin.property(
		short_description=_('Forward zone for DNS entry'),
		long_description='',
		syntax=univention.admin.syntax.dnsEntry,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'dnsEntryZoneReverse': univention.admin.property(
		short_description=_('Reverse zone for DNS entry'),
		long_description='',
		syntax=univention.admin.syntax.dnsEntryReverse,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'dnsEntryZoneAlias': univention.admin.property(
		short_description=_('Zone for DNS alias'),
		long_description='',
		syntax=univention.admin.syntax.dnsEntryAlias,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'dnsAlias': univention.admin.property(
		short_description=_('DNS alias'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'dhcpEntryZone': univention.admin.property(
		short_description=_('DHCP service'),
		long_description='',
		syntax=univention.admin.syntax.dhcpEntry,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'password': univention.admin.property(
		short_description=_('Password'),
		long_description='',
		syntax=univention.admin.syntax.passwd,
		multivalue=False,
		options=['kerberos', 'posix', 'samba'],
		required=False,
		may_change=True,
		identifies=False,
		dontsearch=True
	),
	'unixhome': univention.admin.property(
		short_description=_('Unix home directory'),
		long_description='',
		syntax=univention.admin.syntax.absolutePath,
		multivalue=False,
		options=['posix'],
		required=True,
		may_change=True,
		identifies=False,
		default=('/dev/null', [])
	),
	'shell': univention.admin.property(
		short_description=_('Login shell'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=['posix'],
		required=False,
		may_change=True,
		identifies=False,
		default=('/bin/bash', [])
	),
	'primaryGroup': univention.admin.property(
		short_description=_('Primary group'),
		long_description='',
		syntax=univention.admin.syntax.GroupDN,
		multivalue=False,
		options=['posix'],
		required=True,
		dontsearch=True,
		may_change=True,
		identifies=False
	),
	'reinstall': univention.admin.property(
		short_description=_('(Re-)install on next boot'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'reinstalloption': univention.admin.property(
		short_description=_('additional start options'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'instprofile': univention.admin.property(
		short_description=_('Name of installation profile'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'inventoryNumber': univention.admin.property(
		short_description=_('Inventory number'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=True,
		include_in_default_search=True,
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'groups': univention.admin.property(
		short_description=_('Groups'),
		long_description='',
		syntax=univention.admin.syntax.GroupDN,
		multivalue=True,
		options=[],
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False
	),
	'sambaRID': univention.admin.property(
		short_description=_('Relative ID'),
		long_description='',
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False,
		options=['samba']
	),
}

layout = [
	Tab(_('General'), _('Basic settings'), layout=[
		Group(_('Computer account'), layout=[
			['name', 'description'],
			'inventoryNumber',
		]),
		Group(_('Network settings '), layout=[
			'network',
			'mac',
			'ip',
		]),
		Group(_('DNS Forward and Reverse Lookup Zone'), layout=[
			'dnsEntryZoneForward',
			'dnsEntryZoneReverse',
		]),
		Group(_('DHCP'), layout=[
			'dhcpEntryZone'
		]),
	]),
	Tab(_('Account'), _('Account'), advanced=True, layout=[
		'password',
		'primaryGroup'
	]),
	Tab(_('Unix account'), _('Unix account settings'), advanced=True, layout=[
		['unixhome', 'shell']
	]),
	Tab(_('Services'), _('Services'), advanced=True, layout=[
		'service',
	]),
	Tab(_('Deployment'), _('Deployment'), advanced=True, layout=[
		['reinstall'],
		['instprofile', 'reinstalloption']
	]),
	Tab(_('Groups'), _('Group memberships'), advanced=True, layout=[
		'groups',
	]),
	Tab(_('DNS alias'), _('Alias DNS entry'), advanced=True, layout=[
		'dnsEntryZoneAlias'
	]),
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('description', 'description', None, univention.admin.mapping.ListToString)
mapping.register('domain', 'associatedDomain', None, univention.admin.mapping.ListToString)
mapping.register('serverRole', 'univentionServerRole')
mapping.register('mac', 'macAddress')
mapping.register('inventoryNumber', 'univentionInventoryNumber')
mapping.register('reinstall', 'univentionServerReinstall', None, univention.admin.mapping.ListToString)
mapping.register('instprofile', 'univentionServerInstallationProfile', None, univention.admin.mapping.ListToString)
mapping.register('reinstalloption', 'univentionServerInstallationOption', None, univention.admin.mapping.ListToString)
mapping.register('network', 'univentionNetworkLink', None, univention.admin.mapping.ListToString)
mapping.register('unixhome', 'homeDirectory', None, univention.admin.mapping.ListToString)
mapping.register('shell', 'loginShell', None, univention.admin.mapping.ListToString)
mapping.register('service', 'univentionService')
mapping.register('operatingSystem', 'univentionOperatingSystem', None, univention.admin.mapping.ListToString)
mapping.register('operatingSystemVersion', 'univentionOperatingSystemVersion', None, univention.admin.mapping.ListToString)

# add Nagios extension
nagios.addPropertiesMappingOptionsAndLayout(property_descriptions, mapping, options, layout)


class object(computerBase):
	module = module
	mapping = mapping
	CONFIG_NAME = 'univentionDefaultMemberserverGroup'
	DEFAULT_OCS = ['top', 'person', 'univentionHost', 'univentionMemberServer']
	SAMBA_ACCOUNT_FLAG = 'W'
	SERVER_TYPE = 'univentionMemberServer'
	SERVER_ROLE = 'member'


rewrite = object.rewrite
lookup_filter = object.lookup_filter
lookup = object.lookup
identify = object.identify
