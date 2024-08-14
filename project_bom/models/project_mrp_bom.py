# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
# from statistics import mean
import logging

from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.exceptions import UserError, AccessError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectMrpProductTypes(models.Model):
    _name = 'project.product.types'
    _description = 'Type of products'
    _order = 'sequence, id'

    sequence = fields.Integer(default=1)
    name = fields.Char('Name', translate=True)
    code = fields.Char('Code')


class ProjectMrpBom(models.Model):
    _name = 'project.mrp.bom'
    _description = 'Develop BOM for production'
    _order = 'sequence, id'

    def _get_default_product_uom_id(self):
        return self.env['uom.uom'].search([], limit=1, order='id').id

    @api.depends('project_bom_line_ids.price_subtotal')
    def _amount_all(self):
        for project_bom in self.filtered(lambda r: r.currency_id):
            direct_amount_untaxed = amount_untaxed = 0.0
            for line in project_bom.project_bom_line_ids:
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
    version = fields.Char('Version', default='1.0')
    display_name = fields.Char('Display name', compute='_compute_display_name')
    product_id = fields.Many2one('product.product', 'Product')
    product_tmpl_id = fields.Many2one('product.template', 'Product Template', required=True)
    # routing_id = fields.Many2one('mrp.routing', 'Routing',
    #                              help="The operations for producing this BoM.  When a routing is specified, "
    #                                   "the production orders will be executed through work orders, otherwise everything"
    #                                   " is processed in the production order itself. ")
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
    project_bom_line_ids = fields.One2many('project.mrp.bom.line', 'project_bom_id', 'BoM Lines', copy=True)
    # bom_ids = fields.One2many('mrp.bom', 'project_bom_id', 'BOM')
    # bom_id = fields.Many2one('mrp.bom', 'Current BOM')
    # copy_from_bom_id = fields.Many2one('mrp.bom', 'Copy from BOM', related='bom_id.copy_from_bom_id')
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


