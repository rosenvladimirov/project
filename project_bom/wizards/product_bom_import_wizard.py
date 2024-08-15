# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _, SUPERUSER_ID

import logging
_logger = logging.getLogger(__name__)


class RemoteMultiCompanyProductImport(models.TransientModel):
    _name = 'product.bom.import'
    _description = 'Import Product Bom'

    product_id = fields.Many2one('product.product', 'Product')
    product_tmpl_id = fields.Many2one('product.template', 'Product Template')
    default_code = fields.Char('Internal Reference')
    project_bom_id = fields.Many2one('project.mrp.bom', 'Project bom')

    def default_get(self, fields_list):
        res = super(RemoteMultiCompanyProductImport, self).default_get(fields_list)
        project_bom = self.env['project.mrp.bom'].browse(self._context.get('active_id'))
        if 'project_bom_id' not in res:
            res['project_bom_id'] = project_bom.id
        res.update({
            'product_id': project_bom.product_id.id,
            'product_tmpl_id': project_bom.product_id.product_tmpl_id.id,
            'default_code': project_bom.product_id.default_code,
        })
        return res


    def import_product_bom(self):
        for record in self:
            product_id = record.product_id
            product_tmpl_id = record.product_tmpl_id
            default_code = record.default_code

            if not default_code:
                default_code = product_id.default_code
            if not default_code:
                default_code = product_tmpl_id.default_code

            res = self.env['product.product'].search([('default_code', '=', default_code)]).ids
            if not res:
                res = self.env['product.template'].search([('default_code', '=', default_code)])
                products = self.env['product.product'].browse(res.mapped('product_variant_ids'))
                res_new = set([])
                for product in products:
                    res_new.update([product.id])
                res = list(res_new)


            for product_res in self.env['product.product'].browse(res):
                product_bom = self.env['mrp.bom']._bom_find(product_res)
                _logger.info('LOCAL BOM %s' % product_bom)
                if product_bom:
                    record.project_bom_id.project_bom_line_ids.filtered(lambda r: r.editable).unlink()
                    for product_bom, components in product_bom.items():
                        for component_default_code, product_component in components.items():
                            current_product = self.env['product.product']. \
                                search([('default_code', '=', component_default_code)])
                            if len(current_product.ids) > 1:
                                current_product = current_product[0]
                            if current_product:
                                product_tmpl_id = current_product.product_tmpl_id
                                product_type_id = product_tmpl_id.categ_id.get_product_type_id()
                                if product_tmpl_id.product_type_id:
                                    product_type_id = product_tmpl_id.product_type_id
                                project_bom_line_id = record.project_bom_id.project_bom_line_ids.filtered(
                                    lambda r: r.product_tmpl_id == product_tmpl_id)
                                if project_bom_line_id:
                                    project_bom_line_id.product_qty += product_component['product_qty']
                                else:
                                    project_bom_line_id = self.env['project.mrp.bom.line'].create({
                                        'project_bom_id': record.project_bom_id.id,
                                        'product_tmpl_id': product_tmpl_id.id,
                                        'product_type_id': product_type_id and product_type_id.id or product_type_id.id,
                                        'product_qty': product_component['product_qty'],
                                        'price_unit': product_tmpl_id.standard_price,
                                        'editable': True,
                                    })
                                project_bom_line_id.operation_ids.create({
                                    'project_bom_line_id': project_bom_line_id.id,
                                    'project_bom_id': record.project_bom_id.id,
                                    'product_tmpl_id': product_tmpl_id.id,
                                    'product_id': current_product.id,
                                    'product_qty': product_component['product_qty'],
                                    'name': product_component['operation'],
                                })
                                record.project_bom_id.project_bom_line_ids |= project_bom_line_id
