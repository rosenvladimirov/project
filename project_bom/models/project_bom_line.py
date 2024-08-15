# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, _
from odoo.models import NewId

_logger = logging.getLogger(__name__)


class ProjectMrpBomLine(models.Model):
    _name = 'project.mrp.bom.line'
    _description = 'Project bom lines'
    _order = "sequence, id"
    # _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'mrp.bom.line': 'bom_line_id'}

    def _get_default_product_uom_id(self):
        return self.env['uom.uom'].search([], limit=1, order='id').id

    sequence = fields.Integer('Sequence',
                              default=1,
                              help="Gives the sequence order when displaying.")
    project_bom_id = fields.Many2one('project.mrp.bom',
                                     'Parent Project BOM',
                                     index=True,
                                     ondelete='cascade',
                                     required=True)
    company_id = fields.Many2one('res.company',
                                 related='project_bom_id.company_id',
                                 store=True)
    bom_line_id = fields.Many2one('mrp.bom.line',
                                  'BOM Line',
                                  required=True,
                                  ondelete='restrict')
    version_ids = fields.One2many('project.mrp.bom.line.version',
                                 'bom_line_id',
                                 'Versions')
    project_product_id = fields.Many2one('product.product',
                                         'Component',
                                         required=True,
                                         check_company=True)
    project_product_uom_category_id = fields.Many2one(related='project_product_id.uom_id.category_id')
    project_product_uom_id = fields.Many2one(
        'uom.uom', 'Product Unit of Measure',
        default=_get_default_product_uom_id,
        required=True,
        help="Unit of Measure (Unit of Measure) is the unit of measurement for the inventory control",
        domain="[('category_id', '=', project_product_uom_category_id)]")

    project_product_qty = fields.Float('Quantity', default=1.0, digits='Product Unit of Measure', required=True)
    project_operation_id = fields.Many2one('mrp.routing.workcenter',
                                           'Consumed in Operation',
                                           check_company=True,
                                           domain="[('id', 'in', allowed_operation_ids)]",
                                           help="The operation where the components are consumed, "
                                                "or the finished products created.")
    approve = fields.Boolean('Approved')

    def action_approve(self, product_id):
        for record in self:
            if isinstance(record.id, NewId):
                break
            project_bom_id = record.project_bom_id
            version = self.env['project.mrp.bom.line.version'].search([
                ('bom_line_id', '=', record.id), ('version', '=', project_bom_id.version)
            ])
            if record.approve:
                record.bom_line_id.product_id = record.project_product_id
                record.bom_line_id.product_uom_id = record.project_product_uom_id
                record.bom_line_id.product_qty = record.project_product_qty
                if not version:
                    record.version_ids.create({
                        'bom_line_id': record.id,
                        'version': project_bom_id.version,
                        'product_id': record.project_product_id.id,
                        'product_uom_id': record.project_product_uom_id.id,
                        'product_qty': record.project_product_qty,
                    })
            elif not record.approve and version:
                record.bom_line_id.product_id = version.product_id
                record.bom_line_id.product_uom_id = version.product_uom_id
                record.bom_line_id.product_qty = version.product_qty
            # record.project_bom_id
