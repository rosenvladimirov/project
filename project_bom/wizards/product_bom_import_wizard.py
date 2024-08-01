# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _, SUPERUSER_ID

import logging
_logger = logging.getLogger(__name__)


class RemoteMultiCompanyProductImport(models.TransientModel):
    _name = 'product.bom.import'
    _description = 'Import Product Bom'

    product_id = fields.Many2one('product.product', 'Product')
    default_code = fields.Char('Internal Reference')
    use_remote = fields.Boolean('From remote', default=True)
    project_bom_id = fields.Many2one('project.mrp.bom', 'Project bom')

    @api.model
    def default_get(self, fields_list):
        res = super(RemoteMultiCompanyProductImport, self).default_get(fields_list)
        project_bom = self.env['project.mrp.bom'].browse(self._context.get('active_id'))
        if 'project_bom_id' not in res:
            res['project_bom_id'] = project_bom.id
        res.update({
            'product_id': project_bom.product_id.id,
            'default_code': project_bom.product_id.default_code,
        })
        return res

    @api.multi
    def import_product_bom(self):
        # if self._context.get('active_model') == 'product.product' and len(self._context.get('active_ids', [])) > 1:
        #     product_tmpl_ids = self.env['product.product'].browse(self._context['active_ids'])
        for record in self:
            if record.use_remote:
                if self.env.user.company_id.remote_user \
                        and self.env.user.company_id.remote_password \
                        and self.env.user.company_id.remote_database:
                    remote = self.env.user.company_id.remote_access()
                    if remote:
                        product_id = record.product_id
                        default_code = record.default_code
                        if not default_code:
                            default_code = product_id.default_code
                        if not default_code:
                            default_code = product_id.product_tmpl_id.default_code

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
                        if res_remote:
                            project_bom_id = record.project_bom_id
                            bulk_product_qty = project_bom_id.bulk_product_qty != 0.0 and project_bom_id.bulk_product_qty or 1.0
                            try:
                                for product_remote in remote.env['product.product'].browse(res_remote):
                                    product_bom = product_remote.get_explored_bom(bulk_product_qty)
                                    _logger.info('REMOTE BOM %s' % product_bom)
                                    if product_bom:
                                        project_bom_id.project_bom_line_ids.filtered(lambda r: r.editable).unlink()
                                        for product_bom, components in product_bom.items():
                                            for component_default_code, product_component in components.items():
                                                current_product = self.env['product.product'].\
                                                    search([('default_code', '=', component_default_code)])
                                                if len(current_product.ids) > 1:
                                                    current_product = current_product[0]
                                                if current_product:
                                                    product_tmpl_id = current_product.product_tmpl_id
                                                    product_type_id = product_tmpl_id.categ_id.get_product_type_id()
                                                    if product_tmpl_id.product_type_id:
                                                        product_type_id = product_tmpl_id.product_type_id
                                                    project_bom_line_id = project_bom_id.project_bom_line_ids.filtered(lambda r: r.product_tmpl_id == product_tmpl_id)
                                                    if project_bom_line_id:
                                                        project_bom_line_id.product_qty += product_component['product_qty'] / bulk_product_qty or 1.0
                                                    else:
                                                        project_bom_line_id = self.env['project.mrp.bom.line'].create({
                                                            'project_bom_id': project_bom_id.id,
                                                            'product_tmpl_id': product_tmpl_id.id,
                                                            'product_type_id': product_type_id and product_type_id.id or product_type_id.id,
                                                            'product_qty': product_component['product_qty'] / bulk_product_qty or 1.0,
                                                            'price_unit': product_tmpl_id.standard_price,
                                                            'editable': True,
                                                        })
                                                    project_bom_line_id.operation_ids.create({
                                                        'project_bom_line_id': project_bom_line_id.id,
                                                        'project_bom_id': project_bom_id.id,
                                                        'product_tmpl_id': product_tmpl_id.id,
                                                        'product_id': current_product.id,
                                                        'product_qty': product_component['product_qty'] * bulk_product_qty,
                                                        'name': product_component['operation'],
                                                    })
                                                    project_bom_id.project_bom_line_ids |= project_bom_line_id
                                        project_bom_id.price_unit_type = 'avg'
                            except ValueError:
                                _logger.info("Error with import")

            else:
                product_id = record.product_id
                default_code = record.default_code
                if not default_code:
                    default_code = product_id.default_code
                if not default_code:
                    default_code = product_id.product_tmpl_id.default_code
                res = self.env['product.product'].search([('default_code', '=', default_code)]).ids
                if not res:
                    res = self.env['product.template'].search([('default_code', '=', default_code)])
                    products = self.env['product.product'].browse(res.mapped('product_variant_ids'))
                    res_new = set([])
                    for product in products:
                        res_new.update([product.id])
                    res = list(res_new)


                for product_res in self.env['product.product'].browse(res):
                    product_bom = product_res.get_explored_bom()
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
