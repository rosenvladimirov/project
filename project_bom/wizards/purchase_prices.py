# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from statistics import mean

from odoo import api, models, fields, _
from odoo.addons import decimal_precision as dp

import logging

_logger = logging.getLogger(__name__)


class PurchasePrice(models.TransientModel):
    _name = 'bom.get.purchase.price'
    _description = "Get purchase price wizard"

    product_tmpl_id = fields.Many2one('product.template', 'Product template')
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', required=True)
    standard_price = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
    price_line = fields.One2many('bom.get.purchase.price.line', 'purchase_price_id', string='Purchase price lines')
    supp_price_line = fields.One2many('bom.get.purchase.price.supp', 'purchase_price_id', string='Supplier price lines')
    line_ids = fields.Many2many('project.mrp.bom.line', string='Origin lines')

    use_price = fields.Boolean('Use this price')

    @api.onchange('use_price')
    @api.depends('price_line')
    def onchange_use_price(self):
        for record in self:
            if record.use_price:
                for line in record.price_line:
                    line.use_price = False

    @api.model
    def get_unit_price(self, x):
        purchase_id = self.env['purchase.order.line'].search([('product_id', '=', x.product_id.id),
                                                              ('state', 'in', ['purchase', 'done'])],
                                                             order='date_planned DESC', limit=1)

        if x.price_unit != 0.0:
            price_unit = x.price_unit
        elif x.price_unit == 0.0 and purchase_id:
            price_unit = purchase_id.price_unit
            order = purchase_id.order_id
            if purchase_id.taxes_id:
                price_unit = purchase_id.taxes_id.with_context(round=False).compute_all(
                    price_unit, currency=purchase_id.order_id.currency_id, quantity=1.0, product=purchase_id.product_id,
                    partner=purchase_id.order_id.partner_id
                )['total_excluded']
            if purchase_id.product_uom.id != purchase_id.product_id.uom_id.id:
                price_unit *= purchase_id.product_uom.factor / purchase_id.product_id.uom_id.factor
            if order.currency_id != order.company_id.currency_id:
                price_unit = order.currency_id.with_context(date=order.date_approve).\
                    compute(price_unit, order.company_id.currency_id, round=False)
        else:
            price_unit = x.product_id.standard_price
        _logger.info("PRICE UNIT 1 %s=>std=%s:mv=%s:p=%s" % (x.product_id.display_name, x.product_id.standard_price, x.price_unit, purchase_id and purchase_id.price_unit))
        return price_unit

    @api.model
    def default_get(self, fields_list):
        res = super(PurchasePrice, self).default_get(fields_list)
        if self._context.get('active_model') == 'project.mrp.bom.line' and self._context.get('active_ids'):
            price_line = []
            supp_price_line = []
            bom_line_ids = self.env['project.mrp.bom.line'].browse(self._context['active_id'])

            for bom_line_id in bom_line_ids:
                for product_id in bom_line_id.product_tmpl_id.product_variant_ids:
                    purchase_ids = self.env['purchase.order.line'].search([('product_id', '=', product_id.id),
                                                                          ('state', 'in', ['purchase', 'done'])],
                                                                         order='date_planned DESC')
                    if purchase_ids:
                        for purchase_id in purchase_ids:
                            price_unit = purchase_id.price_unit
                            price_line.append((0, False, {
                                'name': purchase_id.order_id.partner_id.id,
                                'product_id': product_id.id,
                                'product_tmpl_id': product_id.product_tmpl_id.id,
                                'purchase_line_id': purchase_id.id,
                                'product_uom': purchase_id.product_id.uom_id.id,
                                'price_unit': price_unit,
                                'currency_id': purchase_id.order_id.currency_id.id,
                                'date': purchase_id.date_order,
                            }))
                    for line in bom_line_id.product_tmpl_id.seller_ids:
                        supp_price_line.append((0, False, {
                            'name': line.name.id,
                            'product_id': line.product_id.id,
                            'product_tmpl_id': line.product_tmpl_id.id,
                            'product_uom': line.product_uom.id,
                            'price_unit': line.price,
                            'currency_id': line.currency_id.id,
                            'date_start': line.date_start,
                            'date_end': line.date_end,
                            'supp_info_id': line.id,
                        }))

            if bom_line_ids[0].product_tmpl_id.product_variant_count > 1:
                standard_price = mean([x.standard_price for x in bom_line_ids[0].product_tmpl_id.product_variant_ids])
            else:
                standard_price = bom_line_ids[0].product_tmpl_id.standard_price
            res.update({
                'product_tmpl_id': bom_line_ids[0].product_tmpl_id.id,
                'product_uom': bom_line_ids[0].product_uom_id.id,
                'line_ids': [(6, False, bom_line_ids.ids)],
                'standard_price': standard_price,
                'price_line': price_line,
                'supp_price_line': supp_price_line,
            })
        return res

    @api.multi
    def action_use_price(self):
        for record in self:
            purchase_price_id = record.price_line.filtered(lambda r: r.use_price)
            if purchase_price_id:
                price_unit = purchase_price_id.price_unit
                order = purchase_price_id.purchase_line_id.order_id
                purchase_id = purchase_price_id.purchase_line_id
                if purchase_id.taxes_id:
                    price_unit = purchase_id.taxes_id.with_context(round=False).compute_all(
                        price_unit, currency=purchase_id.order_id.currency_id, quantity=1.0,
                        product=purchase_id.product_id,
                        partner=purchase_id.order_id.partner_id
                    )['total_excluded']
                if purchase_id.product_uom.id != purchase_id.product_id.uom_id.id:
                    price_unit *= purchase_id.product_uom.factor / purchase_id.product_id.uom_id.factor
                if order.currency_id != order.company_id.currency_id:
                    price_unit = order.currency_id.with_context(date=order.date_approve). \
                        compute(price_unit, order.company_id.currency_id, round=False)
                record.line_ids.write({
                    'price_unit': price_unit,
                })
            supp_price_id = record.supp_price_line.filtered(lambda r: r.use_price)
            if supp_price_id:
                price_unit = supp_price_id.price_unit
                supp = supp_price_id.supp_info_id
                company_id = self.env.user.company_id
                product_id = supp.product_id
                if not product_id:
                    product_id = supp.product_tmpl_id
                if supp.product_uom.id != product_id.uom_id.id:
                    price_unit *= supp.product_uom.factor / product_id.uom_id.factor
                if supp.currency_id != company_id.currency_id:
                    price_unit = supp.currency_id.with_context(date=fields.Date.today()). \
                        compute(price_unit, company_id.currency_id, round=False)
                record.line_ids.write({
                    'price_unit': price_unit,
                })
            if not purchase_price_id and not supp_price_id:
                record.line_ids.write({
                    'price_unit': record.standard_price,
                })
        return


