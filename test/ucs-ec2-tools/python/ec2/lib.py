# -*- coding: utf-8 -*-
# vim:set shiftwidth=4 tabstop=4:
#
# Copyright 2013 Univention GmbH
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

import ConfigParser
import re
import os
import paramiko
import subprocess
import sys
import glob
import time
import traceback
from socket import error as socket_error
from select import select
try:
	from shlex import quote
except ImportError:
	from pipes import quote

import boto
from boto.ec2 import regions, blockdevicemapping

PATH_UCS_KT_GET = '/usr/bin/ucs-kt-get'

def mac2IPv6linklocal(mac):
	"""
	Converta mac address into a IPv6 link local address.
	>>> mac2IPv6linklocal('0:1:2:3:4:5')
	'fe80::0201:02ff:fe03:0405'
	>>> mac2IPv6linklocal('52:54:00:eb:7c:79')
	'fe80::5054:00ff:feeb:7c79'
	"""
	octets = [int(_, 16) for _ in mac.split(':')]
	octets[0] &= ~1  # clear broadcast bit
	octets[0] ^= 2  # flip universal/local bit
	octets = octets[0:3] + [0xff, 0xfe] + octets[3:6]
	groups = ['%02x%02x' % _ for _ in zip(octets[0::2], octets[1::2])]
	return 'fe80::' + ':'.join(groups)


def _split_config(lines):
	"""
	Iterate over lines of config option.
	"""
	for line in lines.split('\n'):
		line = line.strip()
		if not line:
			continue
		if line.startswith('#'):
			continue
		yield line

