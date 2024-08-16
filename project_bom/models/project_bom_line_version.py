# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ProjectMrpBomLineVersion(models.Model):
    _name = 'project.mrp.bom.line.version'
    _description = 'Project bom line version'
    _order = 'bom_line_id, version'

    def _get_default_product_uom_id(self):
        return self.env['uom.uom'].search([], limit=1, order='id').id

    bom_line_id = fields.Many2one('project.mrp.bom.line',
                                  'BOM Line version',
                                  required=True,
                                  ondelete='cascade')
    version = fields.Char('Version',
                          required=True,
                          index=True)
    product_id = fields.Many2one('product.product',
                                 'Component',
                                 required=True,
                                 check_company=True)
    product_tmpl_id = fields.Many2one('product.template',
                                      'Product Template',
                                      related='product_id.product_tmpl_id',
                                      store=True,
                                      index=True)
    company_id = fields.Many2one(related='bom_line_id.company_id',
                                 store=True,
                                 index=True,
                                 readonly=True)
    product_qty = fields.Float('Quantity',
                               default=1.0,
                               digits='Product Unit of Measure',
                               required=True)
    product_uom_id = fields.Many2one('uom.uom',
                                     'Product Unit of Measure',
                                     default=_get_default_product_uom_id,
                                     required=True,
                                     help="Unit of Measure (Unit of Measure) is the unit of "
                                          "measurement for the inventory control",
                                     domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')

    _sql_constraints = [
        ('bom_line_id_version_uniq', 'unique(bom_line_id, version)', 'Version already exists!')
    ]
