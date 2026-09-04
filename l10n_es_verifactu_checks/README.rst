VERI*FACTU checks before posting
================================

This addon checks an outgoing VERI*FACTU invoice immediately before posting.
If the generated registration is expected to be rejected, the invoice stays in
draft and a small wizard explains every detected problem. The user can go back
and correct it or deliberately choose *Emitir igualmente*, knowing that the
invoice will have to be corrected afterwards. The decision and the validation
errors are recorded in the invoice chatter.

The checks only apply to outgoing invoices and refunds for which
``verifactu_enabled`` is true. Simplified invoices do not require recipient
identification because that block is not sent to AEAT.

The explicit checks cover a missing or future invoice date, recipient identity,
and the format and control character of Spanish NIFs belonging to the receiver,
issuer and software developer. Spanish NIF validation uses Odoo's ``base_vat``
implementation.

OCA must first assign the invoice number and generate its registration date,
hash and chain before the complete record exists. This is done in a database
savepoint. The final payload is then validated against the official AEAT schema;
if it is invalid, the savepoint is rolled back before opening the wizard, so the
invoice remains in draft. ``SuministroInformacion.xsd``, ``SuministroLR.xsd``
and ``xmldsig-core-schema.xsd`` are included in ``data/`` and are always read
locally. The signature schema import uses its local relative path.

Values which are safe to normalise are adjusted before building the record:
receiver names are limited to 120 characters, operation descriptions to 500,
tax rates to two decimals, and the mutually exclusive empty ``IDOtro`` developer
block is removed when a NIF is present.
