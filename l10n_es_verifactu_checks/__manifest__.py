{
    "name": "VERI*FACTU checks before posting",
    "version": "16.0.3.0.0",
    "category": "Accounting",
    "summary": "Warn before posting invoices that VERI*FACTU may reject",
    "depends": ["account", "l10n_es_verifactu_oca"],
    "data": [
        "security/ir.model.access.csv",
        "views/post_warning_wizard.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
