# -*- coding: utf-8 -*-
# Copyright (c) 2022, ER and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from datetime import datetime
from datetime import timedelta
from datetime import time
from matrix.util.utils import getBO
from matrix.matrix.doctype.hrbp_configuration.hrbp_configuration import get_hrbp
import ast
import json
from matrix.api.action_history_api import log_action_history
import numpy as np
import calendar
from frappe.utils.data import now_datetime, today

class EmployeeGoodworks(Document):	#comment out line 37-55 for testing requests			
		
	def validate(self):	
		if frappe.session.user == self.employee_mail:
			now = datetime.now()
			now_string = now.strftime('%Y-%m-%d %H:%M:%S')
			if number_of_requests(now_string, self.employee_mail) == 15:
				request_month = now_string.strftime("%m")
				frappe.throw("You're out of Overtime Requests for the month of", calendar.month_name[int(request_month)])
    
		if check_employee_eligibility(self.employee_level, self.department, self.employment_type)	== 'invalid level':
			frappe.throw("Your level is not among L1, L2 or L3 in order to create Employee Overtime Request")

		elif check_employee_eligibility(self.employee_level, self.department, self.employment_type)	== 'invalid department':
			frappe.throw("Your department is not among Operations - Field - NTEX in order to create Employee Overtime Request")
   
		elif check_employee_eligibility(self.employee_level, self.department, self.employment_type) == 'invalid employment type':
		 	frappe.throw("You need to be a FTE or FTC in order to create Employee Overtime Request")
   
		#check if shift in, shift out and extra shift have valid timings
		if self.extra_shift_timedate == self.shift_in_timedate:
			frappe.throw("Shift In and Extra Shift can't be same")
   
		if self.extra_shift_timedate == self.shift_out_timedate:
			frappe.throw("Shift Out and Extra Shift can't be same")
   
		if self.shift_in_timedate == self.shift_out_timedate:
			frappe.throw("Shift In and Shift Out can't be same")
   
		#check if employee is generating the overtime request while working in a shift
		if self.request_status not in ["Pending for Manager Approval", "Pending for Request Approver Approval", "Pending for HRBP Approval", "Approved", "Rejected", "Abandoned"]:
			#check_request_timing(self.shift_in_timedate, self.shift_out_timedate, self.extra_shift_timedate, self.request_status)

			if type_of_request(self.shift_in_timedate, self.shift_out_timedate, self.extra_shift_timedate) == ("Invalid Request", "between shift in and shift out error"):
				frappe.throw("You cannot request for between shift in and shift out time");
			elif type_of_request(self.shift_in_timedate, self.shift_out_timedate, self.extra_shift_timedate) == ("Invalid Request", "pre-shift error"):
				frappe.throw("You cannot request for pre-shift overtime work less than 3 hours");
			elif type_of_request(self.shift_in_timedate, self.shift_out_timedate, self.extra_shift_timedate) == ("Invalid Request", "post-shift error"):
				frappe.throw("You cannot request for post-shift overtime work less than 3 hours");

		#check if the timings of current request are overlapping with the existing requests	(not working)
		#if self.request_status not in ["Draft", "Pending for Manager Approval", "Pending for Request Approver Approval", "Pending for HRBP Approval", "Approved", "Rejected"]:
		if frappe.session.user == self.employee_mail:
			if self.request_status not in ["Pending for Manager Approval", "Pending for Request Approver Approval", "Pending for HRBP Approval", "Approved", "Rejected", "Abandoned"]:
				if check_request_overlapping(self.shift_in_timedate, self.extra_shift_timedate, self.request_status) == "shift in overlapping with shift out of previous request":
					frappe.throw("Shift in time of this request is overlapping with shiftout time of most previous request, please check previous requests.")
				elif check_request_overlapping(self.shift_in_timedate, self.extra_shift_timedate, self.request_status) == "extra shift overlapping with shift out of previous request":
					frappe.throw("Extra shift time of this request is overlapping with shiftout time of most previous request, please check previous requests.")
		
				elif check_request_overlapping(self.shift_in_timedate, self.extra_shift_timedate, self.request_status) == "shift in overlapping with extra shift of previous request":
					frappe.throw("Shift in time of this request is overlapping with extra shift time of most previous request, please check previous requests.")
		
				elif check_request_overlapping(self.shift_in_timedate, self.extra_shift_timedate, self.request_status) == "extra shift overlapping with extra shift of previous request":
					frappe.throw(("extra shift time of this request is overlapping with extra shift time of most previous request, please check previous requests."))	
			
			if self.request_status not in ["Pending for Manager Approval", "Pending for Request Approver Approval", "Pending for HRBP Approval", "Approved", "Rejected", "Abandoned"]:	
			
				if number_of_requests(self.extra_shift_timedate, frappe.session.user) == "last request":
					frappe.msgprint("This is your last request for this month")
		
				elif number_of_requests(self.extra_shift_timedate, frappe.session.user) == "out of requests":
					extra_shift_timedate_obj = datetime.strptime(self.extra_shift_timedate, '%Y-%m-%d %H:%M:%S')
					request_month = extra_shift_timedate_obj.strftime("%m")
					frappe.throw("You're out of Overtime Requests for the month of", calendar.month_name[int(request_month)])		#	testing needed
	 
				elif number_of_requests(self.extra_shift_timedate, frappe.session.user) == "wait for approval":
					frappe.throw("You have a pending request approval for your previous request, please wait for approval or rejection")
	 
				elif number_of_requests(self.extra_shift_timedate, frappe.session.user) == "wait for clearance":
					frappe.throw("You have multiple requests pending for approval, please wait while your previous requests are cleared")

		#make manager comment mandatory
		if not self.manager_comment and frappe.session.user == self.manager_id:	
			frappe.throw(("Manager Comment is mandatory"))	   
   
