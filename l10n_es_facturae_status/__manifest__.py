# -*- coding: utf-8 -*-
{
    'name': "l10n_es_facturae_status",

    'summary': """Adds FACe status to invoice list""",

    'description': """
        Adds FACe status to invoice list
    """,

    'author': "zvERP",
    'website': "https://www.zvERP.com",
    'license': 'AGPL-3',

    'category': 'Uncategorized',
    'version': '16.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'l10n_es_facturae_face'],

    # always loaded
    'data': [
        'views/account_move.xml',
    ],
}
