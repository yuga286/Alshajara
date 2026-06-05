# import frappe
# from frappe.utils import strip_html

# def update_todo_latest_comment(doc, method):
#     """
#     When a comment is added to a ToDo,
#     copy the comment content into ToDo.latest_comment
#     """

#     # Only for ToDo comments
#     if doc.reference_doctype != "ToDo" or not doc.reference_name:
#         return

#     # Ignore non-user comments
#     if doc.comment_type != "Comment":
#         return

#     # Clean HTML from comment
#     comment_text = strip_html(doc.content or "").strip()

#     if not comment_text:
#         return

#     # Update ToDo directly (no recursion)
#     frappe.db.set_value(
#         "ToDo",
#         doc.reference_name,
#         "latest_comment",
#         comment_text,
#         update_modified=False
#     )

import frappe
from frappe.utils import strip_html

def update_todo_latest_comment(doc, method):

    if doc.reference_doctype != "ToDo" or not doc.reference_name:
        return

    if doc.comment_type != "Comment":
        return

    comment_text = strip_html(doc.content or "").strip()

    if not comment_text:
        return

    # Load ToDo document properly
    todo = frappe.get_doc("ToDo", doc.reference_name)

    # Update field
    todo.latest_comment = comment_text

    # Save document (this triggers Notification)
    todo.save(ignore_permissions=True)
