# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Autor:Kevin Kong (kfx2007@163.com)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import fields,_,api,models
from datetime import datetime,date
from openerp.exceptions import except_orm

class fatung_tax_type(models.Model):
	_name="fatung.tax.type"

	name = fields.Char('Name')
	dedution = fields.Boolean('Dedution')
	valid_days = fields.Integer('Valid Days')
	desc = fields.Text('Description')
	validated = fields.Boolean('Validated')
	is_default = fields.Boolean('Default')
	date = fields.Datetime('Update DateTime',readonly=True)
	operator = fields.Many2one('res.users',readonly=True)

	_defaults={
		"date":datetime.now(),
	}

	@api.model 
	def create(self,val):
		val['operator'] = self.env.user.id
		return super(fatung_tax_type,self).create(val)

	@api.multi 
	def write(self,val):
		val['operator'] = self.env.user.id
		val['date'] = datetime.now()
		return super(fatung_tax_type,self).write(val)


class fatung_invoice(models.Model):
	_name="fatung.invoice"

	state = fields.Selection(string='Status',selection=[('draft','Draft'),('confirm','Confirm'),('certified','Certified')])
	invoice_no = fields.Char('Invoice No',required=True,readonly=True,states={'draft':[('readonly',False)]})
	invoice_type = fields.Many2one('fatung.tax.type','Tax Type',readonly=True,states={'draft':[('readonly',False)]})
	date = fields.Date('Date',readonly=True,states={'draft':[('readonly',False)]})
	invoice_title = fields.Many2one('res.partner','Invoice Title',required=True,readonly=True,states={'draft':[('readonly',False)]},domain=[('supplier','=',True)])
	invoice_author = fields.Many2one('res.partner','Invoice Author',readonly=True,states={'draft':[('readonly',False)]})
	invoice_amount = fields.Float('Invoice Amount',readonly=True,states={'draft':[('readonly',False)]})
	invoice_tax = fields.Float('Invoice Tax',readonly=True,states={'draft':[('readonly',False)]})
	reg_type = fields.Selection(selection=[('a','A'),('b','B')],string='Register Type',readonly=True,states={'draft':[('readonly',False)]})
	op_type = fields.Selection(selection=[('re','receive')],string="Operator Type",readonly=True,states={'draft':[('readonly',False)]})
	partner = fields.Many2one('res.partner','Partner',readonly=True,states={'draft':[('readonly',False)]},domain=[('supplier','=',True)])
	related_attribute = fields.Selection(selection=[('related','Related'),('unrelated','Unrelated')],string='Related',readonly=True,states={'draft':[('readonly',False)]})
	related_amount = fields.Float('Related Amount',readonly=True,states={'draft':[('readonly',False)]})
	related_tax = fields.Float('Related Tax',readonly=True,states={'draft':[('readonly',False)]})
	authorize_date = fields.Date('Authorized Date',readonly=True)
	authorized_user = fields.Many2one('res.users',"Authorized User",readonly=True)
	register_user = fields.Many2one('res.users',"Register User",readonly=True)
	invoice_line = fields.One2many('fatung.invoice.line','f_invoice_id',string="Line",readonly=True,states={'draft':[('readonly',False)]})
	invoice_tax = fields.Float('Tax Amount',readonly=True)	
	voucher = fields.Many2one('account.voucher','Ref Payments',readonly=True)
	

	_defaults={
		"state":"draft",
		"date":date.today(),
		"op_type":"re",
		"authorize_date":date.today(),
		"related_attribute":"related",
	}

	@api.onchange('invoice_title')
	def _onchange_invoice_title(self):
		if self.related_attribute=="related":
			self.partner = self.invoice_title

	@api.one
	def _check_no(self):
		inv = self.env['fatung.invoice'].search([('invoice_no','=',self.invoice_no)])
		if len(inv):
			raise except_orm(_('Warning'),_('Invoice No duplicated!'))

	@api.one
	def btn_inv(self):
		if not len(self.invoice_line):
			invos = self.env['account.invoice'].search(
				[('state','!=','draft'),('state','!=','cancel'),('type','=','in_invoice'),
				('partner_id','=',self.partner.id)
			])
			if len(invos):
				res=[]
				amount =0
				for inv in invos:
					if inv.f_unrelated_amount>0 or inv.f_unrelated_amount==-1:
						if amount<self.related_amount:
							amount +=inv.amount_untaxed
							self.invoice_tax +=inv.amount_tax
							res.append(inv)
				if len(res):	
					res.sort(key=lambda x:x.date_invoice)
					total = self.related_amount
					for r in res:
						for line in r.invoice_line:
							if line.uamount==-1:
								line.uamount=line.price_subtotal
							related_amount =0
							if line.uamount>total:
								related_amount = total
								total -= related_amount
							else:
								related_amount = line.uamount								
								total -= related_amount

							if related_amount:
								self.invoice_line.create({
									'invoice_id':r.id,
									'f_invoice_id':self.id,
									'partner':r.partner_id.id,
									'product':line.product_id.id,
									'quantity':line.quantity,
									'unit_price':line.price_unit,
									'invoice_date':r.date_invoice,
									'principal':r.user_id.name,
									'origin':r.origin,
									'amount':line.price_subtotal,
									'line_id':line.id,
									'related_amount':related_amount,
									})
	@api.one
	def btn_post(self):
		#check if line amount and tax is correct.
		amount =0 
		for line in self.invoice_line:
			amount += line.related_amount

		if amount<self.related_amount:
			raise except_orm(_('Warning'),_('Untaxed amount does not equal to Related Amount!'))

		if self.invoice_tax != self.related_tax:
			raise except_orm(_('Warning'),_('Invoice Tax does not equal to Related Tax!'))

		#create account move.
		if self.related_attribute=='unrelated':
			journal = self.env['account.journal'].search([('type','=','bank')])
			account_move_obj = self.env['account.move']
			account_move_line_obj = self.env['account.move.line']
			move = account_move_obj.create({
				"journal_id":journal[0].id,
				"type":"purchase",
				"ref":self.invoice_no+ u"非关联",
				})

			f1 = self.env['account.account'].search([('code','=','F1')])
			f2 = self.env['account.account'].search([('code','=','F2')])
			f3 = self.env['account.account'].search([('code','=','F3')])

			account_move_line_obj.create({
				"name":self.invoice_no,
				"account_id":f1.id,
				"credit":self.invoice_amount,
				"move_id":move.id,
				})

			account_move_line_obj.create({
				"name":self.invoice_no,
				"account_id":f2.id,
				"credit":self.invoice_tax,
				"move_id":move.id,
				})

			account_move_line_obj.create({
				"name":self.invoice_no,
				"account_id":f3.id,
				"debit":self.invoice_amount+self.invoice_tax,
				"move_id":move.id,
				})
		else:
			remain = self.related_amount
			for line in self.invoice_line:
				if line.line_id.uamount==-1:
					line.line_id.uamount = line.line_id.price_subtotal

				if line.line_id.ref_no:
					line.line_id.ref_no +=self.invoice_no
				else:
					line.line_id.ref_no = self.invoice_no

				remain -=line.line_id.uamount
				if remain<0:
					line.line_id.uamount =-remain
					line.unrelated = -remain	
				else:
					line.line_id.uamount =0

			self.invoice_amount = self.related_amount
			self.invoice_tax = self.related_tax

		self.register_user = self.env.user
		self.state='confirm'

	@api.one
	def btn_cer(self):
		self.authorize_date = datetime.now()
		self.authorized_user = self.env.user
		self.state = "certified"

	@api.model
	def create(self,val):
		if val.get('invoice_no'):
			inv = self.env['fatung.invoice'].search([('invoice_no','=',val['invoice_no'])])
			if len(inv):
				raise except_orm(_('Warning'),_('Invoice No duplicated!'))
		return super(fatung_invoice,self).create(val)

	@api.multi
	def write(self,val):
		if val.get('invoice_no'):
			inv = self.env['fatung.invoice'].search([('invoice_no','=',val['invoice_no'])])
			if len(inv):
				raise except_orm(_('Warning'),_('Invoice No duplicated!'))
		return super(fatung_invoice,self).write(val)

	@api.one
	def btn_pay(self):
		if not self.voucher:
			voucher_obj = self.env["account.voucher"]
			account = self.env['account.account'].search([('code','=','F1')])
			journal = self.env['account.journal'].search([('type','=','bank')])
			v = voucher_obj.create({
				"partner_id":self.invoice_title.id,
				"journal_id":journal[0].id,
				"account_id":account.id,
				"total":self.invoice_amount+self.invoice_tax,
				"reference":self.invoice_no,
				"type":"payment",
				})

	@api.multi
	def btn_view_pay(self):

		ir_model_data = self.env['ir.model.data']
		action_object = self.env['ir.actions.act_window']

		result = action_object.for_xml_id('account_voucher','action_vendor_payment')
		view_id = ir_model_data.xmlid_to_res_id('account_voucher.view_vendor_payment_form')
		result['views']=[(view_id or view_id[1] or False,'form')]

		voucher = self.env['account.voucher'].search([('reference','=',self.invoice_no)])
		result['res_id'] = voucher[0].id or False

		return result


