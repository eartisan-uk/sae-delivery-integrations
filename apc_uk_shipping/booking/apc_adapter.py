# -*- coding: utf-8 -*-

import base64
import logging

from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

from odoo.addons.transport_booking_core.booking import (
    BookingResult,
    TransportBookingAdapter,
    TransportBookingError,
    register_adapter,
)

from ..models.apc_api import ApcApiClient


@register_adapter
class ApcAdapter(TransportBookingAdapter):
    """APC Overnight booking adapter for the transport_booking_core framework."""

    provider_code = "apc"

    def _carrier(self, leg):
        carrier = leg._leg_find_delivery_carrier()
        if not carrier or carrier.delivery_type != "apc":
            raise TransportBookingError(
                "This leg does not resolve to an APC Overnight carrier.")
        return carrier

    def book(self, leg):
        carrier = self._carrier(leg)
        try:
            data = carrier._apc_book_leg(leg)
        except (UserError, ValidationError) as exc:
            raise TransportBookingError(
                exc.args[0] if exc.args else str(exc)) from exc

        response = data.get("response", {})
        _logger.info("APC booking response: %s", response)

        # Parse WayBill - APC v3 response structure: {"Orders": {"Order": {"WayBill": "..."}}}
        waybill = ""
        orders = response.get("Orders", {})
        if isinstance(orders, list):
            orders = orders[0] if orders else {}
        order_entry = orders.get("Order", orders) if isinstance(orders, dict) else {}
        if isinstance(order_entry, dict):
            waybill = order_entry.get("WayBill", "") or ""

        _logger.info("APC parsed waybill: '%s'", waybill)

        # Wait 3-5s then fetch label (KB p.34)
        import time
        time.sleep(3)

        label_bytes = None
        label_filename = f"APC-Label-{waybill}.pdf" if waybill else "label.pdf"

        if waybill:
            client = ApcApiClient(carrier)
            try:
                label_resp = client.call(
                    "GET", f"Orders/{waybill}.json",
                    params={"searchtype": "CarrierWaybill",
                            "labelformat": carrier.apc_label_format or "PDF",
                            "labels": "True"})
                _logger.info("APC label response for %s: %s", waybill, label_resp)
                labels = label_resp.get("Labels", {})
                if isinstance(labels, dict):
                    labels = [labels]
                for lbl in labels:
                    if lbl.get("WayBill") == waybill:
                        b64 = lbl.get("Content", "")
                        if b64:
                            label_bytes = base64.b64decode(b64)
                        break
                _logger.info("APC label fetched: %s bytes", len(label_bytes) if label_bytes else 0)
            except Exception as exc:
                _logger.warning("APC label fetch failed for %s: %s", waybill, exc)

        return BookingResult(
            tracking_number=waybill,
            consignment_ref=waybill,
            label=label_bytes,
            label_filename=label_filename,
            raw_response=data,
        )

    def cancel(self, leg):
        carrier = self._carrier(leg)
        waybill = leg.booking_ref
        if not waybill:
            raise TransportBookingError("No booking reference on this leg.")
        client = ApcApiClient(carrier)
        try:
            client.call(
                "PUT", f"Orders/{waybill}.json",
                params={"searchtype": "CarrierWaybill"},
                payload={"CancelOrder": {"Order": {"Status": "CANCELLED"}}}
            )
        except ValidationError as exc:
            raise TransportBookingError(str(exc)) from exc
        return True

    def get_tracking_url(self, leg):
        reference = leg.tracking_code or leg.booking_ref or ""
        return f"https://www.apc-overnight.com/track?trackingNumber={reference}"