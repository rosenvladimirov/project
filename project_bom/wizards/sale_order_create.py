# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from statistics import mean

from odoo import api, models, fields, _
from odoo.addons import decimal_precision as dp

import logging

_logger = logging.getLogger(__name__)


class BomSaleOrder(models.TransientModel):
    _name = 'bom.sale.order'
    _description = "Sale order create wizard"

    project_bom_id = fields.Many2many('project.mrp.bom', string='Project BOM')
    sale_order_id = fields.Many2one('sale.order', string='Sale order')
    date = fields.Datetime('Sale order date', related='sale_order_id.date_order')
    partner_id = fields.Many2one('res.partner', 'Partner', related='sale_order_id.partner_id')
    partner_shipping_id = fields.Many2one('res.partner', string='Delivery Address',
                                          related='sale_order_id.partner_shipping_id')
    currency_id = fields.Many2one('res.currency', 'Currency', related='sale_order_id.currency_id')
    save_coefficient = fields.Float('Save price coefficient', default=1.0)
    product_uom_qty = fields.Float(string='Quantity',
                                   digits=dp.get_precision('Product Unit of Measure'), required=True, default=1.0)
    product_set_auto = fields.Boolean('Auto create Product Set')
    product_set_id = fields.Many2one('product.set', 'Product set')
    project_sale_lines = fields.One2many('bom.sale.order.line', inverse_name='bom_sale_order_id',
                                         string='BOM Sale order lines')

    @api.model
    def default_get(self, fields_list):
        res = super(BomSaleOrder, self).default_get(fields_list)
        if self._context.get('active_model') == 'project.mrp.bom' or res.get('project_bom_id'):
            project_sale_lines = []
            if not res.get('project_bom_id'):
                project_bom_ids = self.env['project.mrp.bom'].browse(self._context['active_ids'])
            else:
                project_bom_ids = self.env['project.mrp.bom'].browse(res['project_bom_id'][0][2])
            if project_bom_ids:
                res['project_bom_id'] = [(6, False, project_bom_ids.ids)]
                for project in project_bom_ids:
                    for line in project.project_bom_line_ids:
                        project_sale_lines.append((0, False, {
                            'project_bom_line_id': line.id,
                            'mrp_product_tmpl_id': project.product_tmpl_id.id,
                            'product_tmpl_id': line.product_tmpl_id.id,
                            'oring_product_uom_qty': line.product_qty,
                            'product_uom': line.product_uom_id.id,
                            'oring_price_unit': line.price_unit,
                            'tax_id': [(6, False, [])],
                        }))
            if project_sale_lines:
                res['project_sale_lines'] = project_sale_lines
        # _logger.info("RES %s" % res)
        return res

    @api.onchange('sale_order_id', 'save_coefficient', 'product_uom_qty')
    @api.depends('project_sale_lines.price_unit', 'project_sale_lines.price_subtotal', 'project_sale_lines.price_total')
    def onchange_sale_order_id(self):
        if self.sale_order_id:
            company_id = self.env.user.company_id
            for line in self.project_sale_lines:
                line.product_uom_qty = line.oring_product_uom_qty * self.product_uom_qty
                price_unit = line.oring_price_unit
                if self.sale_order_id.currency_id != company_id.currency_id:
                    price_unit = company_id.currency_id.with_context(date=fields.Date.today()). \
                        compute(price_unit, self.sale_order_id.currency_id, round=False)
                line.price_unit = price_unit * self.save_coefficient

    @api.multi
    def action_create_sale_lines(self):
        sale_order_line = []
        sale_order_ids = self.env['sale.order']

        for record in self:
            addr = record.partner_id.address_get(['delivery', 'invoice'])
            product_set_id = record.product_set_id
            for project in record.project_bom_id:
                if record.product_set_auto:
                    product_set_id = self.env['product.set'].create({
                        'name': project.product_tmpl_id.display_name,
                        'code': project.product_tmpl_id.default_code or self.env['ir.sequence'].next_by_code('product.set'),
                        'sale_ok': True,
                        'fiscal_position_id': self.env['account.fiscal.position'].get_fiscal_position(
                            record.partner_id.id, addr['delivery']),
                        'pricelist_id': record.partner_id.property_product_pricelist
                                        and record.partner_id.property_product_pricelist.id or False,
                        'partner_invoice_id': addr['invoice'],
                        'partner_shipping_id': addr['delivery'],
                        'currency_id': record.partner_id.property_product_pricelist
                                       and record.partner_id.property_product_pricelist.currency_id.id or False,

                    })
                sale_order_ids |= record.sale_order_id
                for line in record.project_sale_lines. \
                        filtered(lambda r: r.project_bom_line_id.project_bom_id == project):
                    if line.product_uom_qty == 0.0 or not line.product_id:
                        continue
                    sale_order_line.append((0, False, {
                        'product_id': line.product_id.id,
                        'discount': line.discount,
                        'price_unit': line.price_unit,
                        'product_uom_id': line.product_uom,
                        'product_uom_qty': line.product_uom_qty,
                        'product_set_id': product_set_id.id,
                        'currency_id': record.currency_id.id,
                    }))
                    if record.product_set_auto:
                        product_set_id.set_lines = [(0, False, {
                            'product_tmpl_id': line.product_tmpl_id.id,
                            'product_id': line.product_id.id,
                            'quantity': line.product_uom_qty,
                            'tax_id': [(6, False, line.tax_id.ids)],
                        })]
                if sale_order_line:
                    record.sale_order_id.order_line = sale_order_line
        action = self.env.ref('sale.action_orders').read()[0]
        if len(sale_order_ids.ids) > 1:
            action['res_ids'] = sale_order_ids.ids
            action['domain'] = [('id', 'in', sale_order_ids.ids)]
        elif len(sale_order_ids.ids) == 1:
            action['view_id'] = self.env.ref('sale.view_order_form').id
            action['view_mode'] = 'tree,form'
            action['res_id'] = sale_order_ids[0].id
        return action