class fatung_invoice_line(models.Model):
	_name='fatung.invoice.line'

	f_invoice_id = fields.Many2one('fatung.invoice','F_Inovice')
	invoice_id = fields.Many2one('account.invoice','Invoice',domain=[
		('state','!=','draft'),('state','!=','cancel'),('type','=','in_invoice')
		])
	line_id = fields.Many2one('account.invoice.line','Invoice Line')
	partner = fields.Many2one('res.partner','Partner')
	product = fields.Many2one('product.product')
	invoice_date = fields.Date('Invoice Date')
	quantity = fields.Float('Quantity')
	unit_price = fields.Float('Unit Price')
	principal = fields.Char('Principal')
	due_date = fields.Date('Due Date')
	origin = fields.Char('Origin')
	amount = fields.Float('Amount')
	related_amount = fields.Float('Related Amount')
	uamount = fields.Float('Uamount')

	@api.one
	@api.onchange('invoice_id')
	def _onchange_invoice_id(self):
		self.partner = self.invoice_id.partner_id
		self.invoice_date = self.invoice_id.date_invoice
		self.due_date = self.invoice_id.date_due
		self.principal = self.invoice_id.user_id.name
		self.origin = self.invoice_id.origin
		self.amount = self.invoice_id.amount_untaxed