def check_request_overlapping(shift_in_timedate, extra_shift_timedate, request_status):			#function to check if the timing of current request is overlapping with other requests
	 
	shift_in_timedate_obj = datetime.strptime(shift_in_timedate, '%Y-%m-%d %H:%M:%S')
	extra_shift_timedate_obj = datetime.strptime(extra_shift_timedate, '%Y-%m-%d %H:%M:%S')
	user = frappe.session.user
	req1_details = frappe.db.sql("""SELECT shift_in_timedate, shift_out_timedate, extra_shift_timedate FROM `tabEmployee Goodworks` WHERE `employee_mail` = '{0}' and ((`request_status` = 'Pending for Manager Approval') 
							  or (`request_status` = 'Pending for Request Approver Approval') or (`request_status` = 'Pending for HRBP Approval') 
							  or (`request_status` = 'Approved')) ORDER BY (DATE_FORMAT(STR_TO_DATE(extra_shift_timedate, '%d-%m-%Y'), '%d') and DATE_FORMAT(STR_TO_DATE(extra_shift_timedate, '%d-%m-%Y'), '%m') and DATE_FORMAT(STR_TO_DATE(extra_shift_timedate, '%d-%m-%Y'), '%Y')) DESC;""".format(user, as_list=True))
	#get first object and return it*****  
	
	if len(req1_details) == 0:		#if user is creating the first request
		return ""
	else:
		prev_shift_out_datetime_obj = req1_details[0][1]
		prev_extra_shift_datetime_obj = req1_details[0][2]	

		if request_status not in ["Pending for Manager Approval", "Pending for Request Approver Approval", "Pending for HRBP Approval", "Approved"]:
  
			if prev_extra_shift_datetime_obj < prev_shift_out_datetime_obj:		#check if extra time was done in preshift (previous request)
				if shift_in_timedate_obj < extra_shift_timedate_obj:			#check if extra time was done in postshift (current request)
					if prev_shift_out_datetime_obj > shift_in_timedate_obj:		#check if overlapping
						return "shift in overlapping with shift out of previous request"
						frappe.throw(("Shift in time of this request is overlapping with shiftout time of most previous request, please check previous requests."))
				else:
					if prev_shift_out_datetime_obj > extra_shift_timedate_obj:	#check if overlapping (extra time was done in preshift)
						return "extra shift overlapping with shift out of previous request"
						frappe.throw(("Extra shift time of this request is overlapping with shiftout time of most previous request, please check previous requests."))
			else:
				if shift_in_timedate_obj < extra_shift_timedate_obj:			#check if extra time was done in postshift (current request)
					if prev_extra_shift_datetime_obj > shift_in_timedate_obj:	#check if overlapping (extra time was done in postshift (previous request))
						return "shift in overlapping with extra shift of previous request"
						
						frappe.throw(("Shift in time of this request is overlapping with extra shift time of most previous request, please check previous requests."))
				else:
					if prev_extra_shift_datetime_obj > extra_shift_timedate_obj:#check if overlapping (extra time was done in postshift (previous request))
						return "extra shift overlapping with extra shift of previous request"
						frappe.throw(("extra shift time of this request is overlapping with extra shift time of most previous request, please check previous requests."))

