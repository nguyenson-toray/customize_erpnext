from frappe.model.document import Document


class UniformSetting(Document):
    # Rules now live in the standalone "Uniform Rule" DocType (each rule
    # validates its own item shape). Nothing to do here.
    pass
