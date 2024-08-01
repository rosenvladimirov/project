# Copyright 2023 Rosen Vladimirov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Project Bom',
    'summary': """
        Project bom without mrp module""",
    'version': '17.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Rosen Vladimirov,Odoo Community Association (OCA)',
    'website': 'https://github.com/rosenvladimirov/project',
    'depends': [
        'sale',
        'project',
        'product',
        'purchase',
    ],
    'data': [
        'data/ir_cron.xml',
        'security/ir.model.access.csv',
        'views/project_mrp_bom_views.xml',
        'views/product_template_views.xml',
        'wizards/purchase_prices.xml',
        'wizards/product_bom_import_wizard.xml',
    ],
    'demo': [
    ],
}
