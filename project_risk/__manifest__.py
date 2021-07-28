{
    'name': 'Project Risk',
    'summary': 'MOR risk management method',
    'author': 'Onestein, Odoo Community Association (OCA)',
    'license': 'AGPL-3',
    'website': 'https://github.com/OCA/project',
    'category': 'Project Management',
    'version': '11.0.1.0.1',
    'depends': [
        'project'
    ],
    'data': [
        'security/ir_model_access.xml',

        'data/project_risk_response_category_data.xml',
        'data/project_risk_category_data.xml',

        'views/project_risk_response_category_view.xml',
        'views/project_risk_category_view.xml',
        'views/project_risk_view.xml',
        'views/project_project_view.xml',

        'menuitems.xml',
    ],
    'installable': True,
}