def check_request_timing(shift_in, shift_out, extra_shift, request_status):				#function to check if the timing of current request is between working shift
	shift_in_timedate_obj = datetime.strptime(shift_in, '%Y-%m-%d %H:%M:%S')
	shift_out_timedate_obj = datetime.strptime(shift_out, '%Y-%m-%d %H:%M:%S')
	extra_shift_timedate_obj = datetime.strptime(extra_shift, '%Y-%m-%d %H:%M:%S')
	current_time = now_datetime()		#can change for testing

	if (extra_shift_timedate_obj < shift_in_timedate_obj):
		#check workflow state of the request
		if request_status not in ["Pending for Manager Approval", "Pending for Request Approver Approval", "Pending for HRBP Approval", "Approved", "Rejected"]:
			if (current_time <= shift_out_timedate_obj and current_time >= extra_shift_timedate_obj):		#pre shift 7am 11am 8pm
				return ''
			else:
				frappe.throw(("You need to create your request while you're working in a shift. (between Extra-Shift Time and Shift-Out Time.)")) 			#future date	and 	past date
				
	elif (extra_shift_timedate_obj > shift_in_timedate_obj) and (extra_shift_timedate_obj > shift_out_timedate_obj):		#post shift 10am 7pm 10pm
		if (current_time <= extra_shift_timedate_obj and current_time >= shift_in_timedate_obj):
			return ''
		else:
			frappe.throw(("You need to create your request while you're working in a shift. (between Shift-In Time and Extra-Shift Time.)")) 
	
	elif (extra_shift_timedate_obj > shift_in_timedate_obj) and (extra_shift_timedate_obj < shift_out_timedate_obj):
		frappe.throw("Extra Shift can't be between Shift in and Shift out time")
		
def get_permission_query_conditions(user):								#function to get permission query conditions (to enable to disable list view for a particular user)
	if frappe.session.user != "Administrator":			#update manager config visibility
		if not user: 
			user = frappe.session.user 			
		query = """((`tabEmployee Goodworks`.`workflow_state` = 'Draft' and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}'))
		or (`tabEmployee Goodworks`.`workflow_state` = 'Pending for Manager Approval'  and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}')) 
		or (`tabEmployee Goodworks`.`workflow_state` = 'Pending for Request Approver Approval' and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}'))
		or (`tabEmployee Goodworks`.`workflow_state` = 'Pending for HRBP Approval' and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}'))
		or (`tabEmployee Goodworks`.`workflow_state` = 'Approved' and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}'))
		or (`tabEmployee Goodworks`.`workflow_state` = 'Rejected' and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}'))
		or (`tabEmployee Goodworks`.`workflow_state` = 'Abandoned' and (`tabEmployee Goodworks`.`employee_mail` = '{0}' or `tabEmployee Goodworks`.`manager_id` = '{0}' or `tabEmployee Goodworks`.`request_approver_id` = '{0}' or `tabEmployee Goodworks`.`hrbp_id` = '{0}')))""".format(user)
		return query
	  