class VM:
	"""
	Generic instance.
	"""
	def __init__(self, section, config, virtualisation):
		''' Initialize a VM instance '''
		self.section = section
		self.virtualisation = virtualisation

		self.private_key = None
		if config.has_option('Global', 'ec2_keypair_file'):
			self.private_key = os.path.expanduser(config.get('Global', 'ec2_keypair_file'))

		# Save the profile, it will be later written to the VM
		try:
			self.profile = config.get(section, 'profile')
		except ConfigParser.NoOptionError:
			self.profile = None

		# Read and save the file lines and ignore comments
		try:
			lines = config.get(section, 'files')
			self.files = list(_split_config(lines))
		except ConfigParser.NoOptionError:
			self.files = []

		# list of commands
		self.commands = []
		while True:
			try:
				commands = config.get(self.section,
						'command%d' % (len(self.commands) + 1,))
			except ConfigParser.NoOptionError:
				break
			cmds = list(_split_config(commands))
			self.commands.append(cmds)

		# logfile
		for sname in (section, 'Global'):
			if config.has_option(sname, 'logfile'):
				self.logfile = os.path.expanduser(config.get(sname, 'logfile'))
				break

		# Create the logfile
		if self.logfile:
			log = open(self.logfile, 'a+')
			log.write('Created instance %s at %s\n' % (section, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())))
			log.close()
		self.logfile_fd = None

		self.ec2 = None       # EC2 only
		self.instance = None
		self.server = None    # KVM only
		self.client = None
		self.sftp = None


	def _wait_instance(self, timeout=300):
		"""
		Wait until instance is created.
		"""
		start = now = time.time()
		while now - start < timeout:
			if self.instance.state == 'running':
				break
			if self.instance.state == 'pending':
				self._log('Pending %d...' % (timeout - now + start))
			time.sleep(10)

			try:
				self.instance.update()
			except boto.exception.EC2ResponseError, ex:
				for error in ex.errors:
					self._log('Error code: %r', error.error_code)
					if error.error_code == 'InvalidInstanceID.NotFound':
						break
				else:
					self._log('Unexcpected error waiting for instance: %s', ex)
					raise
			now = time.time()
		else:
			self._log('Timeout waiting for instance')
			raise

	def connect(self):
		''' Wait until the connection is ready '''
		self.client = paramiko.SSHClient()
		self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		start = now = time.time()
		# TODO: make the timeout configurable
		timeout = 300
		while now - start < timeout:
			try:
				if self.virtualisation in ('ec2',):
					self.client.connect(self.get_ip(),
										port=22,
										username='root',
										key_filename=self.private_key),
				elif self.virtualisation in ('kvm',):
					self.client.connect(self.get_ip(),
										port=22,
										username='root',
										password='univention',
										)
				else:
					raise Exception('No virtualisation defined')

				break
			except socket_error:
				self._log('Pending %d...'  % (timeout - now + start))
				time.sleep(5)
				now = time.time()
			except paramiko.AuthenticationException:
				self._log('Authentication failed %d...' % (timeout - now + start))
				time.sleep(5)
				now = time.time()
			except Exception, ex:
				self._log('Unknown error "%s"...'  % (str(ex)))
				self._log('Pending %d...'  % (timeout - now + start))
				time.sleep(5)
				now = time.time()
		else:
			raise

	def create_profiles(self):
		''' Write the given profile to the instance '''
		if not self.profile:
			return

		self._open_sftp_connection()

		remote_profile = self.sftp.file('/var/cache/univention-system-setup/profile', 'w')
		print >> remote_profile, self.profile
		remote_profile.close()

		self._close_sftp_connection()

	def copy_files(self):
		''' Copy the given files to the instance '''
		if not self.files:
			return

		self._open_sftp_connection()

		for line in self.files:
			localfiles, remotedir = line.rsplit(' ', 1)
			expanded_files = glob.glob(os.path.expanduser(localfiles))
			self._remote_mkdir(remotedir)

			for localfile in expanded_files:
				if os.path.exists(localfile):
					fname = os.path.basename(localfile)
					remfile = os.path.join(remotedir, fname)
					self.sftp.put(localfile, remfile)
					self.sftp.chmod(remfile, os.stat(localfile).st_mode & 0777)

		self._close_sftp_connection()

	def _exec_local(self, cmdline):
		"""
		Execute local command redirecting output to local logfile.
		"""
		self._log('Execute local command: %s' % cmdline)

		self._open_logfile()

		ret = subprocess.call(cmdline, shell=True, stdout=self.logfile_fd, stderr=self.logfile_fd)

		self._close_logfile()

		return ret

	def _open_logfile(self):
		"""
		Open internal self.logfile.
		"""
		if self.logfile:
			self.logfile_fd = open(self.logfile, 'a+')
		else:
			self.logfile_fd = sys.stdout

	def _close_logfile(self):
		"""
		Close internal self.logfile.
		"""
		if self.logfile_fd:
			self.logfile_fd.close()
		self.logfile_fd = None

	def run_commands(self, phase):
		''' Run all commands for a given phase e.g. for command1 '''
		for cmdline in self.commands[phase]:
			try:
				_print_process('  %s' % cmdline)
				if cmdline.startswith('LOCAL'):
					cmdline = cmdline[len('LOCAL'):]
					ret = self._exec_local(cmdline)
				else:
					ret = self._ssh_exec(cmdline)
				if ret != 0:
					_print_done('fail: return code %s' % ret)
				else:
					_print_done()
			except paramiko.ssh_exception.SSHException:
				self.connect()
				try:
					ret = self._ssh_exec(cmdline)
					if ret != 0:
						_print_done('fail: return code %s' % ret)
					else:
						_print_done()
				except Exception:
					self._print_exception_to_file()
					_print_done('fail')
			except Exception:
				self._print_exception_to_file()
				_print_done('fail')

	def _print_exception_to_file(self):
		"""
		Write current exception to self.logfile.
		"""
		self._open_logfile()
		traceback.print_exc(file=self.logfile_fd)
		self._close_logfile()

	def command_count(self):
		''' Retrun the  IP address of the started VM '''
		return len(self.commands)

	def get_ip(self):
		''' Retrun the IP address of the started VM '''
		if self.instance.vpc_id:
			return self.instance.private_ip_address
		else:
			return self.instance.ip_address

	def get_name(self):
		'''	Return the configured name for the VM, this is the section for
			this host in the config file '''
		return '[%s]' % self.section

	# Helper functions
	def _ssh_exec(self, command, sshconnection=None):
		'''	Execute command using ssh and writes output to logfile.
			sshconnection defines, which ssh connection shall be used - default is self.client.
		'''
		if sshconnection:
			transport = sshconnection.get_transport()
		else:
			transport = self.client.get_transport()
		transport.set_keepalive(15)
		session = transport.open_session()
		try:
			self._log('Execute: %s' % command)
			session.exec_command(command)
			# Close STDIN for remote command
			session.shutdown_write()
			while True:
				r_list, _w_list, _e_list = select([session], [], [], 10)
				if r_list:
					if session.recv_ready():
						data = session.recv(4096)
						self._log(data, newline=False)
						continue
					elif session.recv_stderr_ready():
						data = session.recv_stderr(4096)
						self._log(data, newline=False)
						continue
					else:
						pass  # EOF
				if session.exit_status_ready():
					break
			if session.exit_status != 0:
				self._log('*** Failed %d: %s' % (session.exit_status, command))
		finally:
			session.close()
		return session.exit_status

	def _ssh_exec_get_data(self, command, sshconnection=None, log_stdout=False, log_stderr=True):
		'''	Execute command using ssh and writes output to logfile.
			sshclient defines, which ssh connection shall be used - default is self.client.
		'''
		if sshconnection:
			transport = sshconnection.get_transport()
		else:
			transport = self.client.get_transport()
		transport.set_keepalive(15)
		session = transport.open_session()
		stdout = ''
		stderr = ''
		try:
			self._log('Execute: %s' % command)
			session.exec_command(command)
			# Close STDIN for remote command
			session.shutdown_write()
			while True:
				r_list, _w_list, _e_list = select([session], [], [], 10)
				if r_list:
					if session.recv_ready():
						data = session.recv(4096)
						stdout += data
						if log_stdout:
							self._log(data, newline=False)
						continue
					elif session.recv_stderr_ready():
						data = session.recv_stderr(4096)
						stderr += data
						if log_stderr:
							self._log(data, newline=False)
						continue
					else:
						pass  # EOF
				if session.exit_status_ready():
					break
			if session.exit_status != 0:
				self._log('*** Failed %d: %s' % (session.exit_status, command))
		finally:
			session.close()
		return session.exit_status, stdout, stderr


	def _open_sftp_connection(self):
		'''	Open the SFTP connection and save the connection as self.sftp '''
		self.sftp = self.client.open_sftp()

	def _close_sftp_connection(self):
		'''	Close the SFTP connection '''
		self.sftp.close()

	def _remote_mkdir(self, directory):
		'''	Helpder function to create the given directory structure through
			the SFTP connection '''
		if not directory.startswith('/'):
			return

		try:
			if os.path.exists(directory):
				mode = os.stat(directory).st_mode & 0777
			else:
				mode = 0777
			self.sftp.mkdir(directory, mode=mode)
		except IOError:
			self._remote_mkdir(directory.rsplit("/", 1)[0])

	# Write a message to the log file
	def _log(self, msg, newline=True):
		'''	Write a message to self.logfile '''
		if self.logfile:
			lfile = open(self.logfile, 'a+')
			lfile.write(str(msg))
			if newline:
				lfile.write('\n')
			lfile.close()
		else:
			print 'I: no logfile is configured, print to stdout'
			print msg


