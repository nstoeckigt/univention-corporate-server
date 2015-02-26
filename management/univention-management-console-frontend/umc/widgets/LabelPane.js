/*
 * Copyright 2011-2015 Univention GmbH
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
/*global define console */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/Deferred",
	"dojo/dom-class",
	"dojo/dom-attr",
	"dijit/_WidgetBase",
	"dijit/_TemplatedMixin",
	"dijit/_Container",
	"umc/tools"
], function(declare, lang, array, Deferred, domClass, attr, _WidgetBase, _TemplatedMixin, _Container, tools) {
	lang.extend(_WidgetBase, {
		// displayLabel: Boolean?
		//		If specified as false, LabelPane will not display the label value.
		//		This property is specified by `umc/widgets/LabelPane`.
		displayLabel: true,

		// labelPosition: String?
		labelPosition: '',

		// visible: Boolean?
		//		If set to false, the label and widget will be hidden.
		visible: true
	});

	return declare("umc.widgets.LabelPane", [ _WidgetBase, _TemplatedMixin, _Container ], {
		// summary:
		//		Simple widget that displays a widget/HTML code with a label above.

		templateString: '<div class="umcLabelPane">' +
			'<span class="umcLabelPaneLabelNode umcLabelPaneLabeNodeTop"><label dojoAttachPoint="labelNodeTop" for=""></label></span>' +
			'<span dojoAttachPoint="containerNode,contentNode"></span>' +
			'<span class="umcLabelPaneLabelNode umcLabelPaneLabeNodeRight"><label dojoAttachPoint="labelNodeRight" for=""></label></span>' +
			'<div class="umcLabelPaneLabelNode umcLabelPaneLabeNodeBottom"><label dojoAttachPoint="labelNodeBottom" for=""></label></div>' +
			'</div>',

		// content: String|dijit/_WidgetBase
		//		String which contains the text (or HTML code) to be rendered or
		//		a dijit/_WidgetBase instance.
		content: '',

		// disabled: Boolean
		//		if the content of the label pane should be disabled. the
		//		content widgets must support it
		disabled: false,

		// the widget's class name as CSS class
		baseClass: 'umcLabelPane',

		// labelConf: Object
		//		Dictionary with properties (e.g., "style") that will mixed
		//		directly into the label widget.
		labelConf: null,

		// label: String
		label: null,

		labelNodeTop: null,

		labelNodeBottom: null,

		labelNodeRight: null,

		_startupDeferred: null,

		_orgClass: '',

		constructor: function(params) {
			this._startupDeferred = new Deferred();

			// lang._mixin() would not work sometimes, leaving this.content empty, see
			//   https://forge.univention.org/bugzilla/show_bug.cgi?id=26214#c3
			tools.forIn(params, function(ikey, ival) {
				this[ikey] = ival;
			}, this);
		},

		postMixInProperties: function() {
			this.inherited(arguments);

			// if we have a widget as content and label is not specified, use the widget's
			// label attribute
			if (null === this.label || undefined === this.label) {
				this.label = this.content.label || '';
			}

			// mix labelConf properties into 'this' scope
			if (this.content && 'labelConf' in this.content && this.content.labelConf) {
				lang.mixin(this, this.content.labelConf);
			}

			// save the initial value for class
			this._orgClass = this['class'];
		},

		_isContentAWidget: function() {
			return lang.getObject('content.domNode', false, this) &&
				lang.getObject('content.declaredClass', false, this) &&
				lang.getObject('content.watch', false, this);
		},

		_isContentRequired: function() {
			return lang.getObject('content.required', false, this) === true;
		},

		_isContentVisible: function() {
			return lang.getObject('content.visible', false, this) !== false;
		},

		_isLabelDisplayed: function () {
			return lang.getObject('content.displayLabel', false, this) !== false;
		},

		_getContentID: function() {
			return lang.getObject('content.id', false, this);
		},

		_getContentSizeClass: function() {
			return lang.getObject('content.sizeClass', false, this);
		},

		_getLabelPosition: function() {
			return lang.getObject('content.labelPosition', false, this) || 'bottom';
		},

		_getLabelNode: function() {
			// determine the position of the label
			var labelPosition = this._getLabelPosition();
			if (labelPosition === 'top') {
				return this.labelNodeTop;
			} else if (labelPosition === 'right') {
				return this.labelNodeRight;
			}

			// default label node is below widget
			return this.labelNodeBottom;
		},

		buildRendering: function() {
			this.inherited(arguments);
			domClass.toggle(this.domNode, 'dijitHidden', !this._isContentVisible());
		},

		postCreate: function() {
			this.inherited(arguments);

			// register watch handler for label and visibility changes
			if (this._isContentAWidget()) {
				if (this._isLabelDisplayed()) {
					// only watch the label and required property if widget is not a button
					this.own(this.content.watch('label', lang.hitch(this, function(attr, oldVal, newVal) {
						this.set('label', this.content.get('label') || '');
					})));
					this.own(this.content.watch('required', lang.hitch(this, function(attr, oldVal, newVal) {
						this.set('label', this.content.get('label') || '');
					})));
				}
				this.own(this.content.watch('visible', lang.hitch(this, function(attr, oldVal, newVal) {
					domClass.toggle(this.domNode, 'dijitHidden', !newVal);
				})));
			}
			else if (typeof this.label != "string") {
				this.label = '';
			}
		},

		startup: function() {
			this.inherited(arguments);

			this._startupDeferred.resolve();
		},

		_forEachLabeNode: function(callback) {
			array.forEach([this.labelNodeTop, this.labelNodeRight, this.labelNodeBottom], callback, this);
		},

		_hideNodes: function(exceptOfThisNode) {
			this._forEachLabeNode(function(inode) {
				domClass.toggle(inode, 'dijitHidden', exceptOfThisNode != inode);
			});
		},

		_setLabelAttr: function(label) {
			if (!this._isLabelDisplayed()) {
				// the widget displays the label itself
				this._hideNodes();
				return;
			}

			// if we have a widget which is required, add the string ' (*)' to the label
			if (this._isContentAWidget() && this._isContentRequired()) {
				label = label + ' *';
			}
			this.label = label;

			// set the label itself and show the corresponding label node
			var labelNode = null;
			if (label) {
				labelNode = this._getLabelNode();
				attr.set(labelNode, 'innerHTML', label);
			}
			this._hideNodes(labelNode);

			// set the labels' 'for' attribute
			var id = this._getContentID();
			if (labelNode && this._isContentAWidget() && id) {
				attr.set(labelNode, 'for', id);
			}
		},

//TODO: this seems to be obsolete and can be removed
//		_setBetweenNonCheckBoxesAttr: function(betweenNonCheckBoxes) {
//			if (betweenNonCheckBoxes && this.content.isInstanceOf(DijitCheckBox)) {
//				domClass.add(this.domNode, 'umcLabelPaneCheckBoxBetweenNonCheckBoxes');
//			}
//		},

		_setContentAttr: function(content) {
			this.content = content;

			// we have a string
			if (typeof content == "string") {
				this.contentNode.innerHTML = content;
			}
			// if we have a widget, clear the content and hook in the domNode directly
			else if (this._isContentAWidget()) {
				this.contentNode.innerHTML = '';
				this.addChild(content);
			}

			// set the content's size class
			var sizeClass = this._getContentSizeClass();
			if (sizeClass) {
				domClass.add(this.domNode, 'umcSize-' + sizeClass);
			}

			if (this._isContentAWidget()) {
				// add extra CSS classes based on the content type
				var contentClasses = this.content.baseClass.split(/\s+/);
				var labelClasses = array.map(contentClasses, function(iclass) {
					return this.baseClass + '-' + iclass;
				}, this);
				labelClasses.push(this._orgClass);
				this.set('class', labelClasses);
			}

			this.set('disabled', this.disabled);
		},

		_setDisabledAttr: function(value) {
			if (this._isContentAWidget()) {
				this.content.set('disabled', value);
			}
		}
	});
});
