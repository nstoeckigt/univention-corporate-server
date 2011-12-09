#!/bin/bash
#
# Copyright (C) 2010-2011 Univention GmbH
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

export DEBIAN_FRONTEND=noninteractive

UPDATER_LOG="/var/log/univention/updater.log"
UPDATE_LAST_VERSION="$1"
UPDATE_NEXT_VERSION="$2"
PACKAGES_TO_BE_PURGED="kcontrol libusplash0 univention-usplash-theme usplash libnjb5 univention-shares"
PACKAGES_TO_BE_REMOVED="nagios2 nagios2-common nagios2-doc"

install ()
{
	DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir -y --force-yes install $1 >>"$UPDATER_LOG" 2>&1
}
reinstall ()
{
	DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir -y --force-yes --reinstall install $1 >>"$UPDATER_LOG" 2>&1
}
check_and_install ()
{
	state="$(dpkg --get-selections $1 2>/dev/null | awk '{print $2}')"
	if [ "$state" = "install" ]; then
		install $1
	fi
}
check_and_reinstall ()
{
	state="$(dpkg --get-selections $1 2>/dev/null | awk '{print $2}')"
	if [ "$state" = "install" ]; then
		reinstall $1
	fi
}

echo -n "Running postup.sh script:"
echo >> "$UPDATER_LOG"
date >>"$UPDATER_LOG" 2>&1

eval "$(univention-config-registry shell)" >>"$UPDATER_LOG" 2>&1

## for p in univention-xen; do
## 	check_and_install $p
## done
## 
## for p in libxenstore3.0; do
## 	check_and_reinstall $p
## done

if [ -z "$server_role" ] || [ "$server_role" = "basesystem" ] || [ "$server_role" = "basissystem" ]; then
	install univention-basesystem
elif [ "$server_role" = "domaincontroller_master" ]; then
	install univention-server-master
elif [ "$server_role" = "domaincontroller_backup" ]; then
	install univention-server-backup  >>"$UPDATER_LOG" 2>&1
elif [ "$server_role" = "domaincontroller_slave" ]; then
	install univention-server-slave
elif [ "$server_role" = "memberserver" ]; then
	install univention-server-member
elif [ "$server_role" = "mobileclient" ]; then
	install univention-mobile-client
elif [ "$server_role" = "fatclient" ] || [ "$server_role" = "managedclient" ]; then
	install univention-managed-client
fi

# hold on dash update #22557
if [ "$(dpkg-query -W -f='${Status}\n' dash 2>/dev/null)" = "hold ok installed" ]; then
	if [ "$update30_hold_dash" = "true" ]; then
		echo "dash install" | dpkg --set-selections
		install dash
		univention-config-registry unset update30/hold/dash >>"$UPDATER_LOG" 2>&1
	fi
else
	echo "dash install" | dpkg --set-selections
fi




DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Options::=--force-confold -o DPkg::Options::=--force-overwrite -o DPkg::Options::=--force-overwrite-dir -y --force-yes dist-upgrade >>"$UPDATER_LOG" 2>&1

# # https://forge.univention.org/bugzilla/show_bug.cgi?id=18529
# if [ -x /usr/sbin/update-initramfs ]; then
#	update-initramfs -u -k all >>"$UPDATER_LOG" 2>&1
# fi

# remove statoverride for UMC; required to ensure that UCM is not restarted during update (always required)
if [ -e /usr/sbin/univention-management-console-server ]; then
	dpkg-statoverride --remove /usr/sbin/univention-management-console-server >/dev/null 2>&1
	chmod +x /usr/sbin/univention-management-console-server 2>> "$UPDATER_LOG"  >> "$UPDATER_LOG"
fi
if [ -e /usr/sbin/apache2 ]; then
	dpkg-statoverride --remove /usr/sbin/apache2 >/dev/null 2>&1
	chmod +x /usr/sbin/apache2 2>> "$UPDATER_LOG"  >> "$UPDATER_LOG"
fi

# Enable usplash after update (Bug #16363) (always required)
if dpkg -l lilo 2>> "$UPDATER_LOG" >> "$UPDATER_LOG" ; then
	dpkg-divert --rename --divert /usr/share/initramfs-tools/bootsplash.debian --remove /usr/share/initramfs-tools/hooks/bootsplash 2>> "$UPDATER_LOG" >> "$UPDATER_LOG"
fi

