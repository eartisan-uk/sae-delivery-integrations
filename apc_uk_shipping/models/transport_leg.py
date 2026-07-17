# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    to_email = fields.Char(string="Delivery Email")
    to_tel = fields.Char(string="Delivery Phone")
    to_mobile = fields.Char(string="Delivery Mobile")
    from_email = fields.Char(string="Collection Email")
    from_tel = fields.Char(string="Collection Phone")
    from_mobile = fields.Char(string="Collection Mobile")

    apc_order_number = fields.Char(
        string="APC Order Number",
        help="18-digit APC OrderNumber returned after booking.",
        copy=False,
    )
    apc_status_code = fields.Char(
        string="APC Status Code",
        help="Latest status code from APC Tracks endpoint.",
        copy=False,
    )
    apc_status_description = fields.Char(
        string="APC Status Description",
        copy=False,
    )
    apc_label_attachment_id = fields.Many2one(
        "ir.attachment",
        string="APC Label",
        copy=False,
        readonly=True,
    )

    # ====================================================================
    # Tracking poll
    # ====================================================================
    def _apc_poll_tracking(self):
        """Cron: poll APC tracking endpoint and update legs."""
        from .apc_api import ApcApiClient

        carriers = self.env["delivery.carrier"].search(
            [("delivery_type", "=", "apc")])
        if not carriers:
            return

        for carrier in carriers:
            client = ApcApiClient(carrier)
            params = {"datefrom": fields.Datetime.now(), "history": "yes"}
            while True:
                response = client.call("GET", "Tracks.json", params=params)
                for order in response.get("Track", []):
                    waybill = order.get("WayBill")
                    status_code = order.get("StatusCode")
                    status_desc = order.get("Status", "")

                    leg = self.search(
                        [("booking_ref", "=", waybill)], limit=1)
                    if leg:
                        leg.write({
                            "apc_status_code": status_code,
                            "apc_status_description": status_desc,
                        })
                        booking_state = self._apc_status_to_booking_state(
                            status_code)
                        if booking_state:
                            leg.booking_state = booking_state

                next_page = response.get("Pagination", {}).get("NextPage")
                if not next_page:
                    break
                params["page"] = next_page

    def _apc_status_to_booking_state(self, status_code):
        """Map APC status code to booking_state selection."""
        if not status_code:
            return False
        status_map = {
            "1": "booked",
            "62": "booked",
            "63": "booked",
            "70": "booked",
            "71": "booked",
            "69": "booked",
            "2": "booked",
            "3": "booked",
            "97": "none",
        }
        return status_map.get(str(status_code), False)

    def _apply_booking_result(self, result):
        """Write booking outcome + persist the label to APC-specific field.

        Overrides the core to also capture the APC ``OrderNumber`` (18-digit)
        that the adapter stashes in ``raw_response``.
        """
        self.ensure_one()
        vals = {
            "tracking_code": result.tracking_number or self.tracking_code,
            "booking_ref": result.consignment_ref or self.booking_ref,
            "booking_state": "booked",
            "booking_message": False,
        }
        # Extract OrderNumber from the raw booking response.
        raw = result.raw_response or {}
        response = raw.get("response", {}) if isinstance(raw, dict) else {}
        if isinstance(response, dict):
            orders = response.get("Orders", {})
            if isinstance(orders, list):
                orders = orders[0] if orders else {}
            order_entry = (
                orders.get("Order", orders) if isinstance(orders, dict) else {})
            if isinstance(order_entry, list):
                order_entry = order_entry[0] if order_entry else {}
            if isinstance(order_entry, dict):
                order_number = order_entry.get("OrderNumber", "") or ""
                if order_number:
                    vals["apc_order_number"] = order_number
        self.write(vals)
        if result.label:
            filename = result.label_filename or ("APC-Label-%s" % self.id)
            attachment = self._leg_store_label(filename, result.label)
            if attachment:
                self.write({"apc_label_attachment_id": attachment.id})