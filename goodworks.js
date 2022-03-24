// Copyright (c) 2022, ER and contributors
// For license information, please see license.txt
frappe.provide("matrix");

frappe.ui.form.on('Employee Goodworks', {

	onload: function(frm) {
	if (!(frm.doc.owner==frappe.session.user)){
		frm.set_df_property("shift_in_timedate","read_only",1);
		frm.set_df_property("overtime_hours","read_only",1);
		frm.set_df_property("extra_shift_timedate","read_only",1);
	};

	if ((frm.doc.workflow_state == "Pending for HRBP Approval") && (frappe.session.user == frm.doc.hrbp_id)){
		unhide_field(["total_worked_hours"]);
		frm.set_df_property("total_worked_hours","read_only",1);
		cur_frm.refresh_fields();
	}

	if (cur_frm.doc.workflow_state == 'Draft'){
		var today = new Date()
		var date = today.getFullYear()+'-'+(today.getMonth()+1)+'-'+today.getDate();
		var time = today.getHours() + ":" + today.getMinutes() + ":" + today.getSeconds();
		var current_datetime = date+' '+time;
		frm.set_value("current_datetime", current_datetime)
	}

	},
	before_save:function (frm) {
		frappe.call({
			method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.type_of_request",
			args: {
				"shift_in_timedate": frm.doc.shift_in_timedate,
				"shift_out_timedate": frm.doc.shift_out_timedate,
				"extra_shift_timedate": frm.doc.current_datetime},
			callback: function(response){
				if(response.message){
					frm.set_value("request_type", response.message[0]);
				}
				if (frm.doc.request_type != "ODD Shift" && frm.doc.overtime_hours < 3) {
					frappe.throw(__("Overtime hours must be greater than or equal to 3 hours"));
				}

				if (cur_frm.doc.workflow_state == 'Draft'){
					var now = frappe.datetime.now_datetime();
					frm.set_value("extra_shift_timedate", now);
				}
			
			}
		})

		// frappe.call({
		// 	method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.check_request_overlapping",
		// 	args: {
		// 		"shift_in_timedate": frm.doc.shift_in_timedate,
		// 		"extra_shift_timedate": frm.doc.extra_shift_timedate},
		// 	callback: function(response){
		// 		if(response.message){
		// 			if(response.message == "shift in overlapping with shift out of previous request"){
		// 				frappe.throw(("Shift In time of this request is overlapping with Shift Out time of most previous request, please check previous requests."))
		// 			}
		// 			else if (response.message == "extra shift overlapping with shift out of previous request"){
		// 				frappe.throw(("Extra Shift time of this request is overlapping with Shift Out time of most previous request, please check previous requests."))
		// 			}
		// 			else if (response.message == "shift in overlapping with extra shift of previous request"){
		// 				frappe.throw(("Shift In time of this request is overlapping with Extra Shift time of most previous request, please check previous requests."))
		// 			}
		// 			else if (response.message == "extra shift overlapping with extra shift of previous request"){
		// 				frappe.throw(("Extra Shift time of this request is overlapping with Extra Shift time of most previous request, please check previous requests."))
		// 			}
		// 		}
		// 	}
		// })
	},
	validate:function (frm) {
		
		if (frm.doc.shift_in_timedate == undefined){
			frappe.throw("Please enter valid Shift in time and date")
		}
		if ((frm.request_type == "Extended Shift") && (frm.doc.overtime_hours == undefined)) {
			frappe.throw("Please enter valid Overtime Hours")
		}
		if ((frm.doc.overtime_hours == '') && (frm.request_type == "Extended Shift")) {
			frappe.throw("Please fill Overtime Hours")
		}
		else {
			frappe.call({
				method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.request_date",
				args: {
					"extra_shift_timedate": frm.doc.current_datetime},
				callback: function(response){
					frm.set_value("request_date", response.message)
				}
			
			})
		}
	},
	
	refresh: function(frm) {
 
		$('#table_div').remove();
        $('#action_button_section').remove();
        matrix.enable_action_history_view();

		//condition here
		if (frm.doc.__islocal) 		//permission query condition  ...|| frm.doc.workflow_state == "Draft"...
		frappe.call({
			method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.employee_eligibility",			//put error in prepopulation of field
			callback: function(response){
				if(response.message == "invalid level"){
					frappe.throw("Your level is not among L1, L2 or L3 in order to create Employee Overtime Request");
				}
				else if(response.message == "invalid department"){
					frappe.throw("Your department is not among Operations - Field - NTEX in order to create Employee Overtime Request");
				}
				else {
					frappe.call({
						method: 'frappe.client.get_value',
						args: {
							doctype: 'Employee',
							filters: { 'user_id': frappe.session.user },
							fieldname: [
								'name',
								'user_id',
								'employee_name',
								'department',
								'reports_to',
								'level',
								'employment_type'
							]
						}
					}).then ( (r) => {		//is_local or check workflow state (should be draft state)
						if (r.message) {
							// if (r.message.department == "Operations - Field - NTEX") {
								frm.set_value('employee_id', r.message.name);			//EMP code
								frm.set_value('employee_mail', r.message.user_id);		//email				//change employee_mail to user_id
								frm.set_value('employee_name', r.message.employee_name)	//name
								frm.set_value('department', r.message.department)		//department
								frm.set_value('employee_level', r.message.level)		//level
								frm.set_value('employment_type', r.message.employment_type) //employment type
							
								frappe.call({
									method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.get_manager_sr_manager_bo_hrbp",
									args: {
									"employee_id": r.message.name
									},
									callback: function(r) 
									{
										if(r.message) 
										{
											for (const [key, value] of Object.entries(r.message)) 
											{
											if(key=="manager_id"){frm.set_value("manager_id",value);}
											if(key=="manager_name"){frm.set_value("manager_name",value);}
											if(key=="sr_manager_id"){frm.set_value("request_approver_id",value);} 
											if(key=="sr_manager_name"){frm.set_value("request_approver_name",value);}
											if(key=="business_approver_id"){frm.set_value("business_head_id",value);}
											if(key=="business_approver_name"){frm.set_value("business_head_name",value);}
											if(key=="hrbp_id"){frm.set_value("hrbp_id",value);}
											if(key=="hrbp_name"){frm.set_value("hrbp_name",value);}
											if(key=="hrbp_name"){frm.set_value("hrbp_name",value)}
											}
										}
									}
						
								})
						}
					})
				}
			}
		})
		
		if(cur_frm.doc.manager_id != frappe.session.user){
			frm.set_df_property("manager_comment","read_only",true); 
            frm.refresh_field("manager_comment");
		}

		if(cur_frm.doc.request_approver_id != frappe.session.user){
			frm.set_df_property("request_approver_comment","read_only",true); 
            frm.refresh_field("request_approver_comment");
		}
		
		if(cur_frm.doc.hrbp_id != frappe.session.user){
			frm.set_df_property("hrbp_comment","read_only",true); 
			frm.refresh_field("hrbp_comment");
		}

		if (frm.doc.request_status == "Pending for Manager Approval" || frm.doc.request_status == "Pending for Request Approver Approval" || frm.doc.request_status == "Pending for HRBP Approval") {
			frm.set_df_property("shift_in_timedate","read_only",true)
			frm.set_df_property("overtime_hours","read_only",true)
			frm.set_df_property("extra_shift_timedate","read_only",true)
		}

		if ((frm.doc.request_status == "Pending for HRBP Approval") && (frappe.session.user == cur_frm.doc.hrbp_id)) {
			frm.set_df_property("shift_in_timedate","read_only",false)
			frm.set_df_property("overtime_hours","read_only",false)
			frm.set_df_property("extra_shift_timedate","read_only",false)
		}

		//update manager button
		if ((frappe.session.user == cur_frm.doc.hrbp_id) && ((cur_frm.doc.workflow_state != 'Draft') && (cur_frm.doc.workflow_state != 'Approved' ) && (cur_frm.doc.workflow_state != 'Abandoned' ))) {
	
			cur_frm.add_custom_button(__("Update Manager"), function () {
				frappe.call({
					method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.get_manager_sr_manager_bo_hrbp",
					args: {
						"employee_id" : frm.doc.employee_id
					},
					callback: function(r) 
					{
						if(r.message) 
						{
							for (const [key, value] of Object.entries(r.message)) 
							{
							if(key=="manager_id"){
								if (value != frm.doc.manager_id) {
									if ((cur_frm.doc.workflow_state == 'Draft') && (cur_frm.doc.workflow_state == 'Pending for Manager Approval')) {
										if(!frm.doc.manager_comment) {
											frappe.msgprint("Doing this action will change the manager.");		//updating manager
											frm.set_value("manager_id",value);
										}
										else {
											frappe.msgprint("Manager can't be changed.");		//Manager Commented
										}
									}
								}
							}
							if(!frm.doc.manager_comment) {
								if(key=="manager_name"){frm.set_value("manager_name",value);}
							}
							if(key=="sr_manager_id"){
								if (value != frm.doc.request_approver_id) {
									if ((cur_frm.doc.workflow_state == 'Draft') && (cur_frm.doc.workflow_state == 'Pending for Manager Approval') && (cur_frm.doc.workflow_state == 'Pending for Request Approver Approval')) {
										if(!frm.doc.request_approver_comment) {
											frappe.msgprint("Doing this action will change the Request Approver.");		//updating request approver
											frm.set_value("request_approver_id",value);
										}
										else {
											frappe.msgprint("Request Approver can't be changed.");		//Request Approver Commented
										}
									}
								} 
							}
							if(!frm.doc.request_approver_comment) {
								if(key=="sr_manager_name"){frm.set_value("request_approver_name",value);}
							}

							if(key=="business_approver_id"){
								if (value != frm.doc.business_head_id) {
									if ((cur_frm.doc.workflow_state == 'Draft') && (cur_frm.doc.workflow_state == 'Pending for Manager Approval') && (cur_frm.doc.workflow_state == 'Pending for Request Approver Approval')) {
										frappe.msgprint("Doing this action will change the Business Head.");		//updating business head
										frm.set_value("business_head_id",value);
									}
								}
							}
							if(key=="business_approver_name"){frm.set_value("business_head_name",value);}
		
							if(key=="hrbp_id"){
								if (value != frm.doc.hrbp_id) {
									if ((cur_frm.doc.workflow_state == 'Draft') && (cur_frm.doc.workflow_state == 'Pending for Manager Approval') && (cur_frm.doc.workflow_state == 'Pending for Request Approver Approval') && (cur_frm.doc.workflow_state == 'Pending for Request Approver Approval')) {
										if(!frm.doc.request_approver_comment) {
											frappe.msgprint("Doing this action will change the HRBP.");					//updating hrbp
											frm.set_value("hrbp_id",value);
										}
										else {
											frappe.msgprint("HRBP can't be changed.");		//HRBP commented
										}
									}
								}
							}
							if (value != frm.doc.hrbp_id) {
								if(key=="hrbp_name"){frm.set_value("hrbp_name",value);}
							}
							}
						}
					}
				})
			})		
		}

		//abandoned button
		
		if ((frappe.session.user == cur_frm.doc.hrbp_id) && ((cur_frm.doc.workflow_state != 'Draft') && (cur_frm.doc.workflow_state != 'Rejected' ) && (cur_frm.doc.workflow_state != 'Abandoned' ))) {
			let dialog_box = new frappe.ui.Dialog({
				title: 'Enter Reason for Abandonment',
				fields: [
					{
						label: 'Reason for Abandonment',
						fieldname: 'reason_for_abandonment',
						fieldtype: 'Data'
					},
					
				],
				primary_action_label: 'Submit',
				primary_action(values) {
					if(!values['reason_for_abandonment']) {
						frappe.throw(__('Please Enter Reason for Abandonment'))
					}
					frappe.call({
						method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.confirm_abandonment",
						
						args: {
							"doc": frm.doc,
							"approver" : frappe.session.user,
							"reason_for_abandonment" : values['reason_for_abandonment']
						},
						callback: function (r) {
							cur_frm.reload_doc()
						}
					})

					dialog_box.hide();
				}
			});
			cur_frm.add_custom_button(__("Abandone"), function () {
					dialog_box.show();
				})
			
		}
	},

	shift_in_timedate: function(frm){
		frappe.call({
			method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.shiftout_timedate",
			args: {"shift_in_timedate": frm.doc.shift_in_timedate},
			callback: function(response){
				frm.set_value("shift_out_timedate", response.message)

				frappe.call({
					method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.type_of_request",
					args: {
						"shift_in_timedate": frm.doc.shift_in_timedate,
						"shift_out_timedate": frm.doc.shift_out_timedate,
						"extra_shift_timedate": frm.doc.current_datetime},
					callback: function(response){
						console.log(response.message[0])
						if(response.message[0] == "Extended Shift") {
							unhide_field(["overtime_hours"]);
							cur_frm.refresh_fields();
						}
						else {
							hide_field(["overtime_hours"]);
							cur_frm.refresh_fields();
						}
						if (frm.doc.request_type != "ODD Shift" && frm.doc.overtime_hours < 3) {
							frappe.throw(__("Overtime hours must be greater than or equal to 3 hours"));
						}
					}
				})

				frappe.call({
					method: "matrix.matrix.doctype.employee_goodworks.employee_goodworks.calculate_total_worked_hours",
					args: {
						"shift_in": frm.doc.shift_in_timedate,
						"shift_out": frm.doc.shift_out_timedate,
						"extra_shift": frm.doc.current_datetime},
					callback: function(response){
						console.log(response.message)
						frm.set_value("total_worked_hours", Math.round((Math.abs(response.message) + Number.EPSILON) * 100) / 100)
						frm.refresh_field("total_worked_hours")
					}
				})
			}
		})

	},

	extra_shift_timedate:function(frm) {
						
		//frm.set_value("overtime_hours", Math.round((Math.abs(response.message) + Number.EPSILON) * 100) / 100)


	}

	

});


