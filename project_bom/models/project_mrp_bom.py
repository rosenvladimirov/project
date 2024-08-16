# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
# from statistics import mean
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ProjectMrpBom(models.Model):
    _name = 'project.mrp.bom'
    _description = 'Develop BOM for production'
    _order = 'sequence, id'

    def _get_default_product_uom_id(self):
        return self.env['uom.uom'].search([], limit=1, order='id').id

    @api.depends('project_bom_group_ids.price_subtotal')
    def _amount_all(self):
        for project_bom in self.filtered(lambda r: r.currency_id):
            direct_amount_untaxed = amount_untaxed = 0.0
            for line in project_bom.project_bom_group_ids:
                amount_untaxed += line.price_subtotal
                direct_amount_untaxed += line.direct_price_subtotal
            project_bom.update({
                'amount_untaxed': project_bom.currency_id.round(amount_untaxed),
                'standard_amount_untaxed': project_bom.currency_id.
                round(project_bom.forecast_product_qty * project_bom.standard_price),
                'direct_amount_untaxed': project_bom.currency_id.round(direct_amount_untaxed),
            })
            project_bom.onchange_direct_amount_untaxed()

    sequence = fields.Integer(default=1)
    active = fields.Boolean('Active', default=True,
                            help="If the active field is set to False, it will allow you to hide the bills of "
                                 "material without removing it.")
    work_added = fields.Boolean('Work type', help='Please checked it if work with every time in added mode')
    code = fields.Char('Code')
    version = fields.Char('Version', default='1.0', required=True)
    display_name = fields.Char('Display name', compute='_compute_display_name')
    product_id = fields.Many2one('product.product', 'Product')
    product_tmpl_id = fields.Many2one('product.template', 'Product Template', required=True)
    product_qty = fields.Float('Quantity', default=1.0, required=True)
    bulk_product_qty = fields.Float('Bulk produce', default=1.0,
                                    required=True)
    forecast_product_qty = fields.Float('Forcast Quantity', default=1.0)
    product_uom_id = fields.Many2one('uom.uom', 'Product Unit of Measure',
                                     default=_get_default_product_uom_id, oldname='product_uom', required=True,
                                     help="Unit of Measure (Unit of Measure) is the unit of measurement for the "
                                          "inventory control")
    company_id = fields.Many2one('res.company', 'Company',
                                 default=lambda self: self.env['res.company']._company_default_get('mrp.bom'),
                                 required=True)
    project_bom_line_ids = fields.One2many('project.mrp.bom.line',
                                           'project_bom_id',
                                           'BoM Lines',
                                           copy=True)
    project_bom_group_ids = fields.One2many('project.mrp.bom.group',
                                            'project_bom_id',
                                            'BoM Groups',
                                            copy=False)
    task_id = fields.Many2one('project.task', 'Project Task')
    account_analytic_id = fields.Many2one('account.analytic.account', 'Analytic account')
    price_unit_type = fields.Selection([
        ('avg', _('Average price')),
        ('top', _('Highest purchase price')),
        ('low', _('Lowest purchase price')),
        ('last', _('Last purchase price')),
        ('first', _('First purchase price')),
    ], string='Unit price type')
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all')
    direct_amount_untaxed = fields.Monetary(string='Direct Standard price', store=True, readonly=True,
                                            compute='_amount_all')
    standard_amount_untaxed = fields.Monetary(string='Standard Untaxed Amount', store=True, readonly=True,
                                              compute='_amount_all')
    standard_price = fields.Float('Cost', related='product_id.standard_price')
    direct_standard_price = fields.Float('Direct cost', related='product_id.direct_standard_price')
    currency_id = fields.Many2one('res.currency', 'Currency', related='company_id.currency_id')
    sale_order_ids = fields.Many2many('sale.order', string='Sale orders')
    partner_id = fields.Many2one('res.partner', 'Partner')
    last_update_qty = fields.Datetime('Last update External Qty')
    note = fields.Text('Note', translate=True)

    def _compute_display_name(self):
        for record in self:
            if record.code:
                record.display_name = "(%s) %s" % (record.code, record.product_tmpl_id.display_name)
            else:
                record.display_name = "%s" % record.product_tmpl_id.display_name

    def toggle_work_added(self):
        for record in self:
            record.work_added = not record.work_added

    def store_standard_price(self):
        for record in self:
            record.product_tmpl_id.standard_price = record.amount_untaxed

    @api.onchange('sale_order_ids')
    def onchange_sale_order_ids(self):
        forecast_product_qty = 0.0
        for line in self.sale_order_ids.mapped('order_line').filtered(lambda r: r.product_id == self.product_id):
            forecast_product_qty += line.product_uom_qty
        self.forecast_product_qty = forecast_product_qty != 0.0 and forecast_product_qty or self.forecast_product_qty

    @api.onchange('direct_amount_untaxed')
    def onchange_direct_amount_untaxed(self):
        self.direct_standard_price = self.direct_amount_untaxed

    @api.onchange('product_uom_id')
    def onchange_product_uom_id(self):
        res = {}
        if not self.product_uom_id or not self.product_tmpl_id:
            return
        if self.product_uom_id.category_id.id != self.product_tmpl_id.uom_id.category_id.id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id
            res['warning'] = {'title': _('Warning'), 'message': _('The Product Unit of Measure you chose has a '
                                                                  'different category than in the product form.')}
        return res

    @api.onchange('product_tmpl_id')
    def onchange_product_tmpl_id(self):
        if self.product_tmpl_id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id
            if self.product_id.product_tmpl_id != self.product_tmpl_id:
                self.product_id = False

    @api.onchange('price_unit_type')
    def _onchange_price_unit_type(self):
        for record in self:
            if record.price_unit_type == 'avg':
                subtotal = 0.0
                for line in record.project_bom_line_ids:
                    line._compute_stock_value()
                    line.price_unit = line.avg_price_unit
                    subtotal += line.price_subtotal
                record.direct_standard_price = subtotal / record.forecast_product_qty
            elif record.price_unit_type == 'last':
                subtotal = 0.0
                for line in record.project_bom_line_ids:
                    for bom_line_id in line:
                        for product_id in bom_line_id.product_tmpl_id.product_variant_ids:
                            purchase_ids = self.env['purchase.order.line'].search([('product_id', '=', product_id.id),
                                                                                   ('state', 'in',
                                                                                    ['purchase', 'done'])],
                                                                                  order='date_planned DESC', limit=1)
                            if purchase_ids:
                                for purchase_id in purchase_ids:
                                    line.price_unit = purchase_id.price_unit
                                    subtotal += line.price_subtotal
                                record.direct_standard_price = subtotal / record.forecast_product_qty
            elif record.price_unit_type == 'first':
                subtotal = 0.0
                for line in record.project_bom_line_ids:
                    for bom_line_id in line:
                        for product_id in bom_line_id.product_tmpl_id.product_variant_ids:
                            purchase_ids = self.env['purchase.order.line'].search([('product_id', '=', product_id.id),
                                                                                   ('state', 'in',
                                                                                    ['purchase', 'done'])],
                                                                                  order='date_planned', limit=1)
                            if purchase_ids:
                                for purchase_id in purchase_ids:
                                    line.price_unit = purchase_id.price_unit
                                    subtotal += line.price_subtotal
                                record.direct_standard_price = subtotal / record.forecast_product_qty
            elif record.price_unit_type == 'top':
                subtotal = 0.0
                for line in record.project_bom_line_ids:
                    for bom_line_id in line:
                        for product_id in bom_line_id.product_tmpl_id.product_variant_ids:
                            purchase_ids = self.env['purchase.order.line'].search([('product_id', '=', product_id.id),
                                                                                   ('state', 'in',
                                                                                    ['purchase', 'done'])],
                                                                                  order='price_unit DESC', limit=1)
                            if purchase_ids:
                                for purchase_id in purchase_ids:
                                    line.price_unit = purchase_id.price_unit
                                    subtotal += line.price_subtotal
                                record.direct_standard_price = subtotal / record.forecast_product_qty
            elif record.price_unit_type == 'low':
                subtotal = 0.0
                for line in record.project_bom_line_ids:
                    for bom_line_id in line:
                        for product_id in bom_line_id.product_tmpl_id.product_variant_ids:
                            purchase_ids = self.env['purchase.order.line'].search([('product_id', '=', product_id.id),
                                                                                   ('state', 'in',
                                                                                    ['purchase', 'done'])],
                                                                                  order='price_unit', limit=1)
                            if purchase_ids:
                                for purchase_id in purchase_ids:
                                    line.price_unit = purchase_id.price_unit
                                    subtotal += line.price_subtotal
                                record.direct_standard_price = subtotal / record.forecast_product_qty

    def action_sort(self):
        for record in self:
            for line in record.project_bom_line_ids:
                line.sequence = int(line.product_type_id.code or '0')

    def action_version_control(self):
        for record in self:
            for line in record.bom_ids:
                line.sequence = int(line.version.split('.')[0]) * 1000 + int(line.version.split('.')[1]) * 10

    # @api.multi
    # def action_create_bom(self):
    #     for record in self:
    #         sub_version = len(record.bom_ids.ids) + 1
    #         sub_version = "%s" % sub_version
    #         bom_id = self.env['mrp.bom'].create({
    #             'project_bom_id': record.id,
    #             'product_id': record.product_id and record.product_id.id or False,
    #             'product_tmpl_id': record.product_tmpl_id.id,
    #             'code': "%s%s" % (sub_version, record.code and " (%s)" % record.code or ''),
    #             'version': "%s.%s" % (record.version[:2], sub_version.zfill(2)),
    #             'product_uom_id': record.product_uom_id.id,
    #             'product_qty': record.product_qty,
    #             'company_id': record.company_id.id,
    #             'copy_from_bom_id': record.bom_id and record.bom_id.id or False,
    #             'routing_id': record.routing_id and record.routing_id.id or False,
    #             # 'bom_line_ids': bom_line,
    #         })
    #         record.bom_ids |= bom_id
    #         record.bom_id = bom_id
    #         if len(record.bom_ids) > 0:
    #             record.version = bom_id.version
    #         # record.bom_id.version = record.version
    #         record.bom_id.sequence = int(record.version.split('.')[0]) * 1000 + int(record.version.split('.')[1]) * 10
    #         record.sequence = int(record.version.split('.')[0]) * 1000 + int(record.version.split('.')[1]) * 10
    #
    # @api.multi
    # def action_next_bom(self):
    #     for record in self:
    #         current_bom = record.bom_id.sequence
    #         for bom in record.bom_ids.sorted(lambda r: r.sequence):
    #             if bom.sequence > current_bom:
    #                 record.bom_id = bom
    #                 break
    #
    # @api.multi
    # def action_prevision_bom(self):
    #     for record in self:
    #         current_bom = record.bom_id.sequence
    #         for bom in record.bom_ids.sorted(lambda r: r.sequence, reverse=True):
    #             if bom.sequence < current_bom:
    #                 record.bom_id = bom
    #                 break
    #
    # @api.multi
    # def action_set_current_bom(self):
    #     for record in self:
    #         record.action_version_control()
    #         record.bom_id.sequence = 9999

    def operation_bom_line(self):
        for record in self:
            operation_ids = self.env['project.mrp.bom.operation']
            for line in record.project_bom_line_ids:
                operation_ids |= line.operation_ids
            action = self.env.ref('project_bom.project_mrp_bom_operation_form_action')
            action = action.read()[0]
            action.update({
                'context': {
                    'default_project_bom_id': record.id,
                    'use_project_bom': True,
                },
                'domain': [('id', 'in', operation_ids.ids)],
            })
            return action

    def material_bom_line(self):
        for record in self:
            line_ids = self.env['project.mrp.bom.line']
            for line in record.project_bom_line_ids:
                line_ids |= line
            action = self.env.ref('project_bom.project_mrp_bom_line_form_action')
            action = action.read()[0]
            action.update({
                'context': {
                    'default_project_bom_id': record.id,
                },
                'domain': [('id', 'in', line_ids.ids)],
            })
            return action

    def unlink(self):
        for record in self:
            for operation in record.mapped('project_bom_line_ids').mapped('operation_ids'):
                operation.unlink()
        return super(ProjectMrpBom, self).unlink()