def has_permission(doc, user): 											#function to get permission for the link (to enable to disable url view for a particular user)	
	if not user: user = frappe.session.user
	if "Administrator" in frappe.get_roles(user): 	
		return True 	

	if user in [doc.manager_id, doc.request_approver_id, doc.hrbp_id, doc.employee_mail]:		#hide new button from js
		return True
	
	return False
	
def number_of_requests(extra_shift, user):
	req_date = datetime.strptime(extra_shift, '%Y-%m-%d %H:%M:%S')
	req_month = req_date.strftime("%m")			#month
	req_year = req_date.strftime("%Y")			#year
	req_details = frappe.db.sql("""SELECT request_status FROM `tabEmployee Goodworks` WHERE (employee_mail = '{0}' and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') = '{1}' and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y') = '{2}') ORDER BY (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%d') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y')) DESC""".format(user, req_month, req_year, as_dict=0))
	number_of_requests = 0
	number_of_approved_requests = 0
	for i in req_details:
		if i[0] == "Approved":
			number_of_approved_requests += 1
		if i[0] not in ["Rejected", "Abandoned", "Draft"]:
			number_of_requests += 1
	if number_of_approved_requests == 14 or number_of_requests == 14:
		return "last request"

	if number_of_approved_requests == 15:
		return "out of requests"

	if number_of_requests >= 15 and number_of_approved_requests == 14:
		return "wait for approval"

	if number_of_requests == 15:
		return "wait for clearance"

def compensation_amount(user, month, year):		#month(request_date) and year(request_date)
	req_details = frappe.db.sql("""SELECT COUNT(request_date) FROM `tabEmployee Goodworks` WHERE workflow_state = 'Approved' and (employee_mail = '{0}' and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') = '{1}' and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y') = '{2}') ORDER BY (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%d') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y')) DESC""".format(user, month, year, as_dict=True))
	value = eval(get_db_config('Amount'))
	amount = int(value) * req_details[0][0]
	return amount

def monthly_report(user, month, year):
	amount = compensation_amount(user, month, year)
	emp_id_and_number_of_requests = frappe.db.sql("""SELECT employee_id, COUNT(request_date) FROM `tabEmployee Goodworks` WHERE workflow_state = 'Approved' and employee_mail = '{0}' and (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') = '{1}') and (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y') = '{2}') ORDER BY (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%d') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y')) DESC;""".format(user, month, year, as_dict=True))
	occurences_for_odd_hours = frappe.db.sql("""SELECT COUNT(request_date) FROM `tabEmployee Goodworks` WHERE workflow_state = 'Approved' and employee_mail = '{0}' and (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') = '{1}') and (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y') = '{2}') and request_type = 'ODD Shift' ORDER BY (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%d') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y')) DESC;""".format(user, month, year, as_dict=True))
	occurences_for_extended_hours = frappe.db.sql("""SELECT COUNT(request_date) FROM `tabEmployee Goodworks` WHERE workflow_state = 'Approved' and employee_mail = '{0}' and (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') = '{1}') and (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y') = '{2}') and request_type = 'Extended Shift' ORDER BY (DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%d') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%m') and DATE_FORMAT(STR_TO_DATE(request_date, '%d-%m-%Y'), '%Y')) DESC;""".format(user, month, year, as_dict=True))
	return emp_id_and_number_of_requests[0][0], emp_id_and_number_of_requests[0][1], amount, occurences_for_extended_hours[0][0], occurences_for_odd_hours[0][0]

