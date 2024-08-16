# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ProjectMrpBomOperation(models.Model):
    _name = 'project.mrp.bom.operation'
    _description = 'Project bom operations'
    _order = "sequence, id"

    def _get_default_product_uom_id(self):
        return self.env['uom.uom'].search([], limit=1, order='id').id

    sequence = fields.Integer('Sequence', default=1,
                              help="Gives the sequence order when displaying.")
    name = fields.Char('Name')
    code = fields.Char('Code')
    description = fields.Char('Description')
    product_qty = fields.Float('Product Quantity', default=1.0)
    project_bom_id = fields.Many2one('project.mrp.bom', 'Parent Project BOM',
                                     related='project_bom_line_id.project_bom_id', store=True)
    project_bom_line_id = fields.Many2one('project.mrp.bom.line', 'Project Bom Line', required=True, index=True)
    product_tmpl_id = fields.Many2one('product.template', 'Product Template', related='product_id.product_tmpl_id')
    product_id = fields.Many2one('product.product', 'Product')
    product_uom_id = fields.Many2one('uom.uom', 'Product Unit of Measure',
                                     default=_get_default_product_uom_id,
                                     required=True,
                                     help="Unit of Measure (Unit of Measure) is the unit of measurement for the "
                                          "inventory control")
    # operation_id = fields.Many2one('mrp.routing.workcenter', 'Consumed in Operation',
    #                                help="The operation where the components are consumed, or the finished products "
    #                                     "created.")
    attribute_value_ids = fields.Many2many('product.attribute.value', string='Variants',
                                           help="BOM Product Variants needed form apply this line.")
    display_name = fields.Char('Display Name', compute='_compute_display_name')

    def _compute_display_name(self):
        for record in self:
            if record.code:
                record.display_name = "[%s] %s" % (record.code, record.name or '')
            else:
                record.display_name = "%s" % record.name or ''

    @api.onchange('product_qty')
    def onchange_product_qty(self):
        if self.project_bom_line_id and not self._context.get('block_by_import'):
            product_qty = sum([x.product_qty for x in self.project_bom_line_id.operation_ids])
            self.project_bom_line_id.product_qty = product_qty

    @api.onchange('product_tmpl_id')
    def onchange_product_tmpl_id(self):
        if not self._context.get('block_by_import'):
            if self.product_tmpl_id:
                return {'domain': {'product_id': [('product_tmpl_id', '=', self.product_tmpl_id)]}}
            else:
                return {'domain': {'product_id': []}}

    @api.onchange('product_id')
    def onchange_product_id(self):
        res = {}
        if self.product_id and not self._context.get('block_by_import'):
            self.product_uom_id = self.product_id.uom_id.id
            res['domain'] = {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
            project_bom_id = self.project_bom_id
            if self._context.get('default_project_bom_id') and not project_bom_id:
                project_bom_id = self.env['project.mrp.bom'].browse(self._context['default_project_bom_id'])
                self.project_bom_id = project_bom_id
            project_bom_line_ids = self.env['project.mrp.bom.line']
            product_tmpl_id = self.product_id.product_tmpl_id
            product_type_id = product_tmpl_id.categ_id.get_product_type_id()

            if product_tmpl_id.product_type_id:
                product_type_id = product_tmpl_id.product_type_id
            for bom_line in project_bom_id.project_bom_line_ids:
                _logger.info("TEMPLATE %s" % bom_line.product_tmpl_id)
                if bom_line.product_tmpl_id == product_tmpl_id:
                    project_bom_line_ids |= bom_line
            _logger.info("NEW ROW %s(%s)(%s)::%s" % (product_tmpl_id,
                                                     product_type_id,
                                                     project_bom_line_ids,
                                                     project_bom_id.mapped('project_bom_line_ids').mapped(
                                                         'product_tmpl_id')))
            if not project_bom_line_ids:
                project_bom_line_ids = self.project_bom_id.project_bom_line_ids.create({
                    'product_tmpl_id': product_tmpl_id.id,
                    'product_type_id': product_type_id and product_type_id.id or False,
                    'product_uom_id': product_tmpl_id.uom_id.id,
                    'product_qty': self.product_qty,
                })
            if self.project_bom_line_id != project_bom_line_ids[0]:
                self.project_bom_line_id = project_bom_line_ids[0]
        return res

    def duplicate(self):
        for record in self:
            record.project_bom_line_id.operation_ids |= record.copy()

    def transfer_variants(self):
        for record in self:
            product_value_ids = record.product_id.product_template_attribute_value_ids
            project_bom_id = record.project_bom_line_id.project_bom_id
            bom_value_ids = project_bom_id.product_tmpl_id.attribute_line_ids.mapped('attribute_id').mapped('value_ids')

            # _logger.info("TRANSFER %s:%s" % (product_value_ids, bom_value_ids))
            if any(x in bom_value_ids.ids for x in product_value_ids.ids):
                mixed = product_value_ids & bom_value_ids
                record.attribute_value_ids = [(6, False, mixed.ids)]