class VM_KVM(VM):
	def __init__(self, section, config):
		''' Initialize a VM instance in local KVM environment '''
		params = [ 'kvm_server',
				   'kvm_ucsversion',
				   'kvm_architecture',
				   'kvm_template',
				   'kvm_interface',
				   'ec2_keypair' ]
		for key in params:
			if not config.has_option(section, key):
				if config.has_option('Global', key):
					config.set(section, key, config.get('Global', key))

		VM.__init__(self, section, config, 'kvm')

		self.config = config

	def start(self):
		''' Start the VM '''
		self.server = paramiko.SSHClient()
		self.server.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		kvm_server = self.config.get(self.section, 'kvm_server')
		try:
			self.server.connect(kvm_server,
								port=22)
		except socket_error, e:
			self._log('Failed to connect to %s...'  % (kvm_server,))
			_print_done('fail (%s)' % (str(e)))
			time.sleep(2)
			sys.exit(1)

		transport = self.server.get_transport()
		transport.set_keepalive(15)

		kvm_name_short = '%s' % (self.section,)
		kvm_name_full = '%s_%s' % (os.getenv('USER'), self.section,)

		cmdline = '%s -y -V %s -A %s -l %s %s' % (
			quote(PATH_UCS_KT_GET),
			quote(self.config.get(self.section, 'kvm_ucsversion')),
			quote(self.config.get(self.section, 'kvm_architecture')),
			quote(kvm_name_short),
			quote(self.config.get(self.section, 'kvm_template')),
			)

		self._log('  %s' % cmdline)
		rt, stdout, stderr = self._ssh_exec_get_data(cmdline, self.server)
		if rt != 0:
			_print_done('fail (return code %s)' % rt)
			print stdout
			print stderr
			sys.exit(1)
		else:
			_print_done()

		cmdline = 'sudo /usr/bin/virsh dumpxml %s' % (
				quote(kvm_name_full),
				)
		_print_process('Detecting IPv6 address')
		rt, stdout, stderr = self._ssh_exec_get_data(cmdline, self.server)
		if rt:
			_print_done('fail (return code %s)' % rt)
			sys.exit(1)
		match = re.search('mac address=.([0-9a-f:]+)', stdout)
		if not match:
			_print_done('failed to get mac address')
			sys.exit(1)

		self.instance = { 'section': self.section,
						  'mac': match.group(1),
						  'ipv6': '%s%%%s' % (mac2IPv6linklocal(match.group(1)), self.config.get(self.section, 'kvm_interface')),
						  }
		self._log('Instance %(section)s: MAC=%(mac)s  IPv6=%(ipv6)s' % self.instance)

	def get_ip(self):
		''' Return the IP address of the started VM '''
		return self.instance['ipv6']