@frappe.whitelist()
def confirm_abandonment(doc , approver , reason_for_abandonment):
	data = json.loads(doc)
	name = data['name']
	record = frappe.get_doc("Employee Goodworks" , name)
	record.reason_for_abandonment = reason_for_abandonment
	record.save(ignore_permissions=True)
	frappe.db.sql("""update `tabEmployee Goodworks` set workflow_state = 'Abandoned', request_status = 'Abandoned' where name = '{0}'""".format(name))
	log_action_history('Abandoned',approver,data['name'],'Employee Overtime','Abandoned')

@frappe.whitelist()
def check_employee_eligibility(employee_level, department, employment_type):						#function to check eligibility of employee via level and department
	eligible_levels = eval(get_db_config('Eligible Levels'))		#####################################################
	eligible_department = eval(get_db_config('Eligible Department'))
	eligible_employment_type = eval(get_db_config('Eligible Employment Type'))
	if employee_level not in eligible_levels:	 	#check employee level
		return "invalid level"
		
	elif department not in eligible_department:	#check employee department
		return "invalid department"

	elif employment_type not in eligible_employment_type:	#check employee employment type
		return "invalid employment type"

@frappe.whitelist()
def employee_eligibility():		#imp
	user_id = frappe.session.user
	emp_details =  frappe.db.get_value("Employee", {"user_id":user_id},["level","department","employment_type"],as_dict=False)
	return check_employee_eligibility(emp_details[0], emp_details[1], emp_details[2])
 
@frappe.whitelist()
def get_manager_sr_manager_bo_hrbp(employee_id):
	# Derivation for pre-populating Manager , Sr Manager , BO and HRBP
	manager_list ={}
	bo = ''
	sr_manager = ''
	hrbp = ''
	reports_to = ''
	emp_level = frappe.db.get_value("Employee" ,employee_id, "level")
	level_employee = int(emp_level[1])
	reports_to_level = ''
	founder_employee_id=[]
	founders = frappe.db.get_value("Matrix Settings Property Value Details", {
									 "settings_key": "founders_employee_id"}, ["settings_value"])
	if founders:
		founder_employee_id=ast.literal_eval(founders)
	else:
		founder_employee_id.extend(['EMP-0015','EMP-0011','EMP-0012'])
	manager_details = frappe.db.sql("""
			select name , user_id ,employee_name , level from `tabEmployee` where name = (select reports_to from `tabEmployee` where name = '%s')
			"""%(employee_id),as_dict=1)
	if manager_details:
		for manager_detail in manager_details:
			manager_list["manager_id"]=manager_detail.get("user_id")
			manager_list["manager_name"]=manager_detail.get("employee_name")
			reports_to = manager_detail.get("name")
			reports_to_level = manager_detail.get('level')
	if not bo:
		bo=getBO(employee_id)
		if bo:
			manager_list["business_approver_id"] = bo
			manager_list["business_approver_name"] = frappe.db.get_value("Employee",{"user_id":bo},"employee_name")
		else:
			count = 0
			level = ''
			emp_id = employee_id
			user_id_enabled = 0
			while not bo and count < 12:
				count += 1
				business_head_details = frappe.db.sql("""
					select name,employee_name,user_id,reports_to from `tabEmployee` where name = (select reports_to from `tabEmployee` where name = '%s')
					"""%(emp_id),as_dict=1)
				if business_head_details:
					for business_head_detail in business_head_details:
						emp_id = business_head_detail.name
						if business_head_detail.reports_to in founder_employee_id: 
							user_id_enabled = frappe.get_value("User",business_head_detail.user_id,"enabled")
							if user_id_enabled == 1:
								manager_list["business_approver_name"] = business_head_detail.employee_name
								manager_list["business_approver_id"] = business_head_detail.user_id
								bo = business_head_detail.name

	if level_employee:
		if level_employee <= 5:
			# if emp_level in ('L7' , 'L7-A' , 'L7-B'):
			# 		manager_list["sr_manager_name"] = manager_list["manager_name"]
			# 		manager_list["sr_manager_id"] = manager_list["manager_id"]
			# 		sr_manager = reports_to
			# else:
				if reports_to_level in ("L5", "L6", "L6-A", "L6-B", "L7" , "L7-A" , "L7-B" ,  "L8" , "L9"):
					if manager_details: 
							manager_list["sr_manager_name"] = manager_list["manager_name"]
							manager_list["sr_manager_id"] = manager_list["manager_id"]
							sr_manager = reports_to
				
					if bo == reports_to:
						manager_list["sr_manager_name"] = manager_list["manager_name"]
						manager_list["sr_manager_id"] = manager_list["manager_id"]
						sr_manager = manager_list["sr_manager_id"]

				if not sr_manager:
					level_sr_manager= ('L5' , 'L6', 'L6-A' , 'L6-B' ,'L7', 'L7-A' , 'L7-B', 'L8' , 'L9')
					count = 0
					level = ''
					user_id_enabled = 0
					bo_name = bo
					emp_id = reports_to
					
					while not sr_manager and count < 12:
						count += 1
						sr_manager_details = frappe.db.sql("""
							select name,employee_name,user_id,level,reports_to,business_owner from `tabEmployee` where name = (select reports_to from `tabEmployee` where name = '%s')
							"""%(emp_id),as_dict=1)
						if sr_manager_details:
							for sr_manager_detail in sr_manager_details:
								emp_id = sr_manager_detail.name
								level = sr_manager_detail.level
								if sr_manager_detail.user_id and level in level_sr_manager:
									user_id_enabled = frappe.get_value("User",sr_manager_detail.user_id,"enabled")
									if user_id_enabled == 1:
										manager_list["sr_manager_name"] = sr_manager_detail.employee_name
										manager_list["sr_manager_id"] = sr_manager_detail.user_id
										sr_manager = sr_manager_detail.user_id
						
	if not hrbp :
		hrbp_id=get_hrbp(employee_id, 'Employee Overtime')
		if hrbp_id:
			manager_list["hrbp_id"] = hrbp_id
			manager_list["hrbp_name"] = frappe.db.get_value("Employee" , {"user_id":hrbp_id} , "employee_name")
	if manager_list:
		return manager_list