matrix.enable_action_history_view = function () {
    if (!cur_frm) {
        return;
    }

    if (cur_frm.doc.__islocal) {
        return;
    }

    const tag = new matrix.action_history(cur_frm.doc.doctype, cur_frm.doc.name);
}

matrix.action_history = class {
    constructor(doctype, docname) {
        this.doctype = doctype;
        this.docname = docname;
        this.add_button_area()
    }
    add_button_area() {
        const me = this;
        $('#table_div').remove();
        $('#action_button_section').remove();
        this.button_area = $(cur_frm.page.body).find(".form-page")
            .append(`<div id="action_button_section" style="padding-left:20px;padding-right:20px;padding-top:10px">
                    <div class="col-sm-12"><h6 class="form-section-heading uppercase">Action History</h6></div>
                    <div class="section-body" style="padding-top:10px;padding-bottom:10px">
                    <button id="action-button-tag" class="btn btn-default btn-xs" data-fieldtype="Button" data-fieldname="" placeholder="" data-doctype="" value="">Load Action History</button>
                    </div>
                    </div>`)
        $(document).off("click", `#action-button-tag`);
        $(document).on("click", `#action-button-tag`, () => {
            me.add_button_handle()
        });
    }
    add_button_handle() {
        $('#table_div').remove();
        frappe.call({
            method: "matrix.api.action_history_api.fetch_action_log",
            args: {
                "doc_name": cur_frm.doc.name,
                "doc_type": cur_frm.doc.doctype
            },
            callback: function (r) {
                $(cur_frm.page.body).find("#action_button_section")
                    .append(
                        `<div id="table_div" class="frappe-control" data-fieldtype="HTML" data-fieldname="" title="">
                    `+ r.message + `
                    </div>`
                    );
            }
        });
    }
};

