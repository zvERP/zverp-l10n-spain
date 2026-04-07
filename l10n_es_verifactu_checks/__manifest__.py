{
    "name": "Require partner country on invoices and other checks",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "summary": "Block invoice confirmation when the partner has no country",
    "depends": ["account", "l10n_es_verifactu_oca"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal_view.xml",
        "views/post_warning_wizard.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
