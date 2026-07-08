# -*- coding: utf-8 -*-

from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    transport_carrier_code = fields.Char(
        string="Transport Pricing Code",
        help="Carrier code emitted by the external transport pricing engine "
             "(e.g. 'DPD'). Maps a selected Transport Leg rate option back to "
             "this delivery method. Leave empty for carriers with no live "
             "booking integration.",
    )
    transport_booking_mode = fields.Selection(
        [
            ("manual", "Manual / No API"),
            ("api", "API Booking"),
        ],
        string="Booking Mode",
        default="manual",
        help="'API Booking' dispatches to the provider adapter selected below. "
             "'Manual / No API' means legs are booked by entering a tracking "
             "reference (e.g. SAE own fleet, Courier Exchange).",
    )
    transport_provider = fields.Selection(
        selection=[("none", "None")],
        string="Booking Provider",
        help="Which API adapter books this carrier (used when Booking Mode is "
             "'API Booking'). Provider add-ons extend this list via "
             "selection_add.",
    )
