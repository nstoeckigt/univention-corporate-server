# -*- coding: utf-8 -*-
#
# Univention Admin Modules
#  admin module for the user objects
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

import hashlib
import os
import string
import re
import copy
import time
import types
import struct
from M2Crypto import X509
import ldap
import base64
from ldap.filter import filter_format

import univention.admin
from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.handlers.groups.group
import univention.admin.password
import univention.admin.samba
import univention.admin.allocators
import univention.admin.localization
import univention.admin.uexceptions
import univention.admin.uldap
import univention.admin.mungeddial as mungeddial
import univention.admin.handlers.settings.prohibited_username
from univention.admin import configRegistry
from univention.lib.s4 import rids_for_well_known_security_identifiers

import univention.debug
import univention.password

translation = univention.admin.localization.translation('univention.admin.handlers.users')
_ = translation.translate

module = 'users/user'
operations = ['add', 'edit', 'remove', 'search', 'move', 'copy']
template = 'settings/usertemplate'

childs = 0
short_description = _('User')
long_description = _('POSIX, Samba and Kerberos account')


options = {
	'default': univention.admin.option(
		short_description=_('POSIX, Samba and Kerberos account'),
		default=True,
		objectClasses=['top', 'person', 'univentionPWHistory', 'posixAccount', 'shadowAccount', 'sambaSamAccount', 'krb5Principal', 'krb5KDCEntry']
	),
	'mail': univention.admin.option(
		short_description=_('Mail account'),
		default=True,
		objectClasses=['univentionMail'],
	),
	'pki': univention.admin.option(
		short_description=_('Public key infrastructure account'),
		default=False,
		editable=True,
		objectClasses=['pkiUser'],
	),
	'person': univention.admin.option(
		short_description=_('Personal information'),
		default=True,
		objectClasses=['person', 'organizationalPerson', 'inetOrgPerson'],
	),
}
property_descriptions = {
	'username': univention.admin.property(
		short_description=_('User name'),
		long_description='',
		syntax=univention.admin.syntax.uid_umlauts,
		multivalue=False,
		include_in_default_search=True,
		required=True,
		may_change=True,
		identifies=True,
		readonly_when_synced=True,
	),
	'uidNumber': univention.admin.property(
		short_description=_('User ID'),
		long_description='',
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		required=False,
		may_change=False,
		identifies=False,
		dontsearch=True,
	),
	'gidNumber': univention.admin.property(
		short_description=_('Group ID of the primary group'),
		long_description='',
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		required=False,
		may_change=False,
		identifies=False,
		editable=False,
		dontsearch=True,
		readonly_when_synced=True,
	),
	'firstname': univention.admin.property(
		short_description=_('First name'),
		long_description='',
		syntax=univention.admin.syntax.TwoThirdsString,
		multivalue=False,
		include_in_default_search=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'lastname': univention.admin.property(
		short_description=_('Last name'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		required=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'gecos': univention.admin.property(
		short_description=_('GECOS'),
		long_description='',
		syntax=univention.admin.syntax.IA5string,
		multivalue=False,
		required=False,
		may_change=True,
		default='<firstname> <lastname><:umlauts,strip>',
		identifies=False,
		dontsearch=True,
		copyable=True,
	),
	'displayName': univention.admin.property(
		short_description=_('Display name'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		default='<firstname> <lastname><:strip>',
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'title': univention.admin.property(
		short_description=_('Title'),
		long_description='',
		syntax=univention.admin.syntax.OneThirdString,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'sambaPrivileges': univention.admin.property(
		short_description=_('Samba privilege'),
		long_description=_('Manage Samba privileges'),
		syntax=univention.admin.syntax.SambaPrivileges,
		multivalue=True,
		required=False,
		dontsearch=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'description': univention.admin.property(
		short_description=_('Description'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'organisation': univention.admin.property(
		short_description=_('Organisation'),
		long_description='',
		syntax=univention.admin.syntax.string64,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'userexpiry': univention.admin.property(
		short_description=_('Account expiry date'),
		long_description=_('Enter date as day.month.year.'),
		syntax=univention.admin.syntax.date2,
		multivalue=False,
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False,
		copyable=True,
	),
	'passwordexpiry': univention.admin.property(
		short_description=_('Password expiry date'),
		long_description=_('Enter date as day.month.year.'),
		syntax=univention.admin.syntax.date,
		multivalue=False,
		editable=False,
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'pwdChangeNextLogin': univention.admin.property(
		short_description=_('Change password on next login'),
		long_description=_('Change password on next login'),
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False,
		readonly_when_synced=True,
	),
	'disabled': univention.admin.property(
		short_description=_('Account deactivation'),
		long_description='',
		syntax=univention.admin.syntax.disabled,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		show_in_lists=True,
		copyable=True,
		default='none',
	),
	'locked': univention.admin.property(
		short_description=_('Locked login methods'),
		long_description='',
		syntax=univention.admin.syntax.locked,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		show_in_lists=True,
		default='none',
	),
	'password': univention.admin.property(
		short_description=_('Password'),
		long_description='',
		syntax=univention.admin.syntax.userPasswd,
		multivalue=False,
		required=True,
		may_change=True,
		identifies=False,
		dontsearch=True,
		readonly_when_synced=True,
	),
	'street': univention.admin.property(
		short_description=_('Street'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'e-mail': univention.admin.property(
		short_description=_('E-mail address'),
		long_description='',
		syntax=univention.admin.syntax.emailAddress,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		default=['<mailPrimaryAddress>'],
	),
	'postcode': univention.admin.property(
		short_description=_('Postal code'),
		long_description='',
		syntax=univention.admin.syntax.OneThirdString,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'city': univention.admin.property(
		short_description=_('City'),
		long_description='',
		syntax=univention.admin.syntax.TwoThirdsString,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'country': univention.admin.property(
		short_description=_('Country'),
		long_description='',
		syntax=univention.admin.syntax.Country,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'phone': univention.admin.property(
		short_description=_('Telephone number'),
		long_description='',
		syntax=univention.admin.syntax.phone,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'employeeNumber': univention.admin.property(
		short_description=_('Employee number'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		include_in_default_search=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'roomNumber': univention.admin.property(
		short_description=_('Room number'),
		long_description='',
		syntax=univention.admin.syntax.OneThirdString,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'secretary': univention.admin.property(
		short_description=_('Superior'),
		long_description='',
		syntax=univention.admin.syntax.UserDN,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'departmentNumber': univention.admin.property(
		short_description=_('Department number'),
		long_description='',
		syntax=univention.admin.syntax.OneThirdString,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'employeeType': univention.admin.property(
		short_description=_('Employee type'),
		long_description='',
		syntax=univention.admin.syntax.string,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'homePostalAddress': univention.admin.property(
		short_description=_('Private postal address'),
		long_description='',
		syntax=univention.admin.syntax.postalAddress,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'homeTelephoneNumber': univention.admin.property(
		short_description=_('Private telephone number'),
		long_description='',
		syntax=univention.admin.syntax.phone,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'mobileTelephoneNumber': univention.admin.property(
		short_description=_('Mobile phone number'),
		long_description='',
		syntax=univention.admin.syntax.phone,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'pagerTelephoneNumber': univention.admin.property(
		short_description=_('Pager telephone number'),
		long_description='',
		syntax=univention.admin.syntax.phone,
		multivalue=True,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'birthday': univention.admin.property(
		short_description=_('Birthdate'),
		long_description=_('Date of birth'),
		syntax=univention.admin.syntax.iso8601Date,
		multivalue=False,
		options=['person'],
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'unixhome': univention.admin.property(
		short_description=_('Unix home directory'),
		long_description='',
		syntax=univention.admin.syntax.absolutePath,
		multivalue=False,
		required=True,
		may_change=True,
		identifies=False,
		default='/home/<username>'
	),

	'shell': univention.admin.property(
		short_description=_('Login shell'),
		long_description='',
		syntax=univention.admin.syntax.OneThirdString,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		default='/bin/bash',
		copyable=True,
	),
	'sambahome': univention.admin.property(
		short_description=_('Windows home path'),
		long_description=_('The directory path which is used as the user\'s Windows home directory, e.g. \\\\ucs-file-server\\smith.'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'scriptpath': univention.admin.property(
		short_description=_('Windows logon script'),
		long_description=_('The user-specific logon script relative to the NETLOGON share, e.g. user.bat.'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'profilepath': univention.admin.property(
		short_description=_('Windows profile directory'),
		long_description=_('The directory path (resolvable by windows clients) e.g. %LOGONSERVER%\\%USERNAME%\\windows-profiles\\default which is used to configure a roaming profile.'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'homedrive': univention.admin.property(
		short_description=_('Windows home drive'),
		long_description=_('The drive letter (with trailing colon) where the Windows home directory of this user lies, e.g. M:. Needs only be specified if it is different to the Samba configuration.'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'sambaRID': univention.admin.property(
		short_description=_('Relative ID'),
		long_description=_('The relative ID (RID) is the local part of the SID and will be assigned automatically to next available RID. It can not be subsequently changed. Valid values are numbers upwards 1000. RIDs below 1000 are reserved to standard groups and other special objects.'),
		syntax=univention.admin.syntax.integer,
		multivalue=False,
		required=False,
		may_change=True,
		dontsearch=True,
		identifies=False,
		readonly_when_synced=True,
	),
	'groups': univention.admin.property(
		short_description=_('Groups'),
		long_description='',
		syntax=univention.admin.syntax.GroupDN,
		multivalue=True,
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'primaryGroup': univention.admin.property(
		short_description=_('Primary group'),
		long_description='',
		syntax=univention.admin.syntax.GroupDN,
		multivalue=False,
		required=True,
		dontsearch=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'mailHomeServer': univention.admin.property(
		short_description=_('Mail home server'),
		long_description='',
		syntax=univention.admin.syntax.MailHomeServer,
		nonempty_is_default=True,
		multivalue=False,
		options=['mail'],
		required=False,
		dontsearch=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'mailPrimaryAddress': univention.admin.property(
		short_description=_('Primary e-mail address'),
		long_description='',
		syntax=univention.admin.syntax.primaryEmailAddressValidDomain,
		multivalue=False,
		include_in_default_search=True,
		options=['mail'],
		required=False,
		dontsearch=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
	),
	'mailAlternativeAddress': univention.admin.property(
		short_description=_('Alternative e-mail address'),
		long_description='',
		syntax=univention.admin.syntax.emailAddressValidDomain,
		multivalue=True,
		options=['mail'],
		required=False,
		dontsearch=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=False,
		copyable=True,
	),
	'mailForwardAddress': univention.admin.property(
		short_description=_('Forward e-mail address'),
		long_description=_("Incoming e-mails for this user are copied/redirected to the specified forward e-mail adresses. Depending on the forwarding setting, a local copy of each e-mail is kept. If no forwarding e-mail addresses are specified, the e-mails are always kept in the user's mailbox."),
		syntax=univention.admin.syntax.emailAddress,
		multivalue=True,
		options=['mail'],
		required=False,
		dontsearch=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=False,
		copyable=True,
	),
	'mailForwardCopyToSelf': univention.admin.property(
		short_description=_('Forwarding setting'),
		long_description=_("Specifies if a local copy of each incoming e-mail is kept for this user. If no forwarding e-mail addresses are specified, the e-mails are always kept in the user's mailbox."),
		syntax=univention.admin.syntax.emailForwardSetting,
		multivalue=False,
		options=['mail'],
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=False,
		copyable=True,
	),
	'overridePWHistory': univention.admin.property(
		short_description=_('Override password history'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'overridePWLength': univention.admin.property(
		short_description=_('Override password check'),
		long_description='',
		syntax=univention.admin.syntax.boolean,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'homeShare': univention.admin.property(
		short_description=_('Home share'),
		long_description=_('Share, the user\'s home directory resides on'),
		syntax=univention.admin.syntax.WritableShare,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		copyable=True,
	),
	'homeSharePath': univention.admin.property(
		short_description=_('Home share path'),
		long_description=_('Path to the home directory on the home share'),
		syntax=univention.admin.syntax.HalfString,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		default='<username>'
	),
	'sambaUserWorkstations': univention.admin.property(
		short_description=_('Allow the authentication only on this Microsoft Windows host'),
		long_description=(''),
		syntax=univention.admin.syntax.string,
		multivalue=True,
		required=False,
		dontsearch=False,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'sambaLogonHours': univention.admin.property(
		short_description=_('Permitted times for Windows logins'),
		long_description=(""),
		syntax=univention.admin.syntax.SambaLogonHours,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		identifies=False,
		readonly_when_synced=True,
		copyable=True,
	),
	'jpegPhoto': univention.admin.property(
		short_description=_("Picture of the user (JPEG format)"),
		long_description=_('Picture for user account in JPEG format'),
		syntax=univention.admin.syntax.jpegPhoto,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		options=['person'],
		identifies=False,
		copyable=True,
	),
	'userCertificate': univention.admin.property(
		short_description=_("PKI user certificate (DER format)"),
		long_description=_('Public key infrastructure - user certificate '),
		syntax=univention.admin.syntax.Base64Upload,
		multivalue=False,
		required=False,
		dontsearch=True,
		may_change=True,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerCountry': univention.admin.property(
		short_description=_('Issuer Country'),
		long_description=_('Certificate Issuer Country'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerState': univention.admin.property(
		short_description=_('Issuer State'),
		long_description=_('Certificate Issuer State'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerLocation': univention.admin.property(
		short_description=_('Issuer Location'),
		long_description=_('Certificate Issuer Location'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerOrganisation': univention.admin.property(
		short_description=_('Issuer Organisation'),
		long_description=_('Certificate Issuer Organisation'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerOrganisationalUnit': univention.admin.property(
		short_description=_('Issuer Organisational Unit'),
		long_description=_('Certificate Issuer Organisational Unit'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerCommonName': univention.admin.property(
		short_description=_('Issuer Common Name'),
		long_description=_('Certificate Issuer Common Name'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateIssuerMail': univention.admin.property(
		short_description=_('Issuer Mail'),
		long_description=_('Certificate Issuer Mail'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectCountry': univention.admin.property(
		short_description=_('Subject Country'),
		long_description=_('Certificate Subject Country'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectState': univention.admin.property(
		short_description=_('Subject State'),
		long_description=_('Certificate Subject State'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectLocation': univention.admin.property(
		short_description=_('Subject Location'),
		long_description=_('Certificate Subject Location'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectOrganisation': univention.admin.property(
		short_description=_('Subject Organisation'),
		long_description=_('Certificate Subject Organisation'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectOrganisationalUnit': univention.admin.property(
		short_description=_('Subject Organisational Unit'),
		long_description=_('Certificate Subject Organisational Unit'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectCommonName': univention.admin.property(
		short_description=_('Subject Common Name'),
		long_description=_('Certificate Subject Common Name'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSubjectMail': univention.admin.property(
		short_description=_('Subject Mail'),
		long_description=_('Certificate Subject Mail'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateDateNotBefore': univention.admin.property(
		short_description=_('Valid from'),
		long_description=_('Certificate valid from'),
		syntax=univention.admin.syntax.date,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateDateNotAfter': univention.admin.property(
		short_description=_('Valid until'),
		long_description=_('Certificate valid until'),
		syntax=univention.admin.syntax.date,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateVersion': univention.admin.property(
		short_description=_('Version'),
		long_description=_('Certificate Version'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'certificateSerial': univention.admin.property(
		short_description=_('Serial'),
		long_description=_('Certificate Serial'),
		syntax=univention.admin.syntax.string,
		multivalue=False,
		required=False,
		dontsearch=True,
		editable=False,
		options=['pki'],
		identifies=False,
		copyable=True,
	),
	'umcProperty': univention.admin.property(
		short_description=_('UMC user preferences'),
		long_description=_('Key value pairs storing user preferences for UMC'),
		syntax=univention.admin.syntax.keyAndValue,
		dontsearch=True,
		multivalue=True,
		required=False,
		may_change=True,
		identifies=False,
		copyable=True,
	),
}

# append CTX properties
for key, value in mungeddial.properties.items():
	property_descriptions[key] = value

default_property_descriptions = copy.deepcopy(property_descriptions)  # for later reset of descriptions

layout = [
	Tab(_('General'), _('Basic settings'), layout=[
		Group(_('User account'), layout=[
			['title', 'firstname', 'lastname'],
			['username', 'description'],
			'password',
			['overridePWHistory', 'overridePWLength'],
			'mailPrimaryAddress',
		]),
		Group(_('Personal information'), layout=[
			'displayName',
			'birthday',
			'jpegPhoto',
		]),
		Group(_('Organisation'), layout=[
			'organisation',
			['employeeNumber', 'employeeType'],
			'secretary',
		]),
	]),
	Tab(_('Groups'), _('Groups'), layout=[
		Group(_('Primary group'), layout=[
			'primaryGroup',
		]),
		Group(_('Additional groups'), layout=[
			'groups',
		]),
	]),
	Tab(_('Account'), _('Account settings'), layout=[
		Group(_('Locking and deactivation'), layout=[
			['disabled', 'locked'],
			['userexpiry', 'passwordexpiry'],
			'pwdChangeNextLogin',
		]),
		Group(_('Windows'), _('Windows account settings'), layout=[
			['homedrive', 'sambahome'],
			['scriptpath', 'profilepath'],
			'sambaRID',
			'sambaPrivileges',
			'sambaLogonHours',
			'sambaUserWorkstations'
		]),
		Group(_('POSIX (Linux/UNIX)'), _('POSIX (Linux/UNIX) account settings'), layout=[
			['unixhome', 'shell'],
			['uidNumber', 'gidNumber'],
			['homeShare', 'homeSharePath'],
		]),
	]),
	Tab(_('Contact'), _('Contact information'), layout=[
		Group(_('Business'), layout=[
			'e-mail',
			'phone',
			['roomNumber', 'departmentNumber'],
			['street', 'postcode', 'city', 'country'],
		]),
		Group(_('Private'), layout=[
			'homeTelephoneNumber',
			'mobileTelephoneNumber',
			'pagerTelephoneNumber',
			'homePostalAddress'
		]),
	]),
	Tab(_('Mail'), _('Mail preferences'), advanced=True, layout=[
		Group(_('Advanced settings'), layout=[
			'mailAlternativeAddress',
			'mailHomeServer',
		], ),
		Group(_('Mail forwarding'), layout=[
			'mailForwardCopyToSelf',
			'mailForwardAddress',
		], ),
	]),
	Tab(_('UMC preferences'), _('UMC preferences'), advanced=True, layout=[
		Group(_('UMC preferences'), layout=[
			'umcProperty',
		]),
	]),
	Tab(_('Certificate'), _('Certificate'), advanced=True, layout=[
		Group(_('General'), '', [
			'userCertificate',
		]),
		Group(_('Subject'), '', [
			['certificateSubjectCommonName', 'certificateSubjectMail'],
			['certificateSubjectOrganisation', 'certificateSubjectOrganisationalUnit'],
			'certificateSubjectLocation',
			['certificateSubjectState', 'certificateSubjectCountry'],
		]),
		Group(_('Issuer'), '', [
			['certificateIssuerCommonName', 'certificateIssuerMail'],
			['certificateIssuerOrganisation', 'certificateIssuerOrganisationalUnit'],
			'certificateIssuerLocation',
			['certificateIssuerState', 'certificateIssuerCountry'],
		]),
		Group(_('Validity'), '', [
			['certificateDateNotBefore', 'certificateDateNotAfter']
		]),
		Group(_('Misc'), '', [
			['certificateVersion', 'certificateSerial']
		])
	])
]

# append tab with CTX flags
layout.append(mungeddial.tab)


def check_prohibited_username(lo, username):
	"""check if the username is allowed"""
	module = univention.admin.modules.get('settings/prohibited_username')
	for prohibited_object in (module.lookup(None, lo, '') or []):
		if username in prohibited_object['usernames']:
			raise univention.admin.uexceptions.prohibitedUsername(username)


def case_insensitive_in_list(dn, list):
	for element in list:
		if dn.decode('utf8').lower() == element.decode('utf8').lower():
			return True
	return False


def posixDaysToDate(days):
	return time.strftime("%Y-%m-%d", time.gmtime(long(days) * 3600 * 24))


def sambaWorkstationsMap(workstations):
	univention.debug.debug(univention.debug.ADMIN, univention.debug.ALL, 'samba: sambaWorkstationMap: in=%s; out=%s' % (workstations, string.join(workstations, ',')))
	return string.join(workstations, ',')


def sambaWorkstationsUnmap(workstations):
	univention.debug.debug(univention.debug.ADMIN, univention.debug.ALL, 'samba: sambaWorkstationUnmap: in=%s; out=%s' % (workstations[0], string.split(workstations[0], ',')))
	return string.split(workstations[0], ',')


def logonHoursMap(logontimes):
	"converts the bitfield 001110010110...100 to the respective string"

	# convert list of bit numbers to bit-string
	# bitstring = '0' * 168

	if logontimes == '':
		# if unsetting it, see Bug #33703
		return None

	bitstring = ''.join(map(lambda x: x in logontimes and '1' or '0', range(168)))

	# for idx in logontimes:
	# 	bitstring[ idx ] = '1'

	logontimes = bitstring

	# the order of the bits of each byte has to be reversed. The reason for this is that
	# consecutive bytes mean consecutive 8-hrs-intervals, but the leftmost bit stands for
	# the last hour in that interval, the 2nd but leftmost bit for the second-but-last
	# hour and so on. We want to hide this from anybody using this feature.
	# See http://ma.ph-freiburg.de/tng/tng-technical/2003-04/msg00015.html for details.

	newtimes = ""
	for i in range(0, 21):
		bitlist = list(logontimes[(i * 8):(i * 8) + 8])
		bitlist.reverse()
		newtimes += "".join(bitlist)
	logontimes = newtimes

	# create a hexnumber from each 8-bit-segment
	ret = ""
	for i in range(0, 21):
		val = 0
		exp = 7
		for j in range((i * 8), (i * 8) + 8):
			if not (logontimes[j] == "0"):
				val += 2**exp
			exp -= 1
		# we now have: 0<=val<=255
		hx = hex(val)[2:4]
		if len(hx) == 1:
			hx = "0" + hx
		ret += hx

	return ret


def logonHoursUnmap(logontimes):
	"converts the string to a bit array"

	times = logontimes[0][:42]
	while len(times) < 42:
		times = times
	ret = ""
	for i in range(0, 42, 2):
		val = int(times[i:i + 2], 16)
		ret += intToBinary(val)

	# reverse order of the bits in each byte. See above for details
	newtime = ""
	for i in range(0, 21):
		bitlist = list(ret[(i * 8):(i * 8) + 8])
		bitlist.reverse()
		newtime += "".join(bitlist)

	# convert bit-string to list
	return filter(lambda i: newtime[i] == '1', range(168))


def intToBinary(val):
	ret = ""
	while val > 0:
		ret = str(val & 1) + ret
		val = val >> 1
	# pad with leading 0s until length is n*8
	if ret == "":
		ret = "0"
	while not (len(ret) % 8 == 0):
		ret = "0" + ret
	return ret


def GMTOffset():
	# returns the difference in hours between local time and GMT (is -1 for CET and CEST)
	return time.timezone / 3600


def load_certificate(user_certificate):
	"""Import a certificate in DER format"""
	if not user_certificate:
		return {}
	try:
		certificate = base64.decodestring(user_certificate)
	except base64.binascii.Error:
		return {}
	try:
		x509 = X509.load_cert_string(certificate, X509.FORMAT_DER)

		values = {
			'certificateDateNotBefore': x509.get_not_before().get_datetime().date().isoformat(),
			'certificateDateNotAfter': x509.get_not_after().get_datetime().date().isoformat(),
			'certificateVersion': str(x509.get_version()),
			'certificateSerial': str(x509.get_serial_number()),
		}
		X509.m2.XN_FLAG_SEP_MULTILINE & ~X509.m2.ASN1_STRFLGS_ESC_MSB | X509.m2.ASN1_STRFLGS_UTF8_CONVERT
		for entity, prefix in (
			(x509.get_issuer(), "certificateIssuer"),
			(x509.get_subject(), "certificateSubject"),
		):
			for key, attr in load_certificate.ATTR.items():
				value = getattr(entity, key)
				values[prefix + attr] = value
	except (X509.X509Error, AttributeError):
		return {}

	univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'value=%s' % values)
	return values


load_certificate.ATTR = {
	"C": "Country",
	"ST": "State",
	"L": "Location",
	"O": "Organisation",
	"OU": "OrganisationalUnit",
	"CN": "CommonName",
	"emailAddress": "Mail",
}


def mapHomePostalAddress(old):
	new = []
	for i in old:
		new.append(string.join(i, '$'))
	return new


def unmapHomePostalAddress(old):
	new = []
	for i in old:
		if '$' in i:
			new.append(i.split('$'))
		else:
			new.append([i, " ", " "])

	return new


def unmapUserExpiry(oldattr):
	return unmapKrb5ValidEndToUserexpiry(oldattr) or unmapSambaKickoffTimeToUserexpiry(oldattr) or unmapShadowExpireToUserexpiry(oldattr)


def unmapShadowExpireToUserexpiry(oldattr):
	# The shadowLastChange attribute is the amount of days between 1/1/1970 upto the day that password was modified,
	# shadowMax is the number of days a password is valid. So the password expires on 1/1/1970 + shadowLastChange + shadowMax.
	# shadowExpire contains the absolute date to expire the account.

	if 'shadowExpire' in oldattr and len(oldattr['shadowExpire']) > 0:
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'userexpiry: %s' % posixDaysToDate(oldattr['shadowExpire'][0]))
		if oldattr['shadowExpire'][0] != '1':
			return posixDaysToDate(oldattr['shadowExpire'][0])


def unmapKrb5ValidEndToUserexpiry(oldattr):
	if 'krb5ValidEnd' in oldattr:
		krb5validend = oldattr['krb5ValidEnd'][0]
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'krb5validend is: %s' % krb5validend)
		return "%s-%s-%s" % (krb5validend[0:4], krb5validend[4:6], krb5validend[6:8])


def unmapSambaKickoffTimeToUserexpiry(oldattr):
	if 'sambaKickoffTime' in oldattr:
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'sambaKickoffTime is: %s' % oldattr['sambaKickoffTime'][0])
		return time.strftime("%Y-%m-%d", time.gmtime(long(oldattr['sambaKickoffTime'][0]) + (3600 * 24)))


def unmapPasswordExpiry(oldattr):
	if 'shadowLastChange' in oldattr and 'shadowMax' in oldattr and len(oldattr['shadowLastChange']) > 0 and len(oldattr['shadowMax']) > 0:
		try:
			return posixDaysToDate(int(oldattr['shadowLastChange'][0]) + int(oldattr['shadowMax'][0]))
		except:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'users/user: failed to calculate password expiration correctly, use only shadowMax instead')
		return posixDaysToDate(int(oldattr['shadowMax'][0]))


def _add_disabled(disabled, new_disabled):
	if disabled == 'none' or not disabled:
		return new_disabled
	elif (disabled == 'windows' and new_disabled == 'posix') or (new_disabled == 'windows' and disabled == 'posix'):
		return 'windows_posix'
	elif (disabled == 'windows' and new_disabled == 'kerberos') or (new_disabled == 'windows' and disabled == 'kerberos'):
		return 'windows_kerberos'
	elif (disabled == 'kerberos' and new_disabled == 'posix') or (new_disabled == 'kerberos' and disabled == 'posix'):
		return 'posix_kerberos'
	elif disabled == 'posix_kerberos' and new_disabled == 'windows':
		return 'all'
	elif disabled == 'windows_kerberos' and new_disabled == 'posix':
		return 'all'
	elif disabled == 'windows_posix' and new_disabled == 'kerberos':
		return 'all'


def unmapDisabled(oldattr):
	disabled = 'none'
	if unmapSambaDisabled(oldattr):
		disabled = _add_disabled(disabled, 'windows')
	if unmapKerberosDisabled(oldattr):
		disabled = _add_disabled(disabled, 'kerberos')
	if unmapPosixDisabled(oldattr, disabled):
		disabled = _add_disabled(disabled, 'posix')
	return disabled


def unmapSambaDisabled(oldattr):
	flags = oldattr.get('sambaAcctFlags', None)
	if flags:
		acctFlags = univention.admin.samba.acctFlags(flags[0])
		try:
			return acctFlags['D'] == 1
		except KeyError:
			pass


def unmapKerberosDisabled(oldattr):
	kdcflags = oldattr.get('krb5KDCFlags', ['0'])[0]
	return kdcflags == '254'


def unmapPosixDisabled(oldattr, disabled):
	# TODO: is it correct to evaluate kerberos / windows here?
	shadowExpire = oldattr.get('shadowExpire', ['0'])[0]
	return shadowExpire == '1' or (shadowExpire < int(time.time() / 3600 / 24) and (_is_kerberos_disabled(disabled) or _is_windows_disabled(disabled)))


def _is_kerberos_disabled(disabled):
	return disabled in ('all', 'kerberos', 'posix_kerberos', 'windows_kerberos')


def _is_windows_disabled(disabled):
	return disabled in ('all', 'windows', 'windows_posix', 'windows_kerberos')


def unmapLocked(oldattr):
	locked = 'none'
	userPassword = oldattr.get('userPassword', [''])[0]
	if userPassword and univention.admin.password.is_locked(userPassword):
		locked = 'posix'

	flags = oldattr.get('sambaAcctFlags', None)
	if flags:
		acctFlags = univention.admin.samba.acctFlags(flags[0])
		try:
			if acctFlags['L'] == 1:
				if locked == 'posix':
					locked = 'all'
				else:
					locked = 'windows'
		except KeyError:
			pass
	return locked


def unmapSambaRid(oldattr):
	sid = oldattr.get('sambaSID', [''])[0]
	pos = sid.rfind('-')
	return sid[pos + 1:]


def unmapPassword(oldattr):
	return oldattr.get('userPassword', [''])[0]


def mapKeyAndValue(old):
	lst = []
	for entry in old:
		lst.append('%s=%s' % (entry[0], entry[1]))
	return lst


def unmapKeyAndValue(old):
	lst = []
	for entry in old:
		lst.append(entry.split('=', 1))
	return lst


mapping = univention.admin.mapping.mapping()
mapping.register('username', 'uid', None, univention.admin.mapping.ListToString)
mapping.register('uidNumber', 'uidNumber', None, univention.admin.mapping.ListToString)
mapping.register('gidNumber', 'gidNumber', None, univention.admin.mapping.ListToString)
mapping.register('title', 'title', None, univention.admin.mapping.ListToString)
mapping.register('description', 'description', None, univention.admin.mapping.ListToString)
mapping.register('organisation', 'o', None, univention.admin.mapping.ListToString)

mapping.register('mailPrimaryAddress', 'mailPrimaryAddress', None, univention.admin.mapping.ListToLowerString)
mapping.register('mailAlternativeAddress', 'mailAlternativeAddress')
mapping.register('mailHomeServer', 'univentionMailHomeServer', None, univention.admin.mapping.ListToString)
mapping.register('mailForwardAddress', 'mailForwardAddress')
mapping.register('mailForwardCopyToSelf', 'mailForwardCopyToSelf', None, univention.admin.mapping.ListToString)

mapping.register('street', 'street', None, univention.admin.mapping.ListToString)
mapping.register('e-mail', 'mail')
mapping.register('postcode', 'postalCode', None, univention.admin.mapping.ListToString)
mapping.register('city', 'l', None, univention.admin.mapping.ListToString)
mapping.register('country', 'st', None, univention.admin.mapping.ListToString)
mapping.register('phone', 'telephoneNumber')
mapping.register('roomNumber', 'roomNumber', None, univention.admin.mapping.ListToString)
mapping.register('employeeNumber', 'employeeNumber', None, univention.admin.mapping.ListToString)
mapping.register('employeeType', 'employeeType', None, univention.admin.mapping.ListToString)
mapping.register('secretary', 'secretary')
mapping.register('departmentNumber', 'departmentNumber', None, univention.admin.mapping.ListToString)
mapping.register('mobileTelephoneNumber', 'mobile')
mapping.register('pagerTelephoneNumber', 'pager')
mapping.register('homeTelephoneNumber', 'homePhone')
mapping.register('homePostalAddress', 'homePostalAddress', mapHomePostalAddress, unmapHomePostalAddress)
mapping.register('unixhome', 'homeDirectory', None, univention.admin.mapping.ListToString)
mapping.register('shell', 'loginShell', None, univention.admin.mapping.ListToString)
mapping.register('sambahome', 'sambaHomePath', None, univention.admin.mapping.ListToString)
mapping.register('sambaUserWorkstations', 'sambaUserWorkstations', sambaWorkstationsMap, sambaWorkstationsUnmap)
mapping.register('sambaLogonHours', 'sambaLogonHours', logonHoursMap, logonHoursUnmap)
mapping.register('sambaPrivileges', 'univentionSambaPrivilegeList')
mapping.register('scriptpath', 'sambaLogonScript', None, univention.admin.mapping.ListToString)
mapping.register('profilepath', 'sambaProfilePath', None, univention.admin.mapping.ListToString)
mapping.register('homedrive', 'sambaHomeDrive', None, univention.admin.mapping.ListToString)
mapping.register('gecos', 'gecos', None, univention.admin.mapping.ListToString)
mapping.register('displayName', 'displayName', None, univention.admin.mapping.ListToString)
mapping.register('birthday', 'univentionBirthday', None, univention.admin.mapping.ListToString)
mapping.register('lastname', 'sn', None, univention.admin.mapping.ListToString)
mapping.register('firstname', 'givenName', None, univention.admin.mapping.ListToString)
mapping.register('userCertificate', 'userCertificate;binary', univention.admin.mapping.mapBase64, univention.admin.mapping.unmapBase64)
mapping.register('jpegPhoto', 'jpegPhoto', univention.admin.mapping.mapBase64, univention.admin.mapping.unmapBase64)
mapping.register('umcProperty', 'univentionUMCProperty', mapKeyAndValue, unmapKeyAndValue)
mapping.registerUnmapping('sambaRID', unmapSambaRid)
mapping.registerUnmapping('passwordexpiry', unmapPasswordExpiry)
mapping.registerUnmapping('userexpiry', unmapUserExpiry)
mapping.registerUnmapping('disabled', unmapDisabled)
mapping.registerUnmapping('locked', unmapLocked)
mapping.registerUnmapping('password', unmapLocked)  # TODO: register with regular mapping


class object(univention.admin.handlers.simpleLdap, mungeddial.Support):
	module = module

	def __add_disabled(self, new):
		self['disabled'] = _add_disabled(self['disabled'], new)

	def __is_kerberos_disabled(self):
		return _is_kerberos_disabled(self['disabled'])

	def __is_windows_disabled(self):
		return _is_windows_disabled(self['disabled'])

	def __is_posix_disabled(self):
		return self['disabled'] in ('all', 'posix', 'posix_kerberos', 'windows_posix')

	def __pwd_is_auth_saslpassthrough(self, password):
		return password.startswith('{SASL}') and univention.admin.baseConfig.get('directory/manager/web/modules/users/user/auth/saslpassthrough', 'no').lower() == 'keep'

	@property
	def __forward_copy_to_self(self):
		return self.get('mailForwardCopyToSelf') == '1'

	def __remove_old_mpa(self, forward_list):
		if forward_list and self.oldattr.get('mailPrimaryAddress') and self.oldattr['mailPrimaryAddress'] != self['mailPrimaryAddress']:
			try:
				forward_list.remove(self.oldattr['mailPrimaryAddress'])
			except ValueError:
				pass

	def __set_mpa_for_forward_copy_to_self(self, forward_list):
		if self.__forward_copy_to_self and self['mailForwardAddress']:
			forward_list.append(self['mailPrimaryAddress'])
		else:
			try:
				forward_list.remove(self['mailPrimaryAddress'])
			except ValueError:
				pass

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes=None):
		self.groupsLoaded = 1
		self.password_length = 8

		univention.admin.handlers.simpleLdap.__init__(self, co, lo, position, dn, superordinate, attributes=attributes)
		mungeddial.Support.__init__(self)

	def open(self, loadGroups=True):
		univention.admin.handlers.simpleLdap.open(self)

		if self.exists():
			self._unmap_mail_forward()
			self._unmap_pwd_change_next_login()
			self.sambaMungedDialUnmap()
			self.sambaMungedDialParse()
			self._unmap_automount_information()
			self.reload_certificate()

		self._load_groups(loadGroups)
		self.save()

	def _load_groups(self, loadGroups):
		self.newPrimaryGroupDn = 0
		self.oldPrimaryGroupDn = 0
		if self.exists():
			self.groupsLoaded = loadGroups
			if loadGroups:  # this is optional because it can take much time on larger installations, default is true
				self['groups'] = self.lo.searchDn(filter=filter_format('(&(cn=*)(|(objectClass=univentionGroup)(objectClass=sambaGroupMapping))(uniqueMember=%s))', [self.dn]))
			else:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'user: open with loadGroups=false for user %s' % self['username'])
			primaryGroupNumber = self.oldattr.get('gidNumber', [''])[0]
			if primaryGroupNumber:
				primaryGroupResult = self.lo.searchDn(filter=filter_format('(&(cn=*)(|(objectClass=posixGroup)(objectClass=sambaGroupMapping))(gidNumber=%s))', [primaryGroupNumber]))
				if primaryGroupResult:
					self['primaryGroup'] = primaryGroupResult[0]
				else:
					try:
						primaryGroup = self.lo.search(filter='(objectClass=univentionDefault)', base='cn=univention,' + self.position.getDomain(), attr=['univentionDefaultGroup'])
						try:
							primaryGroup = primaryGroup[0][1]["univentionDefaultGroup"][0]
						except:
							primaryGroup = None
					except:
						primaryGroup = None

					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'user: could not find primaryGroup, setting primaryGroup to %s' % primaryGroup)

					self['primaryGroup'] = primaryGroup
					self.newPrimaryGroupDn = primaryGroup
					self.__primary_group()
			else:
				self['primaryGroup'] = None
				self.save()
				raise univention.admin.uexceptions.primaryGroup()
		else:
			primary_group_from_template = self['primaryGroup']
			if not primary_group_from_template:
				searchResult = self.lo.search(filter='(objectClass=univentionDefault)', base='cn=univention,' + self.position.getDomain(), attr=['univentionDefaultGroup'])
				if not searchResult or not searchResult[0][1]:
					self['primaryGroup'] = None
					self.save()
					raise univention.admin.uexceptions.primaryGroup

				for tmp, number in searchResult:
					primaryGroupResult = self.lo.searchDn(filter=filter_format('(&(objectClass=posixGroup)(cn=%s))', (univention.admin.uldap.explodeDn(number['univentionDefaultGroup'][0], 1)[0],)), base=self.position.getDomain(), scope='domain')
					if primaryGroupResult:
						self['primaryGroup'] = primaryGroupResult[0]
						self.newPrimaryGroupDn = primaryGroupResult[0]

	def _unmap_pwd_change_next_login(self):
		if self['passwordexpiry']:
			today = time.strftime('%Y-%m-%d').split('-')
			expiry = self['passwordexpiry'].split('-')
			# expiry.reverse()
			# today.reverse()
			if int(string.join(today, '')) >= int(string.join(expiry, '')):
				self['pwdChangeNextLogin'] = '1'

	def _unmap_mail_forward(self):
		# mailForwardCopyToSelf is a "virtual" property. The boolean value is set to True, if
		# the LDAP attribute mailForwardAddress contains the mailPrimaryAddress. The mailPrimaryAddress
		# is removed from oldattr for correct display in CLI/UMC and for proper detection of changes.
		if self.get('mailPrimaryAddress') in self.get('mailForwardAddress', []):
			self.oldattr['mailForwardAddress'] = self.oldattr.get('mailForwardAddress', [])[:]
			self['mailForwardAddress'].remove(self['mailPrimaryAddress'])
			self['mailForwardCopyToSelf'] = '1'
		else:
			self['mailForwardCopyToSelf'] = '0'

	def _unmap_automount_information(self):
		if 'automountInformation' not in self.oldattr:
			return
		try:
			flags, unc = re.split(' *', self.oldattr['automountInformation'][0], 1)
			host, path = unc.split(':', 1)
		except ValueError:
			return

		sharepath = path
		while len(sharepath) > 1:
			filter_ = univention.admin.filter.conjunction('&', [
				univention.admin.filter.expression('univentionShareHost', host, escape=True),
				univention.admin.filter.conjunction('|', [
					univention.admin.filter.expression('univentionSharePath', sharepath.rstrip('/'), escape=True),
					univention.admin.filter.expression('univentionSharePath', '%s/' % (sharepath.rstrip('/')), escape=True),
				])
			])
			res = univention.admin.modules.lookup(univention.admin.modules.get('shares/share'), None, self.lo, filter=filter_, scope='domain')
			if len(res) == 1:
				self['homeShare'] = res[0].dn
				relpath = path.replace(sharepath, '')
				if len(relpath) > 0 and relpath[0] == '/':
					relpath = relpath[1:]
				self['homeSharePath'] = relpath
				break
			elif len(res) > 1:
				break
			elif len(res) < 1:
				sharepath = os.path.split(sharepath)[0]

	def modify(self, *args, **kwargs):
		try:
			return super(object, self).modify(*args, **kwargs)
		except univention.admin.uexceptions.licenseDisableModify:
			# it has to be possible to deactivate an user account when the license is exceeded
			if 'all' not in self['disabled'] or not self.hasChanged('disabled'):
				raise
			kwargs['ignore_license'] = True
			return super(object, self).modify(*args, **kwargs)

	def reload_certificate(self):
		"""Reload user certificate."""
		if 'pki' not in self.options:
			return
		self.info['certificateSubjectCountry'] = ''
		self.info['certificateSubjectState'] = ''
		self.info['certificateSubjectLocation'] = ''
		self.info['certificateSubjectOrganisation'] = ''
		self.info['certificateSubjectOrganisationalUnit'] = ''
		self.info['certificateSubjectCommonName'] = ''
		self.info['certificateSubjectMail'] = ''
		self.info['certificateIssuerCountry'] = ''
		self.info['certificateIssuerState'] = ''
		self.info['certificateIssuerLocation'] = ''
		self.info['certificateIssuerOrganisation'] = ''
		self.info['certificateIssuerOrganisationalUnit'] = ''
		self.info['certificateIssuerCommonName'] = ''
		self.info['certificateIssuerMail'] = ''
		self.info['certificateDateNotBefore'] = ''
		self.info['certificateDateNotAfter'] = ''
		self.info['certificateVersion'] = ''
		self.info['certificateSerial'] = ''
		certificate = self.info.get('userCertificate')
		values = load_certificate(certificate)
		if values:
			self.info.update(values)
		else:
			self.info['userCertificate'] = ''

	def hasChanged(self, key):
		if key == 'disabled':
			acctFlags = univention.admin.samba.acctFlags(self.oldattr.get("sambaAcctFlags", [''])[0]).decode()
			krb5Flags = self.oldattr.get('krb5KDCFlags', [])
			shadowExpire = self.oldattr.get('shadowExpire', [])

			if not acctFlags and not krb5Flags and not shadowExpire:
				return False
			if self['disabled'] == 'all':
				return 'D' not in acctFlags or \
					'126' in krb5Flags or \
					'1' not in shadowExpire
			elif self['disabled'] == 'windows':
				return 'D' not in acctFlags or \
					'254' in krb5Flags or \
					'1' in shadowExpire
			elif self['disabled'] == 'kerberos':
				return 'D' in acctFlags or \
					'126' in krb5Flags or \
					'1' in shadowExpire
			elif self['disabled'] == 'posix':
				return 'D' in acctFlags or \
					'254' in krb5Flags or \
					'1' not in shadowExpire
			elif self['disabled'] == 'windows_kerberos':
				return 'D' not in acctFlags or \
					'126' in krb5Flags or \
					'1' in shadowExpire
			elif self['disabled'] == 'windows_posix':
				return 'D' not in acctFlags or \
					'254' in krb5Flags or \
					'1' not in shadowExpire
			elif self['disabled'] == 'posix_kerberos':
				return 'D' in acctFlags or \
					'126' in krb5Flags or \
					'1' not in shadowExpire
			else:  # enabled
				return 'D' in acctFlags or \
					'254' in krb5Flags or \
					'1' in shadowExpire
		elif key == 'locked':
			password = self['password']
			acctFlags = univention.admin.samba.acctFlags(self.oldattr.get("sambaAcctFlags", [''])[0]).decode()
			if not password and not acctFlags:
				return False
			if self['locked'] == 'all':
				return not univention.admin.password.is_locked(password) or \
					'L' not in acctFlags
			elif self['locked'] == 'windows':
				return univention.admin.password.is_locked(password) or \
					'L' not in acctFlags
			elif self['locked'] == 'posix':
				return not univention.admin.password.is_locked(password) or \
					'L' in acctFlags
			else:
				return univention.admin.password.is_locked(password) or \
					'L' in acctFlags

		return super(object, self).hasChanged(key)

	def __update_groups(self):
		if not self.groupsLoaded:
			return

		if self.exists():
			old_groups = self.oldinfo.get('groups', [])
			old_uid = self.oldinfo.get('username', '')
		else:
			old_groups = []
			old_uid = ""
		new_uid = self.info.get('username', '')
		new_groups = self.info.get('groups', [])

		# change memberUid if we have a new username
		if old_uid and old_uid != new_uid and self.exists():
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: rewrite memberuid after rename')
			for group in new_groups:
				self.__rewrite_member_uid(group)

		group_mod = univention.admin.modules.get('groups/group')

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: check groups in old_groups')
		for group in old_groups:
			if group and not case_insensitive_in_list(group, self.info.get('groups', [])) and group.lower() != self['primaryGroup'].lower():
				grpobj = group_mod.object(None, self.lo, self.position, group)
				grpobj.fast_member_remove([self.dn], [old_uid])

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: check groups in info[groups]')
		for group in self.info.get('groups', []):
			if group and not case_insensitive_in_list(group, old_groups):
				grpobj = group_mod.object(None, self.lo, self.position, group)
				grpobj.fast_member_add([self.dn], [new_uid])

		if univention.admin.baseConfig.is_true("directory/manager/user/primarygroup/update", True):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: check primaryGroup')
			if not self.exists() and self.info.get('primaryGroup'):
				grpobj = group_mod.object(None, self.lo, self.position, self.info.get('primaryGroup'))
				grpobj.fast_member_add([self.dn], [new_uid])

	def __rewrite_member_uid(self, group, members=[]):
		uids = self.lo.getAttr(group, 'memberUid')
		if not members:
			members = self.lo.getAttr(group, 'uniqueMember')
		new_uids = []
		for memberDNstr in members:
			memberDN = ldap.dn.str2dn(memberDNstr)
			if memberDN[0][0][0] == 'uid':  # UID is stored in DN --> use UID directly
				new_uids.append(memberDN[0][0][1])
			else:
				UIDs = self.lo.getAttr(memberDNstr, 'uid')
				if UIDs:
					new_uids.append(UIDs[0])
					if len(UIDs) > 1:
						univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'users/user: A groupmember has multiple UIDs (%s %r)' % (memberDNstr, UIDs))
		self.lo.modify(group, [('memberUid', uids, new_uids)])

	def __primary_group(self):
		self.newPrimaryGroupDn = 0
		self.oldPrimaryGroupDn = 0
		if not self.hasChanged('primaryGroup'):
			return

		self.newPrimaryGroupDn = self['primaryGroup']
		if 'primaryGroup' in self.oldinfo:
			self.oldPrimaryGroupDn = self.oldinfo['primaryGroup']

		primaryGroupNumber = self.get_gid_for_primary_group()
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: set gidNumber')
		self.lo.modify(self.dn, [('gidNumber', 'None', primaryGroupNumber)])

		# Samba
		primaryGroupSambaNumber = self.get_sid_for_primary_group()
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: set sambaPrimaryGroupSID')
		self.lo.modify(self.dn, [('sambaPrimaryGroupSID', 'None', primaryGroupSambaNumber)])

		if univention.admin.baseConfig.is_true("directory/manager/user/primarygroup/update", True):
			new_uid = self.info.get('username')
			group_mod = univention.admin.modules.get('groups/group')
			grpobj = group_mod.object(None, self.lo, self.position, self.newPrimaryGroupDn)
			grpobj.fast_member_add([self.dn], [new_uid])
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: adding to new primaryGroup %s (uid=%s)' % (self.newPrimaryGroupDn, new_uid))

		self.save()

	def krb5_principal(self):
		domain = univention.admin.uldap.domain(self.lo, self.position)
		realm = domain.getKerberosRealm()
		if not realm:
			raise univention.admin.uexceptions.noKerberosRealm()
		return self['username'] + '@' + realm

	def _check_uid_gid_uniqueness(self):
		if not configRegistry.is_true("directory/manager/uid_gid/uniqueness", True):
			return
		# POSIX, Samba
		fg = univention.admin.filter.expression('gidNumber', self['uidNumber'])
		group_objects = univention.admin.handlers.groups.group.lookup(self.co, self.lo, filter_s=fg)
		if group_objects:
			raise univention.admin.uexceptions.uidNumberAlreadyUsedAsGidNumber('%r' % self["uidNumber"])

	def _ldap_pre_create(self):
		super(object, self)._ldap_pre_create()
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'users/user: dn was set to %s' % self.dn)

		if self['mailPrimaryAddress']:
			self['mailPrimaryAddress'] = self['mailPrimaryAddress'].lower()

		# request a new uidNumber or get lock for manually set uidNumber
		if self['uidNumber']:
			univention.admin.allocators.acquireUnique(self.lo, self.position, 'uidNumber', self['uidNumber'], 'uidNumber', scope='base')
		else:
			self['uidNumber'] = univention.admin.allocators.request(self.lo, self.position, 'uidNumber')
		self.alloc.append(('uidNumber', self['uidNumber']))

		self['gidNumber'] = self.get_gid_for_primary_group()

		self._check_uid_gid_uniqueness()

		# Ensure the primary Group has the samba option enabled
		if not self.lo.getAttr(self['primaryGroup'], 'sambaSID'):
			raise univention.admin.uexceptions.primaryGroupWithoutSamba(self['primaryGroup'])

	def _ldap_pre_ready(self):
		super(object, self)._ldap_pre_ready()

		# get lock for username
		try:
			self.alloc.append(('uid', univention.admin.allocators.request(self.lo, self.position, 'uid', value=self['username'])))
		except univention.admin.uexceptions.noLock:
			raise univention.admin.uexceptions.uidAlreadyUsed(self['username'])

		if not self.exists() or self.hasChanged('username'):
			check_prohibited_username(self.lo, self['username'])

		# get lock for mailPrimaryAddress
		if 'mail' in self.options and self['mailPrimaryAddress']:
			if not self.exists() or self.hasChanged('mailPrimaryAddress'):
				try:
					self.alloc.append(('mailPrimaryAddress', univention.admin.allocators.request(self.lo, self.position, 'mailPrimaryAddress', value=self['mailPrimaryAddress'])))
				except univention.admin.uexceptions.noLock:
					raise univention.admin.uexceptions.mailAddressUsed(self['mailPrimaryAddress'])

	def _ldap_addlist(self):
		al = super(object, self)._ldap_addlist()

		# Samba, POSIX
		if self['primaryGroup']:
			self.newPrimaryGroupDn = self['primaryGroup']

		# Samba
		self.userSid = self.__generate_user_sid(self['uidNumber'])
		al.append(('sambaSID', [self.userSid]))

		# Kerberos
		al.append(('krb5PrincipalName', [self.krb5_principal()]))
		al.append(('krb5MaxLife', '86400'))
		al.append(('krb5MaxRenew', '604800'))

		return al

	def _ldap_post_create(self):
		self._confirm_locks()
		self.__update_groups()
		self.__primary_group()

	def _ldap_post_modify(self):
		# POSIX
		self.__update_groups()
		self.__primary_group()

		if 'mail' in self.options and self.hasChanged('mailPrimaryAddress'):
			if self['mailPrimaryAddress']:
				univention.admin.allocators.confirm(self.lo, self.position, 'mailPrimaryAddress', self['mailPrimaryAddress'])
			else:
				univention.admin.allocators.release(self.lo, self.position, 'mailPrimaryAddress', self.oldinfo['mailPrimaryAddress'])

		# Samba
		if self.hasChanged('sambaRID'):
			univention.admin.allocators.confirm(self.lo, self.position, 'sid', self.userSid)

	def _ldap_pre_modify(self):
		if self.hasChanged('mailPrimaryAddress'):
			if self['mailPrimaryAddress']:
				self['mailPrimaryAddress'] = self['mailPrimaryAddress'].lower()

		if self.hasChanged('username'):
			username = self['username']
			try:
				newdn = 'uid=%s,%s' % (ldap.dn.escape_dn_chars(username), self.lo.parentDn(self.dn))
				self._move(newdn)
			finally:
				univention.admin.allocators.release(self.lo, self.position, 'uid', username)

		if self.hasChanged("uidNumber"):
			# this should never happen, as uidNumber is marked as unchangeable
			self._check_uid_gid_uniqueness()

	def _ldap_modlist(self):
		ml = univention.admin.handlers.simpleLdap._ldap_modlist(self)

		ml = self._modlist_samba_privileges(ml)
		ml = self._modlist_cn(ml)
		ml = self._modlist_gecos(ml)
		ml = self._modlist_display_name(ml)
		ml = self._modlist_krb_principal(ml)
		ml = self._modlist_krb5kdc_flags(ml)
		ml = self._modlist_password_change(ml)
		ml = self._modlist_samba_bad_pw_count(ml)
		ml = self._modlist_sambaAcctFlags(ml)
		ml = self._modlist_samba_kickoff_time(ml)
		ml = self._modlist_krb5_valid_end(ml)
		ml = self._modlist_shadow_expire(ml)
		ml = self._modlist_mail_forward(ml)
		ml = self._modlist_univention_person(ml)
		ml = self._modlist_home_share(ml)
		ml = self._modlist_samba_mungeddial(ml)
		ml = self._modlist_samba_sid(ml)

		return ml

	def _modlist_samba_privileges(self, ml):
		if self.hasChanged('sambaPrivileges'):
			# add univentionSambaPrivileges objectclass
			if self['sambaPrivileges']:
				ml.append(('objectClass', '', 'univentionSambaPrivileges'))  # TODO: check if exists already
		return ml

	def _modlist_cn(self, ml):
		cnAtts = univention.admin.baseConfig.get('directory/manager/usercn/attributes', "<firstname> <lastname>")
		prop = univention.admin.property()
		old_cn = self.oldattr.get('cn', [''])[0]
		cn = prop._replace(cnAtts, self)
		cn = cn.strip()
		if cn != old_cn:
			ml.append(('cn', old_cn, cn))
		return ml

	def _modlist_gecos(self, ml):
		if self.hasChanged(['firstname', 'lastname']):
			prop = self.descriptions['gecos']
			old_gecos = self.oldattr.get('gecos', [''])[0]
			gecos = prop._replace(prop.base_default, self)
			if old_gecos:
				current_gecos = prop._replace(prop.base_default, self.oldinfo)
				if current_gecos == old_gecos:
					ml.append(('gecos', old_gecos, gecos))
		return ml

	def _modlist_display_name(self, ml):
		# update displayName automatically if no custom value has been entered by the user and the name changed
		if self.info.get('displayName') == self.oldinfo.get('displayName') and (self.info.get('firstname') != self.oldinfo.get('firstname') or self.info.get('lastname') != self.oldinfo.get('lastname')):
			prop_displayName = self.descriptions['displayName']
			# check if options for property displayName are used
			if any([x in self.options for x in prop_displayName.options]):
				old_default_displayName = prop_displayName._replace(prop_displayName.base_default, self.oldinfo)
				# does old displayName match with old default displayName?
				if self.oldinfo.get('displayName', '') == old_default_displayName:
					# yes ==> update displayName automatically
					new_displayName = prop_displayName._replace(prop_displayName.base_default, self)
					ml.append(('displayName', self.oldattr.get('displayName', [''])[0], new_displayName))
		return ml

	def _modlist_krb_principal(self, ml):
		if self.hasChanged('username'):
			ml.append(('krb5PrincipalName', self.oldattr.get('krb5PrincipalName', []), [self.krb5_principal()]))
		return ml

	def _check_password_history(self, ml, pwhistoryPolicy):
		if self['overridePWHistory'] != '1':
			pwhistory = self.oldattr.get('pwhistory', [''])[0]

			if self.__pwAlreadyUsed(self['password'], pwhistory):
				raise univention.admin.uexceptions.pwalreadyused()

			if pwhistoryPolicy.pwhistoryLength is not None:
				newPWHistory = self.__getPWHistory(univention.admin.password.crypt(self['password']), pwhistory, pwhistoryPolicy.pwhistoryLength)
				ml.append(('pwhistory', self.oldattr.get('pwhistory', [''])[0], newPWHistory))

		return ml

	def _check_password_complexity(self, pwhistoryPolicy):
		if self['overridePWLength'] != '1':
			password_minlength = min(0, pwhistoryPolicy.pwhistoryPasswordLength) or self.password_length
			if len(self['password']) < password_minlength:
				raise univention.admin.uexceptions.pwToShort(_('The password is too short, at least %d characters needed!') % (password_minlength,))

			if pwhistoryPolicy.pwhistoryPasswordCheck:
				pwdCheck = univention.password.Check(self.lo)
				pwdCheck.enableQualityCheck = True
				try:
					pwdCheck.check(self['password'])
				except ValueError as e:
					raise univention.admin.uexceptions.pwQuality(str(e).replace('W?rterbucheintrag', 'Wörterbucheintrag').replace('enth?lt', 'enthält'))

	def _modlist_samba_password(self, ml, pwhistoryPolicy):
		password_nt, password_lm = univention.admin.password.ntlm(self['password'])
		ml.append(('sambaNTPassword', self.oldattr.get('sambaNTPassword', [''])[0], password_nt))
		ml.append(('sambaLMPassword', self.oldattr.get('sambaLMPassword', [''])[0], password_lm))

		if pwhistoryPolicy.pwhistoryLength is not None:
			smbpwhistory = self.oldattr.get('sambaPasswordHistory', [''])[0]
			newsmbPWHistory = self.__getsmbPWHistory(password_nt, smbpwhistory, pwhistoryPolicy.pwhistoryLength)
			ml.append(('sambaPasswordHistory', self.oldattr.get('sambaPasswordHistory', [''])[0], newsmbPWHistory))
		return ml

	def _modlist_kerberos_password(self, ml):
		if self.exists() and not self.hasChanged('password'):
			return ml

		krb_keys = univention.admin.password.krb5_asn1(self.krb5_principal(), self['password'])
		krb_key_version = str(int(self.oldattr.get('krb5KeyVersionNumber', ['0'])[0]) + 1)
		ml.append(('krb5Key', self.oldattr.get('krb5Key', []), krb_keys))
		ml.append(('krb5KeyVersionNumber', self.oldattr.get('krb5KeyVersionNumber', []), krb_key_version))
		return ml

	def _modlist_password_change(self, ml):
		ml = self._modlist_posix_password(ml)
		ml = self._modlist_kerberos_password(ml)

		modifypassword = not self.exists() or self.hasChanged('password')
		if not self.hasChanged('pwdChangeNextLogin') and not modifypassword:
			return ml

		pwhistoryPolicy = _PasswortHistoryPolicy(self.loadPolicyObject('policies/pwhistory'))

		if modifypassword:
			ml = self._check_password_history(ml, pwhistoryPolicy)
			self._check_password_complexity(pwhistoryPolicy)
			ml = self._modlist_samba_password(ml, pwhistoryPolicy)

		pwd_change_next_login = self.hasChanged('pwdChangeNextLogin') and self['pwdChangeNextLogin'] == '1'
		unset_pwd_change_next_login = self.hasChanged('pwdChangeNextLogin') and self['pwdChangeNextLogin'] == '0'

		if pwd_change_next_login:
			# force user to change password on next login
			shadowMax = "1"
		elif not pwhistoryPolicy.expiryInterval or unset_pwd_change_next_login:
			# 1. no pw expiry interval is defined or
			# 2. remove that user has to change password on next login
			shadowMax = ''
		else:
			shadowMax = pwhistoryPolicy.expiryInterval

		old_shadowMax = self.oldattr.get('shadowMax', [''])[0]
		if old_shadowMax != shadowMax:
			ml.append(('shadowMax', old_shadowMax, shadowMax))

		krb5PasswordEnd = ''
		if pwhistoryPolicy.expiryInterval or pwd_change_next_login:
			expiry = long(time.time())
			if not pwd_change_next_login:
				expiry = expiry + (pwhistoryPolicy.expiryInterval * 3600 * 24)
			expiry = time.strftime("%d.%m.%y", time.gmtime(expiry))
			krb5PasswordEnd = "%s" % "20" + expiry[6:8] + expiry[3:5] + expiry[0:2] + "000000Z"

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'krb5PasswordEnd: %s' % krb5PasswordEnd)
		old_krb5PasswordEnd = self.oldattr.get('krb5PasswordEnd', [''])[0]
		if old_krb5PasswordEnd != krb5PasswordEnd:
			ml.append(('krb5PasswordEnd', old_krb5PasswordEnd, krb5PasswordEnd))

		now = (long(time.time()) / 3600 / 24)
		shadowLastChange = ''
		if pwhistoryPolicy.expiryInterval or unset_pwd_change_next_login:
			shadowLastChange = str(int(now))
		if pwd_change_next_login:
			shadowLastChange = str(int(now) - int(shadowMax) - 1)

		if shadowLastChange:  # FIXME: this check causes, that the value is not unset. Is this correct?
			ml.append(('shadowLastChange', self.oldattr.get('shadowLastChange', [''])[0], shadowLastChange))

		# if pwdChangeNextLogin has been set, set sambaPwdLastSet to 0 (see UCS Bug #17890)
		# OLD behavior was: set sambaPwdLastSet to 1 (see UCS Bug #8292 and Samba Bug #4313)
		sambaPwdLastSetValue = '0' if pwd_change_next_login else str(long(time.time()))
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'sambaPwdLastSetValue: %s' % sambaPwdLastSetValue)
		ml.append(('sambaPwdLastSet', self.oldattr.get('sambaPwdLastSet', [''])[0], sambaPwdLastSetValue))

		return ml

	def _modlist_krb5kdc_flags(self, ml):
		if not self.exists() or self.hasChanged('disabled'):
			if self.__is_kerberos_disabled():  # disable kerberos account
				krb_kdcflags = '254'
			else:  # enable kerberos account
				krb_kdcflags = '126'
			ml.append(('krb5KDCFlags', self.oldattr.get('krb5KDCFlags', ['']), krb_kdcflags))
		return ml

	def _modlist_posix_password(self, ml):
		if not self.exists() or self.hasChanged('locked', 'password'):
			# FIXME: if self['password'] is not a crypted password (e.g. {SASL}, {KINIT}, etc.) and only the locked state changed we need to ignore this.
			if not self.__pwd_is_auth_saslpassthrough(self.oldattr.get('userPassword', [''])[0]):
				if self['locked'] in ['all', 'posix']:
					password_crypt = univention.admin.password.lock_password(self['password'])
				else:
					password_crypt = univention.admin.password.unlock_password(self['password'])
				ml.append(('userPassword', self.oldattr.get('userPassword', [''])[0], password_crypt))

		# remove pwdAccountLockedTime during unlocking
		if self.hasChanged('locked') and self['locked'] not in ['all', 'posix']:
			pwdAccountLockedTime = self.oldattr.get('pwdAccountLockedTime', [''])[0]
			if pwdAccountLockedTime:
				ml.append(('pwdAccountLockedTime', pwdAccountLockedTime, ''))

		return ml

	def _modlist_samba_bad_pw_count(self, ml):
		if self.hasChanged('locked'):
			if self['locked'] not in ['all', 'windows']:
				# reset bad pw count
				ml.append(('sambaBadPasswordCount', self.oldattr.get('sambaBadPasswordCount', [''])[0], "0"))
		return ml

	def _modlist_samba_kickoff_time(self, ml):
		if self.hasChanged('userexpiry'):
			sambaKickoffTime = ''
			if self['userexpiry']:
				sambaKickoffTime = "%d" % long(time.mktime(time.strptime(self['userexpiry'], "%Y-%m-%d")))
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'sambaKickoffTime: %s' % sambaKickoffTime)
			old_sambaKickoffTime = self.oldattr.get('sambaKickoffTime', '')
			if old_sambaKickoffTime != sambaKickoffTime:
				ml.append(('sambaKickoffTime', self.oldattr.get('sambaKickoffTime', [''])[0], sambaKickoffTime))
		return ml

	def _modlist_krb5_valid_end(self, ml):
		if self.hasChanged('userexpiry'):
			krb5ValidEnd = ''
			if self['userexpiry']:
				krb5ValidEnd = "%s%s%s000000Z" % (self['userexpiry'][0:4], self['userexpiry'][5:7], self['userexpiry'][8:10])
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'krb5ValidEnd: %s' % krb5ValidEnd)
			old_krb5ValidEnd = self.oldattr.get('krb5ValidEnd', '')
			if old_krb5ValidEnd != krb5ValidEnd:
				if not self['userexpiry']:
					ml.append(('krb5ValidEnd', old_krb5ValidEnd, '0'))
				else:
					ml.append(('krb5ValidEnd', self.oldattr.get('krb5ValidEnd', [''])[0], krb5ValidEnd))
		return ml

	def _modlist_shadow_expire(self, ml):
		if self.hasChanged('disabled') or self.hasChanged('userexpiry'):
			if self.__is_posix_disabled() and self.hasChanged('disabled') and not self.hasChanged('userexpiry'):
				shadowExpire = '1'
			elif self['userexpiry']:
				shadowExpire = "%d" % long(time.mktime(time.strptime(self['userexpiry'], "%Y-%m-%d")) / 3600 / 24 + 1)
			elif self.__is_posix_disabled():
				shadowExpire = '1'
			else:
				shadowExpire = ''

			old_shadowExpire = self.oldattr.get('shadowExpire', '')
			if old_shadowExpire != shadowExpire:
				ml.append(('shadowExpire', old_shadowExpire, shadowExpire))
		return ml

	def _modlist_mail_forward(self, ml):
		if self['mailForwardAddress'] and not self['mailPrimaryAddress']:
			raise univention.admin.uexceptions.missingInformation(_('Primary e-mail address must be set, if messages should be forwarded for it.'))
		if self.__forward_copy_to_self and not self['mailPrimaryAddress']:
			raise univention.admin.uexceptions.missingInformation(_('Primary e-mail address must be set, if a copy of forwarded messages should be stored in its mailbox.'))

		# remove virtual property mailForwardCopyToSelf from modlist
		ml = [(key_, old_, new_) for (key_, old_, new_) in ml if key_ != 'mailForwardCopyToSelf']

		# add mailPrimaryAddress to mailForwardAddress if "mailForwardCopyToSelf" is True
		for num_, (key_, old_, new_) in enumerate(ml[:]):
			if key_ == 'mailForwardAddress':
				# old in ml may be missing the mPA removed in open()
				if old_:
					ml[num_][1][:] = self.oldattr.get('mailForwardAddress')
				if new_:
					self.__remove_old_mpa(new_)
					self.__set_mpa_for_forward_copy_to_self(new_)
				break
		else:
			mod_ = (
				'mailForwardAddress',
				self.oldattr.get('mailForwardAddress', []),
				self['mailForwardAddress'][:]
			)
			if self['mailForwardAddress']:
				self.__remove_old_mpa(mod_[2])
				self.__set_mpa_for_forward_copy_to_self(mod_[2])
			if mod_[1] != mod_[2]:
				ml.append(mod_)
		return ml

	def _modlist_univention_person(self, ml):
		# make sure that univentionPerson is set as objectClass when needed
		if any(self.hasChanged(ikey) and self[ikey] for ikey in ('umcProperty', 'birthday')):
			ml.append(('objectClass', '', 'univentionPerson'))  # TODO: check if exists already

	def _modlist_home_share(self, ml):
		if self.hasChanged('homeShare') or self.hasChanged('homeSharePath'):
			if self['homeShare']:
				share_mod = univention.admin.modules.get('shares/share')
				try:
					share = share_mod.object(None, self.lo, self.position, self['homeShare'])
					share.open()
				except:
					raise univention.admin.uexceptions.noObject(_('DN given as share is not valid.'))

				if share['host'] and share['path']:
					ml.append(('objectClass', '', 'automount'))  # TODO: check if exists already

					am_host = share['host']
					if not self['homeSharePath'] or type(self['homeSharePath']) not in [types.StringType, types.UnicodeType]:
						raise univention.admin.uexceptions.missingInformation(_('%(homeSharePath)s must be given if %(homeShare)s is given.') % {'homeSharePath': _('Home share path'), 'homeShare': _('Home share')})
					else:
						am_path = os.path.abspath(os.path.join(share['path'], self['homeSharePath']))
						if not am_path.startswith(share['path']):
							raise univention.admin.uexceptions.valueError(_('%s: Invalid path') % _('Home share path'))

					am_old = self.oldattr.get('automountInformation', [''])[0]
					am_new = '-rw %s:%s' % (am_host, am_path)
					ml.append(('automountInformation', am_old, am_new))
				else:
					raise univention.admin.uexceptions.noObject(_('Given DN is no share.'))

			if not self['homeShare'] or not share['host'] or not share['path']:
				ml.append(('objectClass', 'automount', ''))  # TODO: check if not exists
				am_old = self.oldattr.get('automountInformation', [''])[0]
				if am_old:
					ml.append(('automountInformation', am_old, ''))
		return ml

	def _modlist_samba_mungeddial(self, ml):
		sambaMunged = self.sambaMungedDialMap()
		if sambaMunged:
			ml.append(('sambaMungedDial', self.oldattr.get('sambaMungedDial', ['']), [sambaMunged]))
		return ml

	def _modlist_samba_sid(self, ml):
		if self.hasChanged('sambaRID') and not hasattr(self, 'userSid'):
			self.userSid = self.__generate_user_sid(self.oldattr['uidNumber'][0])
			ml.append(('sambaSID', self.oldattr.get('sambaSID', ['']), [self.userSid]))
		return ml

	def _modlist_sambaAcctFlags(self, ml):
		if self.exists() and not self.hasChanged('disabled') and not self.hasChanged('locked'):
			return ml

		old_flags = self.oldattr.get("sambaAcctFlags", [''])[0]
		acctFlags = univention.admin.samba.acctFlags(old_flags)
		if self.__is_windows_disabled():
			# disable samba account
			acctFlags.set('D')
		else:
			# enable samba account
			acctFlags.unset('D')

		if self["locked"] in ['all', 'windows']:
			# lock samba account
			acctFlags.set('L')
		else:
			# unlock samba account
			acctFlags.unset("L")

		if str(old_flags) != str(acctFlags.decode()):
			ml.append(('sambaAcctFlags', old_flags, acctFlags.decode()))
		return ml

	def _ldap_post_remove(self):
		self.alloc.append(('sid', self.oldattr['sambaSID'][0]))
		self.alloc.append(('uid', self.oldattr['uid'][0]))
		self.alloc.append(('uidNumber', self.oldattr['uidNumber'][0]))
		if 'mail' in self.options and self['mailPrimaryAddress']:
			self.alloc.append(('mailPrimaryAddress', self['mailPrimaryAddress']))
		self._release_locks()

		groupObjects = univention.admin.handlers.groups.group.lookup(self.co, self.lo, filter_s=filter_format('uniqueMember=%s', [self.dn]))
		if groupObjects:
			uid = univention.admin.uldap.explodeDn(self.dn, 1)[0]
			for groupObject in groupObjects:
				groupObject.fast_member_remove([self.dn], [uid], ignore_license=1)

		admin_settings_dn = 'uid=%s,cn=admin-settings,cn=univention,%s' % (ldap.dn.escape_dn_chars(self['username']), self.lo.base)
		# delete admin-settings object of user if it exists
		try:
			self.lo.delete(admin_settings_dn)
		except univention.admin.uexceptions.noObject:
			pass

	def _move(self, newdn, modify_childs=True, ignore_license=False):
		olddn = self.dn
		tmpdn = 'cn=%s-subtree,cn=temporary,cn=univention,%s' % (ldap.dn.escape_dn_chars(self['username']), self.lo.base)
		al = [('objectClass', ['top', 'organizationalRole']), ('cn', ['%s-subtree' % self['username']])]
		subelements = self.lo.search(base=self.dn, scope='one', attr=['objectClass'])  # FIXME: identify may fail, but users will raise decode-exception
		if subelements:
			try:
				self.lo.add(tmpdn, al)
			except:
				# real errors will be caught later
				pass
			try:
				moved = dict(self.move_subelements(olddn, tmpdn, subelements, ignore_license))
				subelements = [(moved[subdn], subattrs) for (subdn, subattrs) in subelements]
			except:
				# subelements couldn't be moved to temporary position
				# subelements were already moved back to self
				# stop moving and reraise
				raise

		try:
			dn = super(object, self)._move(newdn, modify_childs, ignore_license)
		except:
			# self couldn't be moved
			# move back subelements and reraise
			self.move_subelements(tmpdn, olddn, subelements, ignore_license)
			raise

		if subelements:
			try:
				moved = dict(self.move_subelements(tmpdn, newdn, subelements, ignore_license))
				subelements = [(moved[subdn], subattrs) for (subdn, subattrs) in subelements]
			except:
				# subelements couldn't be moved to self
				# subelements were already moved back to temporary position
				# move back self, move back subelements to self and reraise
				super(object, self)._move(olddn, modify_childs, ignore_license)
				self.move_subelements(tmpdn, olddn, subelements, ignore_license)
				raise

		return dn

	def __pwAlreadyUsed(self, password, pwhistory):
		for line in pwhistory.split(" "):
			linesplit = line.split("$")  # $method_id$salt$password_hash
			try:
				password_hash = univention.admin.password.crypt(password, linesplit[1], linesplit[2])
			except IndexError:  # old style password history entry, no method id/salt in there
				hash_algorithm = hashlib.new("sha1")
				hash_algorithm.update(password.encode("utf-8"))
				password_hash = hash_algorithm.hexdigest().upper()
			if password_hash == line:
				return True
		return False

	def __getPWHistory(self, newpwhash, pwhistory, pwhlen):
		# split the history
		if len(string.strip(pwhistory)):
			pwlist = string.split(pwhistory, ' ')
		else:
			pwlist = []

		# this preserves a temporary disabled history
		if pwhlen > 0:
			if len(pwlist) < pwhlen:
				pwlist.append(newpwhash)
			else:
				# calc entries to cut out
				cut = 1 + len(pwlist) - pwhlen
				pwlist[0:cut] = []
				if pwhlen > 1:
					# and append to shortened history
					pwlist.append(newpwhash)
				else:
					# or replace the history completely
					if len(pwlist) > 0:
						pwlist[0] = newpwhash
						# just to be sure...
						pwlist[1:] = []
					else:
						pwlist.append(newpwhash)
		# and build the new history
		res = string.join(pwlist)
		return res

	def __getsmbPWHistory(self, newpassword, smbpwhistory, smbpwhlen):
		# split the history
		if len(string.strip(smbpwhistory)):
			pwlist = string.split(smbpwhistory, ' ')
		else:
			pwlist = []

		# calculate the password hash & salt
		salt = ''
		urandom = open('/dev/urandom', 'r')
		# get 16 bytes from urandom for salting our hash
		rand = urandom.read(16)
		for i in range(0, len(rand)):
			salt = salt + '%.2X' % ord(rand[i])
		# we have to have that in hex
		hexsalt = salt
		# and binary for calculating the md5
		salt = self.getbytes(salt)
		# we need the ntpwd binary data to
		pwd = self.getbytes(newpassword)
		# calculating hash. sored as a 32byte hex in sambePasswordHistory,
		# syntax like that: [Salt][MD5(Salt+Hash)]
		#	First 16bytes ^		^ last 16bytes.
		pwdhash = hashlib.md5(salt + pwd).hexdigest().upper()
		smbpwhash = hexsalt + pwdhash

		if len(pwlist) < smbpwhlen:
			# just append
			pwlist.append(smbpwhash)
		else:
			# calc entries to cut out
			cut = 1 + len(pwlist) - smbpwhlen
			pwlist[0:cut] = []
			if smbpwhlen > 1:
				# and append to shortened history
				pwlist.append(smbpwhash)
			else:
				# or replace the history completely
				if len(pwlist) > 0:
					pwlist[0] = smbpwhash
					# just to be sure...
					pwlist[1:] = []
				else:
					pwlist.append(smbpwhash)

		# and build the new history
		res = string.join(pwlist, '')
		return res

	def __allocate_rid(self, rid):
		searchResult = self.lo.search(filter='objectClass=sambaDomain', attr=['sambaSID'])
		domainsid = searchResult[0][1]['sambaSID'][0]
		sid = domainsid + '-' + rid
		try:
			userSid = univention.admin.allocators.request(self.lo, self.position, 'sid', sid)
			self.alloc.append(('sid', userSid))
		except univention.admin.uexceptions.noLock:
			raise univention.admin.uexceptions.sidAlreadyUsed(': %s' % rid)
		return userSid

	def __generate_user_sid(self, uidNum):
		# TODO: cleanup function
		userSid = None

		if self['sambaRID']:
			userSid = self.__allocate_rid(self['sambaRID'])
		else:
			if self.s4connector_present:
				# In this case Samba 4 must create the SID, the s4 connector will sync the
				# new sambaSID back from Samba 4.
				userSid = 'S-1-4-%s' % uidNum
			else:
				rid = rids_for_well_known_security_identifiers.get(self['username'].lower())
				if rid:
					userSid = self.__allocate_rid(rid)
				else:
					try:
						userSid = univention.admin.allocators.requestUserSid(self.lo, self.position, uidNum)
					except:
						pass
			if not userSid or userSid == 'None':
				num = uidNum
				while not userSid or userSid == 'None':
					num = str(int(num) + 1)
					try:
						userSid = univention.admin.allocators.requestUserSid(self.lo, self.position, num)
					except univention.admin.uexceptions.noLock:
						num = str(int(num) + 1)
				self.alloc.append(('sid', userSid))

		return userSid

	def getbytes(self, string):
		# return byte values of a string (for smbPWHistory)
		bytes = [int(string[i:i + 2], 16) for i in xrange(0, len(string), 2)]
		return struct.pack("%iB" % len(bytes), *bytes)

	@classmethod
	def unmapped_lookup_filter(cls):
		return univention.admin.filter.conjunction('&', [
			univention.admin.filter.expression('objectClass', 'posixAccount'),
			univention.admin.filter.expression('objectClass', 'shadowAccount'),
			univention.admin.filter.expression('objectClass', 'sambaSamAccount'),
			univention.admin.filter.expression('objectClass', 'krb5Principal'),
			univention.admin.filter.expression('objectClass', 'krb5KDCEntry'),
			univention.admin.filter.conjunction('!', [univention.admin.filter.expression('uidNumber', '0')]),
			univention.admin.filter.conjunction('!', [univention.admin.filter.expression('uid', '*$')]),
			univention.admin.filter.conjunction('!', [univention.admin.filter.expression('univentionObjectFlag', 'functional')]),
		])

	@classmethod
	def rewrite(cls, filter, mapping):
		if filter.variable == 'username':
			filter.variable = 'uid'
		elif filter.variable == 'firstname':
			filter.variable = 'givenName'
		elif filter.variable == 'lastname':
			filter.variable = 'sn'
		elif filter.variable == 'primaryGroup':
			filter.variable = 'gidNumber'

		elif filter.variable == 'disabled':
			if filter.value == 'none':
				filter.variable = '&(!(shadowExpire=1))(!(krb5KDCFlags=254))(!(|(sambaAcctFlags=[UD       ])(sambaAcctFlags'
				filter.value = '[ULD       ])))'
			elif filter.value == 'all':
				filter.variable = '&(shadowExpire=1)(krb5KDCFlags=254)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags'
				filter.value = '[ULD       ]))'
			elif filter.value == 'posix':
				filter.variable = 'shadowExpire'
				filter.value = '1'
			elif filter.value == 'kerberos':
				filter.variable = 'krb5KDCFlags'
				filter.value = '254'
			elif filter.value == 'windows':
				filter.variable = '|(sambaAcctFlags=[UD       ])(sambaAcctFlags'
				filter.value = '=[ULD       ])'
			elif filter.value == 'windows_kerberos':
				filter.variable = '&(krb5KDCFlags=254)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags'
				filter.value = '=[ULD       ]))'
			elif filter.value == 'windows_posix':
				filter.variable = '&(shadowExpire=1)(|(sambaAcctFlags=[UD       ])(sambaAcctFlags'
				filter.value = '=[ULD       ]))'
			elif filter.value == 'posix_kerberos':
				filter.variable = '&(shadowExpire=1)(krb5KDCFlags'
				filter.value = '254)'
			elif filter.value == '*':
				filter.variable = 'uid'

		elif filter.variable == 'locked':
			# substring match for userPassword is not possible
			if filter.value in ['posix', 'windows', 'all', 'none']:
				if filter.value == 'all':
					filter.variable = '|(sambaAcctFlags=[UL       ])(sambaAcctFlags'
					filter.value = '[ULD       ])'
					# filter.variable='|(sambaAcctFlags=[UL       ])(sambaAcctFlags=[ULD       ])(userPassword'
					# filter.value = '{crypt}!*)'
				if filter.value == 'windows':
					filter.variable = '|(sambaAcctFlags=[UL       ])(sambaAcctFlags'
					filter.value = '[ULD       ])'
				# if filter.value == 'posix':
				#	filter.variable='userPassword'
				#	filter.value = '{crypt}!*'
				if filter.value == 'none':
					# filter.variable='&(!(sambaAcctFlags=[UL       ]))(!(sambaAcctFlags=[ULD       ]))(!(userPassword'
					# filter.value = '{crypt}!*))'
					filter.variable = '&(!(sambaAcctFlags=[UL       ]))(!(sambaAcctFlags'
					filter.value = '[ULD       ]))'
			elif filter.value == '*':
				filter.variable = 'uid'
		else:
			univention.admin.mapping.mapRewrite(filter, mapping)


class _PasswortHistoryPolicy(object):
	pwhistoryLength = None
	pwhistoryPasswordLength = 0
	pwhistoryPasswordCheck = False
	expiryInterval = 0

	def __init__(self, pwhistoryPolicy):
		self.pwhistoryPolicy = pwhistoryPolicy
		if pwhistoryPolicy:
			try:
				self.pwhistoryLength = min(0, int(pwhistoryPolicy['length'] or 0))
			except ValueError:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'Corrupt Password history policy (history length): %r' % (pwhistoryPolicy.dn,))
			try:
				self.pwhistoryPasswordLength = min(0, int(pwhistoryPolicy['pwLength'] or 0))
			except ValueError:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'Corrupt Password history policy (password length): %r' % (pwhistoryPolicy.dn,))
			self.pwhistoryPasswordCheck = (pwhistoryPolicy['pwQualityCheck'] or '').lower() in ['true', '1']
			try:
				self.expiryInterval = min(0, int(pwhistoryPolicy['expiryInterval'] or 0))
			except ValueError:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, 'Corrupt Password history policy (expiry interval): %r' % (pwhistoryPolicy.dn,))


lookup = object.lookup
lookup_filter = object.lookup_filter


def identify(dn, attr, canonical=0):
	if '0' in attr.get('uidNumber', []) or '$' in attr.get('uid', [''])[0] or 'univentionHost' in attr.get('objectClass', []) or 'functional' in attr.get('univentionObjectFlag', []):
		return False
	required_ocs = {'posixAccount', 'shadowAccount', 'sambaSamAccount', 'person', 'krb5KDCEntry', 'krb5Principal'}
	ocs = set(attr.get('objectClass', []))
	return ocs & required_ocs == required_ocs
