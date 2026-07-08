# -*- coding: utf-8 -*-

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..booking import TransportBookingAdapter, TransportBookingError

_logger = logging.getLogger(__name__)


class SaleTransportLeg(models.Model):
    _inherit = "sale.transport.leg"

    # Booking axis - independent of physical movement ``state``.
    booking_state = fields.Selection(
        [
            ("none", "Not Required"),
            ("pending", "Pending"),
            ("booked", "Booked"),
            ("failed", "Failed"),
        ],
        string="Booking Status",
        default="none",
        copy=False,
        tracking=False,
    )
    booking_ref = fields.Char(
        string="Booking Reference", copy=False,
        help="Carrier consignment reference (distinct from Tracking Code).",
    )
    booking_message = fields.Text(
        string="Booking Message", copy=False,
        help="Last booking error, when Booking Status is 'Failed'.",
    )

    # ------------------------------------------------------------------
    # Carrier + adapter resolution
    # ------------------------------------------------------------------
    def _leg_find_delivery_carrier(self):
        """Resolve this leg's selected pricing option to a delivery.carrier.

        The pricing engine fills the free-text ``carrier_code`` (e.g. 'DPD');
        we match it against ``delivery.carrier.transport_carrier_code``. No
        match (e.g. 'CX') returns an empty recordset.
        """
        self.ensure_one()
        code = (self.carrier_code or "").strip()
        if not code:
            return self.env["delivery.carrier"]
        return self.env["delivery.carrier"].search(
            [("transport_carrier_code", "=ilike", code)], limit=1)

    def _leg_booking_adapter(self, carrier):
        return TransportBookingAdapter.for_provider(carrier.transport_provider)

    # ------------------------------------------------------------------
    # Per-leg action (single button, tier dispatch)
    # ------------------------------------------------------------------
    def action_leg_send_to_shipper(self):
        self.ensure_one()
        if self.booking_state == "booked":
            raise UserError(_(
                "This leg is already booked. Reset the booking before "
                "re-sending."))
        if self.is_internal:
            return self._leg_mark_dispatched()
        carrier = self._leg_find_delivery_carrier()
        if carrier and carrier.transport_booking_mode == "api":
            return self._leg_book_api(carrier)
        return self._leg_mark_booked_manual()

    def _leg_book_api(self, carrier):
        adapter = self._leg_booking_adapter(carrier)
        if adapter is None:
            raise UserError(_(
                "No booking adapter is registered for provider '%s'. Install "
                "the matching provider add-on.") % (carrier.transport_provider
                                                    or ""))
        try:
            result = adapter.book(self)
        except TransportBookingError as exc:
            self.write({
                "booking_state": "failed",
                "booking_message": str(exc),
            })
            return self._leg_notify("danger", _("Booking failed: %s") % exc)
        self._apply_booking_result(result)
        return self._leg_notify("success", _("Leg booked."))

    def _apply_booking_result(self, result):
        """Write booking outcome + persist the label. Core owns this."""
        self.ensure_one()
        self.write({
            "tracking_code": result.tracking_number or self.tracking_code,
            "booking_ref": result.consignment_ref or self.booking_ref,
            "booking_state": "booked",
            "booking_message": False,
        })
        if result.label:
            filename = result.label_filename or ("label-%s.bin" % self.id)
            self._leg_store_label(filename, result.label)

    def _leg_store_label(self, filename, content):
        """Persist label bytes as an attachment on the leg (and post to the
        picking chatter when available)."""
        self.ensure_one()
        import base64
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "datas": base64.b64encode(content),
            "res_model": self._name,
            "res_id": self.id,
        })
        picking = self.picking_id
        if picking and hasattr(picking, "message_post"):
            picking.message_post(
                body=_("Shipping label for leg %s") % self.display_name,
                attachment_ids=[attachment.id],
            )
        return attachment

    def _leg_mark_dispatched(self):
        """Internal (own fleet): no API, mark booked."""
        self.ensure_one()
        self.write({"booking_state": "booked", "booking_message": False})
        return self._leg_notify("success", _("Leg marked as dispatched."))

    def _leg_mark_booked_manual(self):
        """Manual external carrier (no API): require a tracking code."""
        self.ensure_one()
        if not self.tracking_code:
            raise UserError(_(
                "Enter a Tracking Code before marking this manual leg as "
                "booked."))
        self.write({"booking_state": "booked", "booking_message": False})
        return self._leg_notify("success", _("Leg marked as booked."))

    def action_leg_reset_booking(self):
        self.ensure_one()
        self.write({
            "booking_state": "none",
            "booking_message": False,
        })
        return True

    def action_leg_cancel_booking(self):
        self.ensure_one()
        carrier = self._leg_find_delivery_carrier()
        adapter = self._leg_booking_adapter(carrier) if carrier else None
        if adapter is not None:
            try:
                adapter.cancel(self)
            except (TransportBookingError, NotImplementedError) as exc:
                raise UserError(_("Could not cancel: %s") % exc)
        self.write({"booking_state": "none", "booking_message": False})
        return self._leg_notify("success", _("Booking cancelled."))

    # ------------------------------------------------------------------
    # Tracking URL
    # ------------------------------------------------------------------
    def _leg_get_tracking_url(self):
        self.ensure_one()
        carrier = self._leg_find_delivery_carrier()
        adapter = self._leg_booking_adapter(carrier) if carrier else None
        if adapter is None:
            return ""
        return adapter.get_tracking_url(self) or ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _leg_notify(self, level, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": level,
                "title": _("Transport Booking"),
                "message": message,
                "sticky": level == "danger",
            },
        }

    # ------------------------------------------------------------------
    # picking.carrier_id primary-leg mirror (native back-compat)
    # ------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if "carrier_service_id" in vals:
            pickings = self.mapped("picking_id")
            for picking in pickings:
                picking._sync_primary_leg_carrier()
        return res
