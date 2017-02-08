/*
 * Copyright 2015-2017 Univention GmbH
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
	"dojo/_base/lang",
	"dojo/on",
	"dojo/keys",
	"dojo/dom",
	"dojo/json",
	"dojo/request/xhr",
	"dijit/form/Button",
	"put-selector/put",
	"umc/tools",
	"./TextBox",
	"./PasswordBox",
	"./lib",
	"umc/i18n!."
], function(lang, on, keys, dom, json, xhr, Button, put, tools, TextBox, PasswordBox, lib, _) {

	return {
		title: _('Password change'),
		desc: _('Change your (expired) password.'),
		hash: 'passwordchange',
		contentContainer: null,
		steps: null,

		/**
		 * Returns the title of the subpage.
		 * */
		getTitle: function() {
			return _(this.title);
		},

		/**
		 * Returns the description of the subpage.
		 * */
		getDesc: function() {
			return _(this.desc);
		},

		/**
		 * Return the content node of the subpage.
		 * If the content does not exists, it will be generated.
		 * */
		getContent: function() {
			if (!this.contentContainer) {
				this.contentContainer = put('div.contentWrapper');
				put(this.contentContainer, 'div.contentDesc', this.getDesc());
				put(this.contentContainer, this._getSteps());
			}
			return this.contentContainer;
		},

		/**
		 * Return the steps for the content node.
		 * If the steps do not exists, they will be generated.
		 * Note: Please call getContent for generating the steps.
		 * */
		_getSteps: function() {
			if (!this.steps) {
				this.steps = put('ol#PasswordChangeSteps.PasswordOl');
				this._createUsername();
				this._createOldPassword();
				this._createNewPassword();
				this._createSubmit();
			}
			return this.steps;
		},

		/**
		 * Creates input field for username.
		 * */
		_createUsername: function() {
			var step = put('li.step');
			var label = put('div.stepLabel', _('Username'));
			put(step, label);
			this._username = new TextBox({
				'class': 'soloLabelPane',
				isValid: function() {
					return !!this.get('value');
				},
				required: true
			});
			this._username.startup();
			put(step, this._username.domNode);
			put(this.steps, step);
		},

		/**
		 * Creates input field for old password.
		 * */
		_createOldPassword: function() {
			var step = put('li.step');
			var label = put('div.stepLabel', _('Old Password'));
			put(step, label);
			this._oldPassword = new TextBox({
				'class': 'soloLabelPane',
				type: 'password',
				isValid: function() {
					return !!this.get('value');
				},
				required: true
			});
			this._oldPassword.startup();
			put(step, this._oldPassword.domNode);
			put(this.steps, step);
		},

		/**
		 * Creates input fields for new password.
		 * */
		_createNewPassword: function() {
			var step = put('li.step');
			var label = put('div.stepLabel', _('New Password'));
			put(step, label);
			this._newPassword = new PasswordBox({
				'class': 'soloLabelPane left'
			});
			this._newPassword.startup();
			put(step, this._newPassword.domNode);
			put(this.steps, step);

			step = put('li.step');
			label = put('div.stepLabel', _('New Password (retype)'));
			put(step, label);
			this._verifyPassword = new TextBox({
				type: 'password',
				'class': 'soloLabelPane',
				isValid: lang.hitch(this, function() {
					return this._newPassword.get('value') ===
						this._verifyPassword.get('value');
				}),
				invalidMessage: _('The passwords do not match, please retype again.'),
				required: true
			});
			this._verifyPassword.startup();
			put(step, this._verifyPassword.domNode);
			put(this.steps, step);
		},

		/**
		 * Creates submit button.
		 * */
		_createSubmit: function() {
			var step = put('div');
			this._submitButton = new Button({
				label: _('Change password'),
				onClick: lang.hitch(this, '_setPassword')
			});
			put(step, '>', this._submitButton.domNode);

			// let the user submit the form by pressing ENTER
			on(document, "keyup", lang.hitch(this, function(evt) {
				if (evt.keyCode === keys.ENTER && !this._submitButton.get('disabled')) {
					this._setPassword();
				}
			}));
			put(this.steps, step);
		},

		/**
		 * Changes the current password if all input fields are valid.
		 * */
		_setPassword: function() {
			this._submitButton.set('disabled', true);
			var allInputFieldsAreValid = this._username.isValid() &&
				this._oldPassword.isValid() &&
				this._newPassword.isValid() &&
				this._verifyPassword.isValid();

			if (allInputFieldsAreValid) {
				var data = {
					password: {
						'username': this._username.get('value'),
						'password': this._oldPassword.get('value'),
						'new_password': this._newPassword.get('value')
					}
				};

				tools.umcpCommand('set', data).then(lang.hitch(this, function(data) {
					lib._removeMessage();
					var callback = function() {
						lib.showLastMessage({
							content: data.message,
							'class': '.success'
						});
					};
					lib.wipeOutNode({
						node: dom.byId('form'),
						callback: callback
					});
					this._clearAllInputFields();
				}), lang.hitch(this, function(err) {
					lib.showMessage({content: err.message, 'class': '.error'});
				})).always(lang.hitch(this, function(){
					this._submitButton.set('disabled', false);
				}));
			} else {
				this._submitButton.set('disabled', false);
			}
		},

		/**
		 * Clears all input field values of the subpage.
		 * */
		_clearAllInputFields: function() {
			this._username.reset();
			this._oldPassword.reset();
			this._newPassword.reset();
			this._verifyPassword.reset();
		}
	};
});