# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, tools, SUPERUSER_ID, _

_logger = logging.getLogger(__name__)


class ProjectMrpProductTypes(models.Model):
    _name = 'project.product.types'
    _description = 'Type of products'
    _order = 'sequence, id'

    sequence = fields.Integer(default=1)
    name = fields.Char('Name', translate=True)
    code = fields.Char('Code')