class account_invoice(models.Model):
	_inherit="account.invoice"

	f_unrelated_amount = fields.Float('Related Amount',compute="_get_uamount")


	_defaults={
		"f_unrelated_amount":-1,
	}

	@api.one
	def _get_uamount(self):
		for line in self.invoice_line:
			self.f_unrelated_amount+=line.uamount


class account_invoice_line(models.Model):
	_inherit="account.invoice.line"

	ref_no = fields.Char('Ref No')
	uamount = fields.Float('Unrelated Amount')

	_defaults={
		'uamount':-1,
	}

class fatung_out_invoice(models.Model):
	_name="fatung.out.invoice"

	invoice_no = fields.Char('Invoice No',required=True,readonly=True,states={'draft':[('readonly',False)]})
	invoice_type = fields.Many2one('fatung.tax.type','Tax Type',readonly=True,states={'draft':[('readonly',False)]})
	date = fields.Date('Date',readonly=True,states={'draft':[('readonly',False)]})
	invoice_title = fields.Many2one('res.partner','Invoice Title',readonly=True,states={'draft':[('readonly',False)]},domain=[('customer','=',True)],required=True)
	invoice_author = fields.Many2one('res.partner','Invoice Author',readonly=True,states={'draft':[('readonly',False)]})
	invoice_amount = fields.Float('Invoice Amount',readonly=True,states={'draft':[('readonly',False)]})
	invoice_tax = fields.Float('Invoice Tax',readonly=True,states={'draft':[('readonly',False)]})
	reg_type = fields.Selection(selection=[('a','A'),('b','B')],string='Register Type',readonly=True,states={'draft':[('readonly',False)]})
	op_type = fields.Selection(selection=[('se','send')],string="Operator Type",readonly=True,states={'draft':[('readonly',False)]})
	partner = fields.Many2one('res.partner','Partner',readonly=True,states={'draft':[('readonly',False)]},domain=[('customer','=',True)])
	related_attribute = fields.Selection(selection=[('related','Related'),('unrelated','Unrelated')],string='Related',readonly=True,states={'draft':[('readonly',False)]})
	related_amount = fields.Float('Related Amount',readonly=True,states={'draft':[('readonly',False)]})
	related_tax = fields.Float('Related Tax',readonly=True,states={'draft':[('readonly',False)]})
	#authorize_date = fields.Date('Authorized Date')
	#authorized_user = fields.Many2one('res.users',"Authorized User")
	register_user = fields.Many2one('res.users',"Register User",readonly=True)
	invoice_line = fields.One2many('fatung.out.invoice.line','f_invoice_id',string="Line",readonly=True,states={'draft':[('readonly',False)]})
	state = fields.Selection(selection=[('draft','Draft'),('confirm','Confirm'),('paid','Paid')])
	voucher = fields.Many2one('account.voucher','Ref Payments',readonly=True)

	_defaults={
		"state":"draft",
		"date":date.today(),
		"op_type":"se",
		"related_attribute":"related",
	}

	@api.one
	def btn_inv(self):
		if not len(self.invoice_line):
			invos = self.env['account.invoice'].search([
				('state','!=','draft'),('state','!=','cancel'),('type','=','out_invoice'),('partner_id','=',self.partner.id)
				])
			if len(invos):
				invos.sorted(key=lambda x:x.date_invoice)
				res=[]
				amount =0
				for inv in invos:
					if inv.f_unrelated_amount>0 or inv.f_unrelated_amount==-1:
						if amount<self.related_amount:
							amount +=inv.amount_untaxed
							self.invoice_tax +=inv.amount_tax
							res.append(inv)
				if len(res):	
					res.sort(key=lambda x:x.date_invoice)
					total = self.related_amount
					for r in res:
						for line in r.invoice_line:
							if line.uamount==-1:
								line.uamount=line.price_subtotal
							related_amount =0
							if line.uamount>total:
								related_amount = total
								total -= related_amount
							else:
								related_amount = line.uamount								
								total -= related_amount

							if related_amount:
								self.invoice_line.create({
									'invoice_id':r.id,
									'f_invoice_id':self.id,
									'partner':r.partner_id.id,
									'product':line.product_id.id,
									'quantity':line.quantity,
									'unit_price':line.price_unit,
									'invoice_date':r.date_invoice,
									'principal':r.user_id.name,
									'origin':r.origin,
									'amount':line.price_subtotal,
									'line_id':line.id,
									'related_amount':related_amount,
									})

	@api.model
	def create(self,val):
		if val.get('invoice_no'):
			inv = self.env['fatung.invoice'].search([('invoice_no','=',val['invoice_no'])])
			if len(inv):
				raise except_orm(_('Warning'),_('Invoice No duplicated!'))
		return super(fatung_out_invoice,self).create(val)

	@api.multi
	def write(self,val):
		if val.get('invoice_no'):
			inv = self.env['fatung.invoice'].search([('invoice_no','=',val['invoice_no'])])
			if len(inv):
				raise except_orm(_('Warning'),_('Invoice No duplicated!'))
		return super(fatung_out_invoice,self).write(val)


	@api.onchange('invoice_title')
	def _onchange_invoice_title(self):
		if self.related_attribute=="related":
			self.partner = self.invoice_title

	@api.one
	def btn_post(self):
		#check if line amount and tax is correct.
		amount =0 
		for line in self.invoice_line:
			amount += line.amount

		if amount<self.related_amount:
			raise except_orm(_('Warning'),_('Untaxed amount does not equal to Related Amount!'))

		if self.invoice_tax != self.related_tax:
			raise except_orm(_('Warning'),_('Invoice Tax does not equal to Related Tax!'))

		#create account move.
		if self.related_attribute=='unrelated':
			journal = self.env['account.journal'].search()
			account_move_obj = self.env['account.move']
			account_move_line_obj = self.env['account.move.line']
			move = account_move_obj.create({
				"journal_id":journal[0].id,
				"type":"purchase",
				"ref":self.invoice_no+ u"非关联",
				})

			f1 = self.env['account.account'].search([('code','=','F1')])
			f2 = self.env['account.account'].search([('code','=','F2')])
			f3 = self.env['account.account'].search([('code','=','F3')])

			account_move_line_obj.create({
				"name":self.invoice_no,
				"account_id":f1.id,
				"debit":self.invoice_amount,
				"move_id":move.id,
				})

			account_move_line_obj.create({
				"name":self.invoice_no,
				"account_id":f2.id,
				"debit":self.invoice_tax,
				"move_id":move.id,
				})

			account_move_line_obj.create({
				"name":self.invoice_no,
				"account_id":f3.id,
				"credit":self.invoice_amount+self.invoice_tax,
				"move_id":move.id,
				})

		else:
			remain = self.related_amount
			for line in self.invoice_line:
				if line.line_id.uamount==-1:
					line.line_id.uamount = line.line_id.price_subtotal

				if line.line_id.ref_no:
					line.line_id.ref_no +=self.invoice_no
				else:
					line.line_id.ref_no = self.invoice_no

				remain -=line.line_id.uamount
				if remain<0:
					line.line_id.uamount =-remain
					line.unrelated = -remain	
				else:
					line.line_id.uamount =0

			self.invoice_amount = self.related_amount
			self.invoice_tax = self.related_tax
		
		self.register_user = self.env.user
		self.state='confirm'

	@api.one
	def btn_pay(self):
		if self.related_attribute=='related':
			raise except_orm(_('Warning'),_("There's no need to pay a related invoice"))

		if not self.voucher:
			voucher_obj = self.env["account.voucher"]
			account = self.env['account.account'].search([('code','=','F1')])
			journal = self.env['account.journal'].search([('type','=','bank')])
			v = voucher_obj.create({
				"partner_id":self.invoice_title.id,
				"journal_id":journal[0].id,
				"account_id":account.id,
				"total":self.invoice_amount+self.invoice_tax,
				"reference":self.invoice_no,
				"type":"receipt",
				})
			if v:
				self.state='paid'

	@api.multi
	def btn_view_pay(self):

		ir_model_data = self.env['ir.model.data']
		action_object = self.env['ir.actions.act_window'] 

		result = action_object.for_xml_id('account_voucher','action_vendor_receipt')
		view_id = ir_model_data.xmlid_to_res_id('account_voucher.view_vendor_receipt_form')
		result['views']=[(view_id or view_id[1] or False,'form')]

		voucher = self.env['account.voucher'].search([('reference','=',self.invoice_no)])
		result['res_id'] = voucher[0].id or False
		
		return result