# univention-squid might be held back due squid still being installed
if [ "$update30_squidpresent" = "true" ]; then
    univention-install univention-squid  >>"$UPDATER_LOG" 2>&1
    univention-config-registry unset update30/squidpresent >>"$UPDATER_LOG" 2>&1
    dpkg --purge squid 2>> "$UPDATER_LOG" >> "$UPDATER_LOG"
fi

# univention-dansguardian is upgraded frm univention-antivir-web
if [ "$update30_dansguardianpresent" = "true" ]; then
    univention-install univention-dansguardian  >>"$UPDATER_LOG" 2>&1
    univention-config-registry unset update30/dansguardianpresent >>"$UPDATER_LOG" 2>&1
fi

# remove obsolte packages, no more required after UCS 3.0-0 update
# Bug #22997
for package in $PACKAGES_TO_BE_PURGED; do
	dpkg -P $package 2>> "$UPDATER_LOG"  >> "$UPDATER_LOG"
	if [ ! 0 -eq $? ]; then
		echo "Puring package $package failed: $?" >> "$UPDATER_LOG"
	fi
done

for package in $PACKAGES_TO_BE_REMOVED; do
	dpkg --remove "$package" 2>> "$UPDATER_LOG"  >> "$UPDATER_LOG"
	if [ ! 0 -eq $? ]; then
		echo "Removing package $package failed: $?" >> "$UPDATER_LOG"
	fi
done

if [ "$server_role" = "domaincontroller_master" ]; then
	echo "Increase priority for some system SRV records from 0 to 100" >>"$UPDATER_LOG" 2>&1 
	/usr/share/univention-directory-manager-tools/change_srv_priority.py >>"$UPDATER_LOG" 2>&1
fi

if [ -n "$update30_kde_check" -a "$update30_kde_check" = "true" ]; then
	if [ -n "$update30_kde_univentionkde" -a "$update30_kde_univentionkde" = "true" ]; then
		install univention-kde
		univention-config-registry unset update30/kde/univentionkde  >>"$UPDATER_LOG" 2>&1
	fi
	if [ -n "$update30_kde_kdepim" -a "$update30_kde_kdepim" = "true" ]; then
		install kdepim
		univention-config-registry unset update30/kde/kdepim  >>"$UPDATER_LOG" 2>&1
	fi
	if [ -n "$update30_kde_kdemultimedia" -a "$update30_kde_kdemultimedia" = "true" ]; then
		install kdemultimedia
		univention-config-registry unset update30/kde/kdemultimedia  >>"$UPDATER_LOG" 2>&1
	fi
	univention-config-registry unset update30/kde/check  >>"$UPDATER_LOG" 2>&1
fi

if [ -n "$update30_uvmm_check" -a "$update30_uvmm_check" = "true" ]; then
	if [ -n "$update30_uvmm_univentionxen" -a "$update30_uvmm_univentionxen" = "true" ]; then
		install univention-xen
		univention-config-registry unset update30/uvmm/univentionxen  >>"$UPDATER_LOG" 2>&1
	fi
	if [ -n "$update30_uvmm_univentionvirtualmachinemanagerdaemon" -a "$update30_uvmm_univentionvirtualmachinemanagerdaemon" = "true" ]; then
		install univention-virtual-machine-manager-daemon
		univention-config-registry unset update30/uvmm/univentionvirtualmachinemanagerdaemon  >>"$UPDATER_LOG" 2>&1
	fi
	if [ -n "$update30_uvmm_univentionvirtualmachinemanagernodexen" -a "$update30_uvmm_univentionvirtualmachinemanagernodexen" = "true" ]; then
		install univention-virtual-machine-manager-node-xen
		univention-config-registry unset update30/uvmm/univentionvirtualmachinemanagernodexen  >>"$UPDATER_LOG" 2>&1
	fi
	if [ -n "$update30_uvmm_univentionvirtualmachinemanagernodekvm" -a "$update30_uvmm_univentionvirtualmachinemanagernodekvm" = "true" ]; then
		install univention-virtual-machine-manager-node-kvm
		univention-config-registry unset update30/uvmm/univentionvirtualmachinemanagernodekvm  >>"$UPDATER_LOG" 2>&1
	fi
	univention-config-registry unset update30/uvmm/check  >>"$UPDATER_LOG" 2>&1
fi

# removes temporary sources list (always required)
if [ -e "/etc/apt/sources.list.d/00_ucs_temporary_installation.list" ]; then
	rm -f /etc/apt/sources.list.d/00_ucs_temporary_installation.list
fi

# remove old sysklogd startup links (Bug #23143)
update-rc.d -f sysklogd remove 2>> "$UPDATER_LOG"  >> "$UPDATER_LOG"

