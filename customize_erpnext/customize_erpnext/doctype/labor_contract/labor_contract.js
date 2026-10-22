// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

const LC_METHOD = 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract';

frappe.ui.form.on('Labor Contract', {
	refresh(frm) {
		set_start_date_label(frm);
		setup_scan_upload(frm);
		if (frm.doc.scan) {
			frm.add_custom_button(__('Download Signed Scan'), () => download_scan(frm));
		}
	},

	document_type(frm) {
		set_start_date_label(frm);
	},
});

// One DocType holds both kinds of document; for an appendix the start date is
// its effective date.
function set_start_date_label(frm) {
	const is_appendix = frm.doc.document_type === 'Appendix';
	frm.set_df_property('start_date', 'label', is_appendix ? __('Effective Date') : __('Start Date'));
	frm.set_df_property('start_date', 'description', is_appendix ? __('The appendix number uses the month of this date.') : '');
}

// The Scan field uploads through upload_scan, which checks the file name before
// any File is created; the server saves the record itself, so reload instead of
// letting the Attach control save a stale copy.
function setup_scan_upload(frm) {
	frm.set_df_property('scan', 'read_only', frm.is_new() ? 1 : 0);
	frm.fields_dict.scan.df.options = {
		method: `${LC_METHOD}.upload_scan`,
		restrictions: { allowed_file_types: ['.pdf', '.jpg', '.jpeg', '.png'] },
		disable_file_browser: true,
		allow_web_link: false,
		allow_take_photo: false,
		allow_google_drive: false,
		allow_toggle_private: false,
		make_attachments_public: 0,
		upload_notes: __('The file name must start with {0}, e.g. {0}.pdf', [frm.doc.name]),
		on_success: () => frm.reload_doc().then(() => offer_mark_signed(frm)),
	};
}

// Saved under the document number, whatever the uploaded file was called
function download_scan(frm) {
	const ext = (frm.doc.scan.match(/\.[^./]+$/) || [''])[0].toLowerCase();
	const link = document.createElement('a');
	link.href = frm.doc.scan;
	link.download = frm.doc.name + ext;
	document.body.appendChild(link);
	link.click();
	link.remove();
}

function offer_mark_signed(frm) {
	if (frm.doc.status === 'Signed') {
		return;
	}
	frappe.prompt(
		[
			{
				fieldtype: 'Date',
				fieldname: 'signed_on',
				label: __('Signed On'),
				default: frappe.datetime.get_today(),
				reqd: 1,
				description: __('Actual signing date'),
			},
		],
		(values) => {
			frappe.call({
				method: `${LC_METHOD}.bulk_mark_signed`,
				args: { contracts: JSON.stringify([frm.doc.name]), signed_on: values.signed_on },
				freeze: true,
				callback: (r) => {
					const error = r.message && (r.message.errors || [])[0];
					if (error) {
						frappe.msgprint(error.error);
					}
					frm.reload_doc();
				},
			});
		},
		__('Scan attached — mark {0} as Signed?', [frm.doc.name]),
		__('Mark as Signed')
	);
}