@frappe.whitelist()
def type_of_request(shift_in_timedate, shift_out_timedate, extra_shift_timedate):						#function to determine the type of request
	
	shift_in_datetime_obj = datetime.strptime(shift_in_timedate, '%Y-%m-%d %H:%M:%S')
	shift_out_datetime_obj = datetime.strptime(shift_out_timedate, '%Y-%m-%d %H:%M:%S')
	extra_shift_datetime_obj = datetime.strptime(extra_shift_timedate, '%Y-%m-%d %H:%M:%S')
	
	current_time = now_datetime()
	morning = current_time.replace(hour=7, minute=0, second=0, microsecond=0)
	evening = current_time.replace(hour=20, minute=0, second=0, microsecond=0)

	# EXTRA IS PRE SHIFT
	if shift_in_datetime_obj <= extra_shift_datetime_obj and extra_shift_datetime_obj <= shift_out_datetime_obj:		#correct
		return "Invalid Request", "between shift in and shift out error"

	if extra_shift_datetime_obj < shift_in_datetime_obj:
		if extra_shift_datetime_obj >= morning and extra_shift_datetime_obj <= evening:			#check inclusive
			if ((shift_in_datetime_obj - extra_shift_datetime_obj).total_seconds() / 3600) >= 3:		#more than 3 hours of overtime work in pre-shift	PRESHIFT
				return "Extended Shift",""		#correct
			else:
				#frappe.throw("You cannot request for pre-shift overtime work less than 3 hours")
				return "Invalid Request", "pre-shift error"			#correct

		elif extra_shift_datetime_obj <= morning or extra_shift_datetime_obj >= evening:		#more than 3 hours of overtime work in pre-shift	PRESHIFT
			return "ODD Shift",""
		else:
			#frappe.throw("You cannot request for pre-shift overtime work less than 3 hours")
			return "Invalid Request", "pre-shift error"	
	
	# EXTRA IS POST SHIFT

	if (extra_shift_datetime_obj > shift_in_datetime_obj) and (extra_shift_datetime_obj > shift_out_datetime_obj):
		if shift_in_datetime_obj >= morning and shift_in_datetime_obj <= evening:
			if ((extra_shift_datetime_obj - shift_out_datetime_obj).total_seconds() / 3600) >= 3:		#more than 3 hours of overtime work in post-shift	POSTSHIFT
				return "Extended Shift",""
			else:
				#frappe.throw("You cannot request for pre-shift overtime work less than 3 hours")
				return "Invalid Request", "post-shift error"	

		elif shift_in_datetime_obj <= morning or shift_in_datetime_obj >= evening:		#more than 3 hours of overtime work in post-shift	POSTSHIFT
			return "ODD Shift",""
		else:
			#frappe.throw("You cannot request for pre-shift overtime work less than 3 hours")
			return "Invalid Request", "post-shift error"	

