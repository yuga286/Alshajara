import frappe
from erpnext.crm.doctype.opportunity.opportunity import make_quotation as erp_make_quotation

@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
    quotation = erp_make_quotation(source_name, target_doc)

    opportunity = frappe.get_doc("Opportunity", source_name)

    quotation.project_capacity = opportunity.project_capacity
    quotation.capacity_unit = opportunity.capacity_unit

    return quotation



import frappe

def create_prospect_silently(lead_name):

    lead = frappe.get_doc("Lead", lead_name)

    existing = frappe.db.exists("Prospect", {
        "lead_name": lead.name
    })

    if existing:
        return existing

    prospect = frappe.new_doc("Prospect")
    prospect.prospect_name = lead.lead_name or lead.company_name
    prospect.lead_name = lead.name

    prospect.insert(ignore_permissions=True)

    return prospect.name







import frappe
from erpnext.crm.doctype.lead.lead import make_opportunity as erpnext_make_opportunity
from frappe.contacts.doctype.address.address import get_address_display


@frappe.whitelist()
def custom_make_opportunity(source_name, target_doc=None):

    doc = erpnext_make_opportunity(source_name, target_doc)

    lead = frappe.get_doc("Lead", source_name)
    set_currency_from_lead(doc, lead)

    # ============================================
    # CONTACT DETAILS
    # ============================================

    doc.contact_email = lead.email_id
    doc.contact_mobile = lead.mobile_no
    doc.contact_display = lead.lead_name

    # ============================================
    # ADDRESS
    # ============================================

    address_links = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Lead",
            "link_name": lead.name,
            "parenttype": "Address"
        },
        fields=["parent"],
        limit=1
    )

    if address_links:

        address = frappe.get_doc("Address", address_links[0].parent)

        doc.customer_address = address.name

        doc.address_display = get_address_display(address.name)

    return doc


def set_currency_from_lead(doc, lead=None):
    if not lead and doc.get("opportunity_from") == "Lead" and doc.get("party_name"):
        lead = frappe.get_doc("Lead", doc.party_name)

    if not lead:
        return doc

    currency = lead.get("currency")
    if not currency and lead.get("country"):
        currency = frappe.db.get_value("Country", lead.country, "currency")

    if currency:
        doc.currency = currency

    return doc