class VM_EC2(VM):
	def __init__(self, section, config):
		''' Initialize a VM instance '''
		self.aws_cfg = {}

		# Copy some global settings to the local VM config
		# but only if the setting is not set in the local VM section
		params = [
				'ec2_ami',
				'ec2_security_group',
				'ec2_instance_type',
				'ec2_keypair',
				'ec2_region',
				'ec2_subnet_id',
				'ec2_partition_size',
				]
		for key in params:
			if not config.has_option(section, key):
				if config.has_option('Global', key):
					config.set(section, key, config.get('Global', key))

		for key in params + ['ec2_reuse']:
			if config.has_option(section, key):
				self.aws_cfg[key] = config.get(section, key)

		VM.__init__(self, section, config, 'ec2')

	def _get_blockdevicemapping(self):
		"""
		Create explicit block device with given size.
		"""
		bdm = None
		if self.aws_cfg.get('ec2_partition_size'):
			dev_sda1 = blockdevicemapping.EBSBlockDeviceType(
					size = self.aws_cfg.get('ec2_partition_size'),
					delete_on_termination=True,
					)
			bdm = blockdevicemapping.BlockDeviceMapping()
			bdm['/dev/sda1'] = dev_sda1
		return bdm

	def start(self):
		''' Start the VM '''
		# self.ec2 = boto.connect_ec2(**self.aws_cfg)
		aws_cfg = {}
		for region in regions(**aws_cfg):
			if region.name == self.aws_cfg['ec2_region']:
				aws_cfg['region'] = region
				break

		env_vars = ('JOB_NAME', 'BUILD_NUMBER')
		user_data = '\n'.join(['%s=%s' % (v, os.getenv(v, '')) for v in env_vars])

		self.ec2 = boto.connect_ec2(**aws_cfg)
		reuse = self.aws_cfg.get('ec2_reuse')
		if reuse:
			reservation = self.ec2.get_all_instances(instance_ids=[reuse])[0]
		elif self.aws_cfg.get('ec2_subnet_id'):
			ami = self.ec2.get_image(self.aws_cfg['ec2_ami'])
			reservation = ami.run(min_count=1,
				max_count=1,
				key_name=self.aws_cfg['ec2_keypair'],
				subnet_id=self.aws_cfg['ec2_subnet_id'],
				user_data=user_data,
				security_group_ids=[self.aws_cfg['ec2_security_group']],
				instance_type=self.aws_cfg['ec2_instance_type'],
				instance_initiated_shutdown_behavior='terminate',  # 'save'
				block_device_map=self._get_blockdevicemapping()
				)
		else:
			ami = self.ec2.get_image(self.aws_cfg['ec2_ami'])
			reservation = ami.run(min_count=1,
				max_count=1,
				key_name=self.aws_cfg['ec2_keypair'],
				user_data=user_data,
				security_groups=[self.aws_cfg['ec2_security_group']],
				instance_type=self.aws_cfg['ec2_instance_type'],
				instance_initiated_shutdown_behavior='terminate',  # 'save'
				block_device_map=self._get_blockdevicemapping()
				)

		self.instance = reservation.instances[0]

		self._wait_instance()

		self.instance.add_tag('Name', 'Test-%s-%s' % (os.getenv('USER'), self.section))
		self.instance.add_tag('class', 'ucs-test')
		for var in env_vars:
			self.instance.add_tag(var.lower(), os.getenv(var, ''))



def _print_process(msg):
	'''	Print s status line '''
	if len(msg) > 64:
		print '%s..' % msg[:63],
	else:
		print '%-65s' % msg,
	sys.stdout.flush()

def _print_done(msg='done'):
	'''	Close the status line opend with _print_process '''
	print '%s' % msg
	sys.stdout.flush()


class Parser(ConfigParser.ConfigParser):
	"""
	Extended config parser providing ordered sections.
	"""
	def set_filename(self, filename):
		"""
		Remember the filename.
		"""
		self._filename = filename

	def hosts(self):
		''' Gives a list of all sections expect Global '''
		hosts = []
		ifile = open(self._filename, 'r')
		for line in ifile:
			if line.strip() == '' or line[0] in '#;':
				continue
			match = ConfigParser.ConfigParser.SECTCRE.match(line)
			if match:
				sectname = match.group('header')
				if sectname != 'Global':
					hosts.append(sectname)
		ifile.close()
		return hosts