@frappe.whitelist()
def calculate_overtime_hours(shift_in, shift_out, extra_shift):					#function to calculate overtime hours
	shift_in_datetime_obj = datetime.strptime(shift_in, '%Y-%m-%d %H:%M:%S')
	shift_out_datetime_obj = datetime.strptime(shift_out, '%Y-%m-%d %H:%M:%S')
	extra_shift_datetime_obj = datetime.strptime(extra_shift, '%Y-%m-%d %H:%M:%S')

	if extra_shift_datetime_obj < shift_in_datetime_obj:
		return ((extra_shift_datetime_obj - shift_in_datetime_obj).total_seconds() / 3600)

	else:
		return ((extra_shift_datetime_obj - shift_out_datetime_obj).total_seconds() / 3600)


@frappe.whitelist()
def calculate_total_worked_hours(shift_in, shift_out, extra_shift):			#function to calculate total worked hours
	shift_in_datetime_obj = datetime.strptime(shift_in, '%Y-%m-%d %H:%M:%S')
	shift_out_datetime_obj = datetime.strptime(shift_out, '%Y-%m-%d %H:%M:%S')
	extra_shift_datetime_obj = datetime.strptime(extra_shift, '%Y-%m-%d %H:%M:%S')

	if extra_shift_datetime_obj < shift_in_datetime_obj:
		return ((shift_out_datetime_obj - extra_shift_datetime_obj).total_seconds() / 3600)
  
	else:
		return ((extra_shift_datetime_obj - shift_in_datetime_obj).total_seconds() / 3600)

@frappe.whitelist()														#function to calculate shift out time based on shift in time
def shiftout_timedate(shift_in_timedate):
	date_time_obj = datetime.strptime(shift_in_timedate, '%Y-%m-%d %H:%M:%S')
	
	shift_out_timedate = date_time_obj + timedelta(hours = 8.5)				#claculate and set shift out time
	actual_shiftout_datetime = shift_out_timedate.strftime("%Y-%m-%d %H:%M:%S")
	return actual_shiftout_datetime

@frappe.whitelist()
def request_date(extra_shift_timedate):	
	#function to calculate and set request date
	date_time_obj = datetime.strptime(extra_shift_timedate, '%Y-%m-%d %H:%M:%S')
	request_date = date_time_obj.date()
	return request_date.strftime("%d-%m-%Y")

@frappe.whitelist()
def check_overtime_hours_visibility(shift_in_timedate):
    date_time_obj = datetime.strptime(shift_in_timedate, '%Y-%m-%d %H:%M:%S')
    now = now_datetime()
    if date_time_obj < now:
        return 'less'
    elif date_time_obj > now:
        return 'more'
    
def get_db_config(config_key):
    return frappe.get_value('Employee Goodworks Config Details',{'config_name':config_key},'config_value')