class PurchasePriceLine(models.TransientModel):
    _name = 'bom.get.purchase.price.line'
    _description = "Get purchase line price wizard"

    purchase_price_id = fields.Many2one('bom.get.purchase.price', string='Purchase price', index=True, required=True,
                                        ondelete='cascade')
    purchase_line_id = fields.Many2one('purchase.order.line', 'Purchase line')
    name = fields.Many2one('res.partner', 'Vendor', related='purchase_line_id.order_id.partner_id')
    product_id = fields.Many2one('product.product', 'Product', related='purchase_line_id.product_id')
    product_tmpl_id = fields.Many2one('product.template', 'Product template',
                                      related='purchase_line_id.product_id.product_tmpl_id')
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure',
                                  related='purchase_line_id.product_uom')
    price_unit = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
    currency_id = fields.Many2one('res.currency', 'Currency', required=True)
    date = fields.Datetime('Price date', related='purchase_line_id.order_id.date_order')
    use_price = fields.Boolean('Use this price')

    @api.onchange('use_price')
    @api.depends('purchase_price_id')
    def onchange_use_price(self):
        for record in self:
            if record.use_price:
                record.purchase_price_id.use_price = False


class PurchasePriceSupplierInfo(models.TransientModel):
    _name = 'bom.get.purchase.price.supp'
    _description = "Get supplier line price wizard"

    purchase_price_id = fields.Many2one('bom.get.purchase.price', string='Purchase price', index=True, required=True,
                                        ondelete='cascade')
    supp_info_id = fields.Many2one('product.supplierinfo', 'Supplier price list')
    product_id = fields.Many2one('product.product', 'Product', related='supp_info_id.product_id')
    product_tmpl_id = fields.Many2one('product.template', 'Product template',
                                      related='supp_info_id.product_id.product_tmpl_id')
    name = fields.Many2one('res.partner', 'Vendor', related='supp_info_id.name')
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', related='supp_info_id.product_uom')
    price_unit = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
    currency_id = fields.Many2one('res.currency', 'Currency', required=True)
    date_start = fields.Date('Start Date', related='supp_info_id.date_start', help="Start date for this vendor price")
    date_end = fields.Date('End Date', related='supp_info_id.date_end', help="End date for this vendor price")
    use_price = fields.Boolean('Use this price')

    @api.onchange('use_price')
    @api.depends('purchase_price_id')
    def onchange_use_price(self):
        for record in self:
            if record.use_price:
                record.purchase_price_id.use_price = False
