# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, tools, _
from odoo.addons import decimal_precision as dp

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _inherit = "product.category"

    product_type_id = fields.Many2one('project.product.types', 'Product Type')

    def get_product_type_id(self):
        product_type_id = False
        for record in self:
            product_type_id = record.product_type_id
            parent_id = record.parent_id
            # _logger.info("CATEG-1 %s" % parent_id)
            while parent_id:
                # _logger.info("CATEG %s" % parent_id)
                product_type_id = parent_id.product_type_id and parent_id.product_type_id or product_type_id
                parent_id = parent_id.parent_id
        return product_type_id


class ProductTemplate(models.Model):
    _inherit = "product.template"

    product_type_id = fields.Many2one('project.product.types', 'Product Type')
    direct_standard_price = fields.Float(
        'Cost', compute='_compute_direct_standard_price',
        inverse='_set_direct_standard_price', search='_search_standard_price',
        digits=dp.get_precision('Product Price'), groups="base.group_user")
    project_bom_count = fields.Integer('# Bill of Material', compute='_compute_project_bom_count')
    remote_available = fields.Float('Quantity On Hand', compute='_compute_remote_available',
                                    search='_search_remote_available', digits=dp.get_precision('Product Unit of Measure'))

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


    @api.depends('product_variant_ids')
    def _compute_remote_available(self):
        for record in self:
            record.remote_available = sum([x.remote_available for x in record.product_variant_ids])

    def _search_remote_available(self, operator, value):
        domain = [('remote_available', operator, value)]
        product_variant_ids = self.env['product.product'].search(domain)
        return [('product_variant_ids', 'in', product_variant_ids.ids)]

    @api.depends('product_variant_ids')
    def get_remote_qty(self):
        for record in self:
            for product_id in record.product_variant_ids:
                product_id.get_remote_qty()

    @api.model
    def action_get_remote_all(self, category='All'):
        category_id = self.env['product.category'].search([('complete_name', '=', category)])
        product_tmpl_ids = self.search([('categ_id', 'child_of', category_id.id)])
        for product_tmpl_id in product_tmpl_ids:
            product_tmpl_id.get_remote_qty()


class ProductProduct(models.Model):
    _inherit = "product.product"

    direct_standard_price = fields.Float('Cost', company_dependent=True, digits=dp.get_precision('Product Price'))
    remote_available = fields.Float('In Outside storages', digits=dp.get_precision('Product Unit of Measure'))
    last_update_qty = fields.Datetime('Last update External Qty')

    def get_remote_qty(self):
        res = False
        for record in self:
            if self.env.user.company_id.remote_user \
                and self.env.user.company_id.remote_password \
                    and self.env.user.company_id.remote_database:
                remote = self.env.user.company_id.remote_access()
                if remote:
                    location_id = self._context.get('location_id', False)
                    if not location_id:
                        try:
                            warehouse = remote.env['stock.warehouse'].search(
                                [('company_id', '=', remote.env.user.company_id.id)], limit=1)
                            if warehouse:
                                warehouse = remote.env['stock.warehouse'].browse(warehouse)
                                location_id = warehouse.lot_stock_id.id
                        except ValueError:
                            _logger.info("Error with import")

                    default_code = record.default_code
                    res_remote = remote.env['product.product'].search([
                        ('default_code', '=', default_code)])
                    if not res_remote:
                        res_remote = remote.env['product.template'].search([
                            ('default_code', '=', default_code)])
                        products = remote.env['product.product'].browse(res_remote)
                        res_remote_new = set([])
                        for product in products:
                            res_remote_new.update([product.id])
                        res_remote = list(res_remote_new)
                    # _logger.info("RES REMOTE %s" % res_remote)
                    if res_remote and location_id:
                        try:
                            for product_remote in remote.env['product.product'].browse(res_remote):
                                qty_available = product_remote.with_context(
                                    dict(self._context, location=location_id)).qty_available
                                record.remote_available = qty_available
                                record.last_update_qty = fields.Datetime.now()
                                res = True
                        except ValueError:
                            _logger.info("Error with import")
        return res