class BomSaleOrderLine(models.TransientModel):
    _name = 'bom.sale.order.line'

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            if not line.product_id:
                continue
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_id. \
                compute_all(price, line.bom_sale_order_id.currency_id, line.product_uom_qty,
                            product=line.product_id, partner=line.bom_sale_order_id.partner_shipping_id)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    bom_sale_order_id = fields.Many2one('bom.sale.order', string='BOM Sale order', index=True, required=True,
                                        ondelete='cascade')
    project_bom_line_id = fields.Many2one('project.mrp.bom.line', 'Project BOM line')
    mrp_product_tmpl_id = fields.Many2one('product.template',
                                          related='project_bom_line_id.project_bom_id.product_tmpl_id')
    product_tmpl_id = fields.Many2one('product.template', 'Product Template',
                                      related='project_bom_line_id.product_tmpl_id')
    product_id = fields.Many2one('product.product', 'Product')
    discount = fields.Float(string='Discount (%)', digits=dp.get_precision('Discount'), default=0.0)
    oring_product_uom_qty = fields.Float(string='Oring Quantity', digits=dp.get_precision('Product Unit of Measure'))
    product_uom_qty = fields.Float(string='Quantity',
                                   digits=dp.get_precision('Product Unit of Measure'), required=True, default=1.0)
    product_uom = fields.Many2one('product.uom', string='Unit of Measure', required=True)
    oring_price_unit = fields.Float(string='Oring Unit Price', digits=dp.get_precision('Currency Product Price'))
    price_unit = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
    price_tax = fields.Float(compute='_compute_amount', string='Taxes', readonly=True, store=True)
    currency_id = fields.Many2one('res.currency', related='bom_sale_order_id.currency_id', string='Currency')
    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal')
    price_total = fields.Monetary(compute='_compute_amount', string='Total', readonly=True, store=True)
    tax_id = fields.Many2many('account.tax', string='Taxes',
                              domain=['|', ('active', '=', False), ('active', '=', True)])

    @api.multi
    def _compute_tax_id(self):
        for line in self:
            fpos = line.bom_sale_order_id.sale_order_id.fiscal_position_id \
                   or line.bom_sale_order_id.sale_order_id.partner_id.property_account_position_id
            # If company_id is set, always filter taxes by the company
            taxes = line.product_id.taxes_id. \
                filtered(lambda r: not line.bom_sale_order_id.sale_order_id.company_id
                                   or r.company_id == line.bom_sale_order_id.sale_order_id.company_id)
            line.tax_id = fpos. \
                map_tax(taxes, line.product_id,
                        line.bom_sale_order_id.sale_order_id.partner_shipping_id) if fpos else taxes

    @api.multi
    @api.onchange('product_id')
    def product_id_change(self):
        if not self.product_id:
            return {'domain': {'product_uom': []}}

        vals = {}
        domain = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
        if not self.product_uom or (self.product_id.uom_id.id != self.product_uom.id):
            vals['product_uom'] = self.product_id.uom_id
            vals['product_uom_qty'] = 1.0

        result = {'domain': domain}

        self._compute_tax_id()

        if self.bom_sale_order_id.sale_order_id.pricelist_id and self.bom_sale_order_id.sale_order_id.partner_id:
            price_unit = self.oring_price_unit
            company_id = self.env.user.company_id
            if self.bom_sale_order_id.sale_order_id.currency_id != company_id.currency_id:
                price_unit = company_id.currency_id.with_context(date=fields.Date.today()). \
                    compute(price_unit, self.bom_sale_order_id.sale_order_id.currency_id, round=False)
            vals['price_unit'] = self.env['account.tax']._fix_tax_included_price_company(
                price_unit,
                self.product_id.taxes_id,
                self.tax_id,
                self.bom_sale_order_id.sale_order_id.company_id) * self.bom_sale_order_id.save_coefficient
            vals['product_uom_qty'] = self.oring_product_uom_qty * self.bom_sale_order_id.product_uom_qty
        self.update(vals)
        return result