class fatung_out_invoice_line(models.Model):
	_name="fatung.out.invoice.line"

	f_invoice_id = fields.Many2one('fatung.out.invoice','F_Inovice')
	invoice_id = fields.Many2one('account.invoice','Invoice',domain=[
		('state','!=','draft'),('state','!=','cancel'),('type','=','out_invoice')
		])
	line_id = fields.Many2one('account.invoice.line','Invoice Line')
	partner = fields.Many2one('res.partner','Partner')
	product = fields.Many2one('product.product')
	invoice_date = fields.Date('Invoice Date')
	quantity = fields.Float('Quantity')
	unit_price = fields.Float('Unit Price')
	principal = fields.Char('Principal')
	due_date = fields.Date('Due Date')
	origin = fields.Char('Origin')
	related_amount = fields.Float('Related Amount')
	amount = fields.Float('Amount')

	@api.one
	@api.onchange('invoice_id')
	def _onchange_invoice_id(self):
		self.partner = self.invoice_id.partner_id
		self.invoice_date = self.invoice_id.date_invoice
		self.due_date = self.invoice_id.date_due
		self.principal = self.invoice_id.user_id.name
		self.origin = self.invoice_id.origin
		self.amount = self.invoice_id.amount_untaxed

class fatung_report(models.Model):
	_name="fatung.report"

	period = fields.Many2one('account.period',string='period',required=True)
	send_amount = fields.Float(string='Out Amount',compute='_get_out_amount')
	send_tax = fields.Float(string='Out Tax',compute='_get_out_amount')
	recieve_tax = fields.Float(string='In Tax',compute='_get_in_tax')
	certified_tax = fields.Float(string='Certified Tax',compute='_get_certified_tax')
	vat = fields.Float('VAT')
	input_tax = fields.Float('Input Tax')
	other_input = fields.Float('Other Input')
	taxable = fields.Float('Taxable Amount',compute="_get_taxable")
	tax_bearing = fields.Float('Tax Bearing',compute="_get_tax_bearing")
	desc = fields.Text('Desc')
	maintance_date = fields.Datetime('Maintance Date')

	_defaults={
		"input_tax":0,
		"other_input":0,
		"vat":0,
	}

	@api.onchange('period')
	def _onchange_period(self):
		self._get_out_amount()
		self._get_in_tax()
		self._get_taxable()
		self._get_tax_bearing()
		self._get_certified_tax()

	@api.one
	def _get_out_amount(self):
		invs = self.env['fatung.out.invoice'].search([('date','>=',self.period.date_start),('date','<',self.period.date_stop),('state','!=','draft')])
		print invs
		if len(invs):
			for inv in invs:
				self.send_amount += inv.invoice_amount
				self.send_tax += inv.invoice_tax

	@api.one
	def _get_in_tax(self):
		invs = self.env['fatung.invoice'].search([('date','>=',self.period.date_start),('date','<',self.period.date_stop),('state','!=','draft')])
		if len(invs):
			for inv in invs:
				self.recieve_tax += inv.invoice_tax

	@api.one
	def _get_certified_tax(self):
		invs = self.env['fatung.invoice'].search([('date','>=',self.period.date_start),('date','<',self.period.date_stop),('state','=','certified')])
		if len(invs):
			for inv in invs:
				self.recieve_tax += inv.invoice_tax

	@api.one
	def _get_taxable(self):
		if self.send_amount>0:
			self.taxable = self.send_tax+self.vat+self.input_tax-self.recieve_tax-self.other_input

	@api.one
	def _get_tax_bearing(self):
		if self.send_amount>0:
			self.tax_bearing = self.taxable / self.send_amount
