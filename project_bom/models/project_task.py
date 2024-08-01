# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, exceptions, fields, models

class Task(models.Model):
    _inherit = "project.task"

    project_mrp_ids = fields.One2many('project.mrp.bom', 'task_id', string='Project MRP Bom')
    mrp_product_tmpl_id = fields.Many2one('product.template', 'Product Template')
    mrp_product_id = fields.Many2one('product.product', 'Product')
    project_mrp_count = fields.Integer('Count Project Bom', compute='_compute_project_mrp_count')

    @api.multi
    def _compute_project_mrp_count(self):
        for record in self:
            record.project_mrp_count = len(record.project_mrp_ids.ids)

    @api.multi
    def action_create_mrp_bom(self):
        for record in self:
            if record.mrp_product_tmpl_id or record.mrp_product_id:
                mrp_product_tmpl_id = record.mrp_product_tmpl_id
                if not mrp_product_tmpl_id and record.project_id:
                    mrp_product_tmpl_id = record.mrp_product_id.product_tmpl_id
                bom_lines_ids = []
                for line in record.material_ids:
                    product_tmpl_id = line.product_id.product_tmpl_id
                    product_type_id = product_tmpl_id.categ_id.get_product_type_id()
                    if product_tmpl_id.product_type_id:
                        product_type_id = product_tmpl_id.product_type_id
                    bom_lines_ids.append((0, False, {
                        'product_tmpl_id': product_tmpl_id.id,
                        'product_type_id': product_type_id and product_type_id.id or False,
                        'product_uom_id': product_tmpl_id.uom_id.id,
                        'product_qty': line.quantity,
                    }))
                project_bom_id = self.env['project.mrp.bom'].create({
                    'code': record.name,
                    'version': '01.01',
                    'product_tmpl_id': mrp_product_tmpl_id.id,
                    'product_id': record.mrp_product_id and record.mrp_product_id.id or False,
                    'type': 'normal',
                    'company_id': self.env.user.company_id.id,
                    'product_qty': 1.0,
                    'task_id': record.id,
                    'project_bom_line_ids': bom_lines_ids and bom_lines_ids or False,
                })