# create /etc/python2.6/sitecustomize.py
univention-config-registry commit /etc/python2.6/sitecustomize.py >>"$UPDATER_LOG" 2>&1

# restore menu.lst: for grub1 chainload into grub2 (no more required after UCS 3.0-0 update)
if [ -e /boot/grub/menu.lst.ucs3.0-0 ]; then
	cp /boot/grub/menu.lst.ucs3.0-0 /boot/grub/menu.lst
fi
# end restore menu.lst

# UCS 3.0 add univentionObjectType 
if [ "$server_role" = "domaincontroller_master" ]; then

	omscript="/usr/share/univention-directory-manager-tools/univention-object-type-migrate"

	if [ ! "$update_objecttype_check" = "no" -a ! "$update_objecttype_check" = "false" -a ! "$update_objecttype_check" = "1" ]; then
		dcs=$(univention-ldapsearch  -x objectClass=univentionDomainController -LLL dn | grep ^dn:| wc -l)
		if [ -n "$dcs" -a "$dcs" -eq 1 ]; then
			# only one dc -> update univentionObjectType
			echo
			echo -n "updating univentionObjectType ... "
			$omscript -a -v >>"$UPDATER_LOG" 2>&1
			echo "done"
			echo
		else
			# multiple dc's -> print a message 
			echo 
			echo "To increase the performance of the Univention Director Manager (UDM) the"
			echo "internal storage of the UDM objects was adapted. To update existing objects,"
			echo "the script \"$(basename $omscript)\" can be used. This script changes"
			echo "all the objects in the LDAP directory and therefore must be called manually"
			echo "on the Domain Controller Master:"
			echo
			echo "-> $omscript -a -v"
			echo 
			echo "Additional information can be found in the release notes."
			echo
			
		fi
	fi
fi
# univentionObjectType end

# executes custom postup script (always required)
if [ ! -z "$update_custom_postup" ]; then
	if [ -f "$update_custom_postup" ]; then
		if [ -x "$update_custom_postup" ]; then
			echo -n "Running custom postupdate script $update_custom_postup"
			"$update_custom_postup" "$UPDATE_LAST_VERSION" "$UPDATE_NEXT_VERSION" >>"$UPDATER_LOG" 2>&1
			echo "Custom postupdate script $update_custom_postup exited with exitcode: $?" >>"$UPDATER_LOG" 2>&1
		else
			echo "Custom postupdate script $update_custom_postup is not executable" >>"$UPDATER_LOG" 2>&1
		fi
	else
		echo "Custom postupdate script $update_custom_postup not found" >>"$UPDATER_LOG" 2>&1
	fi
fi

if [ -x /usr/sbin/univention-check-templates ]; then
	/usr/sbin/univention-check-templates >>"$UPDATER_LOG" 2>&1
	rc=$?
	if [ "$rc" != 0 ]; then
		if [ "$rc" = 1 ]; then
			echo "Warning: $rc UCR template was not updated. Please check $UPDATER_LOG or execute univention-check-templates as root."
		else
			echo "Warning: $rc UCR templates were not updated. Please check $UPDATER_LOG or execute univention-check-templates as root."
		fi
	fi
fi

## BEGIN Bug #25380 (only for UCS 3.0-0)
# set smtpd restrictions for postfix
if [ ! "$update_bugfix25380_disabled" = "yes" ] ; then
	univention-config-registry set \
		mail/postfix/smtpd/restrictions/recipient/10="permit_mynetworks" \
		mail/postfix/smtpd/restrictions/recipient/30="permit_sasl_authenticated" \
		mail/postfix/smtpd/restrictions/recipient/50="reject_unauth_destination" \
		mail/postfix/smtpd/restrictions/recipient/70="reject_unlisted_recipient"
	invoke-rc.d postfix restart
fi
## END Bug #25380


## BEGIN Bug #24413
ucr set gdm/autostart="$(ucr get gdm/autostart/update30backup)" >&3 2>&3
ucr unset gdm/autostart/update30backup >&3 2>&3
eval "$(ucr shell gdm/autostart)"
if [ -x /etc/init.d/gdm -a ! "$gdm_autostart" = "no" -a ! "$gdm_autostart" = "false" ] ; then
	echo "Restarting gdm"
	/etc/init.d/gdm start >&3 2>&3
fi
## END Bug #24413

# For UCS 3.0 a reboot is required
univention-config-registry set update/reboot/required=true >>"$UPDATER_LOG" 2>&1

echo "done."
date >>"$UPDATER_LOG" 2>&1

exit 0

