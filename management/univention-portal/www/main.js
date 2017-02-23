/*
 * Copyright 2016-2017 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dijit/registry",
	"dojo/on",
	"dojo/dom",
	"dojo/promise/all",
	"umc/tools",
	"./PortalCategory",
	"put-selector/put",
	"umc/json!/univention/meta.json"
], function(declare, lang, array, registry, on, dom, all, tools, PortalCategory, put, meta) {
	return {
		portalCategories: null,

		_getInstalledAppsInDomain: function() {
			return tools.umcpCommand('portal/getInstalledAppsInDomain', {}).then(lang.hitch(this, function(data) {
				return data.result;
			}));
		},

		// return an individual app object for every
		// individual installation on multiple servers
		_getAppsPerDomain: function(installedApps) {
			var apps = [];

			array.forEach(installedApps, function(iApp) {
				tools.forIn(iApp.installations, function(hostName, info) {
					var isInstalledOnHost = info.version;
					if (isInstalledOnHost) {
						var app = {
							name: iApp.name,
							description: iApp.description,
							web_interface: iApp.web_interface,
							logo_name: iApp.logo_name,
							id: iApp.id,
							host_ips: info.ip,
							host_name: hostName
						};
						apps.push(app);
					}
				});
			});

			return apps;
		},

		_createCategories: function() {
			this.portalCategories = [];

			var title = 'Management';
			var apps = [{
				name: 'Management',
				description: 'Administrate the UCS domain and the local system',
				web_interface: '/univention/management',
				logo_name: 'univention-management-console',
				host_name: meta.ucr.hostname
			}];
			this._addCategory(title, apps);

			this._getInstalledAppsInDomain().then(lang.hitch(this, function(installedApps) {
				var title = 'Installed Apps';
				var apps = this._getAppsPerDomain(installedApps);
				this._addCategory(title, apps);
			}));
		},

		_addCategory: function(title, apps) {
			var portalCategory = new PortalCategory({
				title: title,
				apps: apps,
				domainName: meta.ucr.domainname
			});
			this.content.appendChild(portalCategory.domNode);
			this.portalCategories.push(portalCategory);
		},

		start: function() {
			this.content = dom.byId('content');
			this.search = registry.byId('umcLiveSearch');
			this.search.on('search', lang.hitch(this, 'filterPortal'));
			this._createCategories();
		},
		
		filterPortal: function() {
			var searchPattern = lang.trim(this.search.get('value'));
			var searchQuery = this.search.getSearchQuery(searchPattern);

			var query = function(app) {
				return searchQuery.test(app);
			};

			array.forEach(this.portalCategories, function(category) {
				category.set('query', query);
			});
		}
	};
});