# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, tools, _

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _inherit = "product.category"

    product_type_id = fields.Many2one('project.product.types', 'Product Type')

    def get_product_type_id(self):
        product_type_id = False
        for record in self:
            product_type_id = record.product_type_id
            parent_id = record.parent_id
            while parent_id:
                product_type_id = parent_id.product_type_id and parent_id.product_type_id or product_type_id
                parent_id = parent_id.parent_id
        return product_type_id


class ProductTemplate(models.Model):
    _inherit = "product.template"

    product_type_id = fields.Many2one('project.product.types', 'Product Type')
    direct_standard_price = fields.Float(
        'Cost',
        compute='_compute_direct_standard_price',
        inverse='_set_direct_standard_price',
        search='_search_direct_standard_price')
    project_bom_count = fields.Integer(
        '# Bill of Material',
        compute='_compute_project_bom_count')

    def _compute_project_bom_count(self):
        read_group_res = self.env['project.mrp.bom'].read_group([('product_tmpl_id', 'in', self.ids)],
                                                                ['product_tmpl_id'],
                                                                ['product_tmpl_id'])
        mapped_data = dict([(data['product_tmpl_id'][0], data['product_tmpl_id_count']) for data in read_group_res])
        for product in self:
            product.project_bom_count = mapped_data.get(product.id, 0)

    @api.depends('product_variant_ids', 'product_variant_ids.direct_standard_price')
    def _compute_direct_standard_price(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.direct_standard_price = template.product_variant_ids.direct_standard_price
        for template in (self - unique_variants):
            template.direct_standard_price = 0.0

    def _set_direct_standard_price(self):
        if len(self.product_variant_ids) == 1:
            self.product_variant_ids.direct_standard_price = self.direct_standard_price

    def _search_direct_standard_price(self, operator, value):
        products = self.env['product.product'].search([('direct_standard_price', operator, value)], limit=None)
        return [('id', 'in', products.mapped('product_tmpl_id').ids)]



class ProductProduct(models.Model):
    _inherit = "product.product"

    direct_standard_price = fields.Float('Cost', company_dependent=True)
