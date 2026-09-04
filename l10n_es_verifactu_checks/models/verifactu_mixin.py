from lxml import etree

from odoo import api, models
from odoo.modules.module import get_resource_path


VERIFACTU_SCHEMA_NS = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd"

VERIFACTU_SCHEMA_FILE = "SuministroInformacion.xsd"
VERIFACTU_LIST_WRAPPERS = frozenset(
    {"Destinatarios", "FacturasRectificadas", "FacturasSustituidas"}
)


class VerifactuMixin(models.AbstractModel):
    _inherit = "verifactu.mixin"

    @api.model
    def _get_verifactu_schema_tree(self):
        """Load a fresh official schema tree with networking disabled."""
        parser = etree.XMLParser(no_network=True)
        return etree.parse(
            get_resource_path(
                "l10n_es_verifactu_checks", "data", VERIFACTU_SCHEMA_FILE
            ),
            parser,
        )

    @api.model
    def _get_verifactu_schema_order(self, tree, root_tag):
        """Return the child order required by the type of the root element."""
        xs = "{http://www.w3.org/2001/XMLSchema}"
        root = tree.getroot()
        type_name = ""
        for element in root.findall("%selement" % xs):
            if element.get("name") == root_tag:
                type_name = (element.get("type") or "").split(":")[-1]
                break
        order = []
        for complex_type in root.iter("%scomplexType" % xs):
            if complex_type.get("name") != type_name:
                continue
            for child in complex_type.iter("%selement" % xs):
                name = child.get("name")
                if name and child.getparent().getparent() is complex_type:
                    order.append(name)
            break
        return order

    @api.model
    def _verifactu_render_element(self, parent, tag, value):
        if value is None or value is False:
            return
        qualified_tag = "{%s}%s" % (VERIFACTU_SCHEMA_NS, tag)
        if isinstance(value, list):
            if tag in VERIFACTU_LIST_WRAPPERS:
                wrapper = etree.SubElement(parent, qualified_tag)
                for item in value:
                    for key, sub_value in item.items():
                        self._verifactu_render_element(wrapper, key, sub_value)
                return
            for item in value:
                self._verifactu_render_element(parent, tag, item)
            return
        element = etree.SubElement(parent, qualified_tag)
        if isinstance(value, dict):
            for key, sub_value in value.items():
                self._verifactu_render_element(element, key, sub_value)
        else:
            element.text = str(value)

    @api.model
    def _format_verifactu_schema_error(self, invalid):
        errors = [entry.message for entry in invalid.error_log] or [str(invalid)]
        return "\n".join(errors)

    def _validate_verifactu_registro(self, invoice_dict):
        """Return every official-XSD error in the generated registration."""
        self.ensure_one()
        if not invoice_dict:
            return None
        root_tag = next(iter(invoice_dict))
        document = etree.Element("{%s}%s" % (VERIFACTU_SCHEMA_NS, root_tag))
        values = invoice_dict[root_tag] or {}
        tree = self._get_verifactu_schema_tree()
        schema_order = self._get_verifactu_schema_order(tree, root_tag)
        ordered_keys = [key for key in schema_order if key in values] + [
            key for key in values if key not in schema_order
        ]
        for key in ordered_keys:
            self._verifactu_render_element(document, key, values[key])
        try:
            etree.XMLSchema(tree).assertValid(document)
        except etree.DocumentInvalid as invalid:
            return self._format_verifactu_schema_error(invalid)
        return None