class ProjectMrpBomLine(models.Model):
    _name = 'project.mrp.bom.line'
    _description = 'Project bom lines'
    _order = "sequence, id"
    _rec_name = "product_tmpl_id"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _get_default_product_uom_id(self):
        return self.env['uom.uom'].search([], limit=1, order='id').id

    @api.depends('product_qty', 'price_unit', 'project_bom_id.forecast_product_qty')
    def _compute_amount(self):
        for line in self:
            line.update({
                'price_subtotal': 0.0,
                'direct_price_subtotal': 0.0,
                'purchase_price_subtotal': 0.0,
            })

            # purchase_price_unit = []
            # purchase_price_subtotal = 0.0
            # for product_id in line.product_tmpl_id.product_variant_ids:
            #     purchase_ids = self.env['purchase.order.line'].search([
            #         ('product_id', '=', product_id.id),
            #         ('state', 'in', ['purchase', 'done'],),
            #         '|',
            #         ('account_analytic_id', '=', False),
            #         ('account_analytic_id', '=', line.project_bom_id.account_analytic_id.id)
            #     ])
            #     for purchase_id in purchase_ids:
            #         if purchase_id.qty_received != 0.0:
            #             price_subtotal = purchase_id._get_stock_move_price_unit() * purchase_id.qty_received
            #             purchase_price_unit.append(price_subtotal)
            #     purchase_price_subtotal = len(purchase_price_unit) > 0 and sum(purchase_price_unit) or 0.0
            # line.update({
            #     'price_subtotal': line.product_qty * line.project_bom_id.forecast_product_qty * line.price_unit,
            #     'direct_price_subtotal': line.product_qty * line.price_unit,
            #     'purchase_price_subtotal': purchase_price_subtotal,
            # })

    @api.depends('product_qty', 'project_bom_id.forecast_product_qty')
    def _compute_forecast(self):
        for line in self:
            line.update({
                'forecast_product_qty': line.product_qty * line.project_bom_id.forecast_product_qty
            })

    product_type_id = fields.Many2one('project.product.types', 'Product type', required=True)
    product_tmpl_id = fields.Many2one('product.template', 'Product Template', required=True)
    product_qty = fields.Float('Product Quantity', default=1.0)
    forecast_product_qty = fields.Float('Forecast Product Quantity', compute='_compute_forecast')
    product_uom_id = fields.Many2one('uom.uom', 'Product Unit of Measure',
                                     default=_get_default_product_uom_id,
                                     required=True,
                                     help="Unit of Measure (Unit of Measure) is the unit of measurement for the "
                                          "inventory control")
    price_unit = fields.Float('Unit Price',
                              help="Technical field used to record the product cost set by the user during a picking "
                                   "confirmation (when costing method used is 'average price' or 'real'). Value given "
                                   "in company currency and in product uom.", copy=False)
    avg_price_unit = fields.Float('Average Price', compute='_compute_stock_value',
                                  copy=False,
                                  store=True,
                                  help="Technical field used to record the product"
                                       "cost(average) set by the user during a picking "
                                       "confirmation (when costing method used is "
                                       "'average price' or 'real'). Value given "
                                       "in company currency and in product uom.",
                                  )

    sequence = fields.Integer('Sequence', default=1,
                              help="Gives the sequence order when displaying.")
    project_bom_id = fields.Many2one('project.mrp.bom', 'Parent Project BOM',
                                     index=True, ondelete='cascade', required=True)
    attribute_value_ids = fields.Many2many('product.attribute.value', string='Variants',
                                           help="BOM Product Variants needed form apply this line.")
    # operation_id = fields.Many2one('mrp.routing.workcenter', 'Consumed in Operation',
    #                                help="The operation where the components are consumed, or the finished products "
    #                                     "created.")
    partner_id = fields.Many2one('res.partner', string='Vendor')
    purchase_price_subtotal = fields.Monetary(compute='_compute_amount', string='Purchase Subtotal', store=True)
    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', store=True)
    direct_price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', store=True)
    currency_id = fields.Many2one('res.currency', 'Currency', related='project_bom_id.company_id.currency_id')

    # bom_line_ids = fields.Many2many('mrp.bom.line', string='Bom Line')
    operation_ids = fields.One2many('project.mrp.bom.operation', 'project_bom_line_id', string='Operations',
                                    ondelete='cascade')
    # ready_for_bom = fields.Boolean('Ready to use in BOM')
    # copy_from_bom_id = fields.Many2one('mrp.bom', 'Copy from BOM', related='project_bom_id.bom_id.copy_from_bom_id')
    description = fields.Char('Description', translate=True)
    editable = fields.Boolean('Editable')
    qty_available = fields.Float('Quantity On Hand', compute='_compute_qty_available')
    virtual_available = fields.Float('Forecast Quantity', compute='_compute_virtual_available')

    _sql_constraints = [
        ('bom_qty_zero', 'CHECK (product_qty>=0)', 'All product quantities must be greater or equal to 0.\n'
                                                   'Lines with 0 quantities can be used as optional lines. \n'
                                                   'You should install the mrp_byproduct module if you want to manage extra products on BoMs !'),
    ]

    @api.constrains('product_tmpl_id')
    def _check_product_recursion(self):
        for bom in self:
            # if bom.bom_line_ids.filtered(lambda x: x.product_id.product_tmpl_id == bom.product_tmpl_id):
            #     raise ValidationError(_('BoM line product %s should not be same as BoM product.') % bom.display_name)
            if len(bom.project_bom_id.mapped('project_bom_line_ids').mapped('product_tmpl_id').filtered(
                lambda r: r == bom.product_tmpl_id).ids) > 1:
                raise ValidationError(_('Project line product %s should be only '
                                        'present one time in project products list.') % bom.product_tmpl_id.name)

    def _compute_stock_value(self):
        for record in self:
            record.avg_price_unit = record._get_average_price()

    def _get_average_price(self):
        avg_price_unit = []
        avg_qty_invoiced = []
        # for product_id in self.product_tmpl_id.product_variant_ids:
        #     purchase_ids = self.env['purchase.order.line'].search([
        #         ('product_id', '=', product_id.id),
        #         ('state', 'in', ['purchase', 'done'],),
        #     ])
        #     for purchase_id in purchase_ids:
        #         if purchase_id.qty_received != 0.0:
        #             price_subtotal = purchase_id._get_stock_move_price_unit() * purchase_id.qty_received
        #             avg_price_unit.append(price_subtotal)
        #             avg_qty_invoiced.append(purchase_id.qty_received)
        avg_price_unit_sum = sum(avg_price_unit)
        avg_qty_invoiced_sum = sum(avg_qty_invoiced)
        avg_qty_invoiced_sum = avg_qty_invoiced_sum != 0.0 and avg_qty_invoiced_sum or 1.0
        return avg_price_unit_sum / avg_qty_invoiced_sum

    @api.depends('operation_ids')
    def _compute_qty_available(self):
        for record in self:
            record.qty_available = sum([x.purchased_product_qty for x in record.operation_ids.mapped('product_id')])

    @api.depends('operation_ids')
    def _compute_virtual_available(self):
        for record in self:
            record.virtual_available = sum([x.purchased_product_qty for x in record.operation_ids.mapped('product_id')])

    @api.onchange('operation_ids')
    def onchange_operation_ids(self):
        if self.operation_ids:
            self.product_qty = sum([x.product_qty for x in self.operation_ids])

    @api.onchange('product_uom_id')
    def onchange_product_uom_id(self):
        res = {}
        if not self.product_uom_id or not self.product_tmpl_id:
            return res
        if self.product_uom_id.category_id != self.product_tmpl_id.uom_id.category_id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id
            res['warning'] = {'title': _('Warning'), 'message': _(
                'The Product Unit of Measure you chose has a different category than in the product form.')}
        return res

    @api.onchange('product_tmpl_id')
    def onchange_product_tmpl_id(self):
        res = {}
        if self.product_tmpl_id:
            # product_type_id = False
            product_tmpl_id = self.product_tmpl_id
            product_type_id = product_tmpl_id.categ_id.get_product_type_id()
            if product_tmpl_id.product_type_id:
                product_type_id = product_tmpl_id.product_type_id
            if product_type_id:
                self.product_type_id = product_type_id.id
                self.sequence = int(product_type_id.code or '0')
        return res

    @api.onchange('product_type_id')
    def onchange_product_type_id(self):
        self.sequence = int(self.product_type_id.code or '0')

    # @api.onchange('product_id')
    # def onchange_product_id(self):
    #     res = {}
    #     if self.product_id:
    #         self.product_uom_id = self.product_id.uom_id.id
    #         self.product_tmpl_id = self.product_id.product_tmpl_id.id
    #         res['domain'] = {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
    #         # product_type_id = False
    #         product_tmpl_id = self.product_id.product_tmpl_id
    #         product_type_id = product_tmpl_id.categ_id.get_product_type_id()
    #         if product_tmpl_id.product_type_id:
    #             product_type_id = product_tmpl_id.product_type_id
    #         if product_type_id:
    #             self.product_type_id = product_type_id.id
    #         self._onchange_quantity()
    #     return res

    @api.onchange('product_qty', 'product_uom_id')
    def _onchange_quantity(self):
        if not self.product_tmpl_id:
            return
        seller = self.env['product.supplierinfo']
        for product_id in self.product_tmpl_id.product_variant_ids:
            seller = product_id._select_seller(
                partner_id=self.partner_id,
                quantity=self.product_qty,
                uom_id=self.product_uom_id)
            if seller:
                break
        if seller:
            price_unit = seller.price if seller else 0.0
            company_id = self.project_bom_id.company_id
            if price_unit and seller and company_id.currency_id and seller.currency_id != company_id.currency_id:
                price_unit = seller.currency_id._convert(
                    from_amount=price_unit,
                    to_currency=company_id.currency_id,
                    company=seller.company_id or self.env.company,
                    date=fields.Date.today(),
                    round=False,
                )

            if seller and self.product_uom_id and seller.product_uom != self.product_uom_id:
                price_unit = seller.product_uom._compute_price(price_unit, self.product_uom_id)

            self.price_unit = price_unit

    # @api.onchange('bom_line_ids')
    # def onchange_product_id(self):
    #     for record in self:
    #         if len(record.bom_line_ids.ids) > 0:
    #             record.ready_for_bom = True

    # @api.multi
    # def transfer_bom_line(self):
    #     for record in self:
    #         # if record.project_bom_id.work_added and record.project_bom_id.bom_id and record.ready_for_bom:
    #         #     if record.copy_from_bom_id:
    #         #         for line in record.copy_from_bom_id.bom_line_ids. \
    #         #                 filtered(lambda r: r.product_id.id in record.product_tmpl_id.product_variant_ids.ids):
    #         #             bom_line_id = self.env['mrp.bom.line'].create({
    #         #                 'product_id': line.product_id.id,
    #         #                 'product_uom_id': line.product_uom_id.id,
    #         #                 'product_qty': line.product_qty,
    #         #                 'sequence': record.sequence + line.sequence,
    #         #                 'attribute_value_ids': [(6, False, line.attribute_value_ids.ids)],
    #         #                 'operation_id': line.operation_id.id,
    #         #                 # 'project_bom_line_id': record.id,
    #         #                 'bom_id': record.project_bom_id.bom_id.id,
    #         #             })
    #         #             record.bom_line_ids |= bom_line_id
    #         if not record.project_bom_id.work_added and \
    #             record.project_bom_id.bom_id and len(record.bom_line_ids.ids) > 0:
    #             bom_id = record.project_bom_id.bom_id.id
    #             bom_line_ids = record.bom_line_ids.ids
    #             action = self.env.ref('mrp_bom_component_menu.mrp_bom_form_action2')
    #             action = action.read()[0]
    #             action.update({
    #                 'context': {
    #                     'default_bom_id': bom_id,
    #                     'default_project_bom_line_id': record.id,
    #                     'default_operation_id': record.operation_id and record.operation_id.id or False
    #                 },
    #                 'domain': [('id', 'in', bom_line_ids), ('bom_id', '=', record.project_bom_id.bom_id.id)],
    #             })
    #             return action
    #
    #         else:
    #             if not record.project_bom_id.bom_id:
    #                 record.project_bom_id.action_create_bom()
    #             mrp_product_tmpl_id = record.project_bom_id.product_tmpl_id \
    #                                   and record.project_bom_id.product_tmpl_id.id or False
    #             product_tmpl_id = record.product_tmpl_id.id
    #             bom_id = record.project_bom_id.bom_id.id
    #             # bom_line_ids = record.project_bom_id.bom_id.bom_line_ids.ids
    #             action = self.env.ref('mrp_bom_multi_mgmt.action_bom_manage_variant')
    #             action = action.read()[0]
    #             action.update({
    #                 'context': {'default_mrp_product_tmpl_id': mrp_product_tmpl_id,
    #                             'default_bom_id': bom_id,
    #                             # 'default_bom_line_ids': bom_line_ids,
    #                             'default_product_tmpl_id': product_tmpl_id,
    #                             'default_project_bom_line_id': record.id,
    #                             'default_routing_id': record.project_bom_id.bom_id.routing_id.id,
    #                             }
    #             })
    #             return action

    def operation_bom_line(self):
        for record in self:
            action = self.env.ref('project_bom.project_mrp_bom_operation_form_action')
            action = action.read()[0]
            action.update({
                'context': {
                    'default_product_tmpl_id': record.product_tmpl_id.id,
                    'default_project_bom_line_id': record.id,
                    'default_product_uom_id': record.product_uom_id.id,
                    'default_project_bom_id': record.project_bom_id.id,
                    'use_project_bom': True,
                },
                'domain': [('id', 'in', record.operation_ids.ids)],
            })
            return action

    def get_price(self):
        line_ids = self.env['project.mrp.bom.line']
        action = self.env.ref('project_bom.act_open_bom_get_purchase_price').read()[0]
        for record in self:
            line_ids |= record
        action['active_ids'] = line_ids.ids
        return action

    @api.model_create_multi
    def create(self, values):
        for vals in values:
            if 'product_id' in vals and 'product_uom_id' not in vals:
                vals['product_uom_id'] = self.env['product.product'].browse(vals['product_id']).uom_id.id
        return super(ProjectMrpBomLine, self).create(values)

    def unlink(self):
        for record in self:
            for operation in record.mapped('operation_ids'):
                operation.unlink()
        return super(ProjectMrpBomLine, self).unlink()


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
