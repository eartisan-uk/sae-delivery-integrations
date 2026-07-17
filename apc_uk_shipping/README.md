# APC UK Shipping

Odoo 18 delivery-carrier integration for **APC Overnight** built against the
Hypaship API v3 (`https://apc-overnight.com`) with **Basic auth over HTTPS**.

## What it does

- Authenticates with your APC **email + password** credentials (Training/Live environments)
- Creates domestic shipments via `POST Orders.json` for all three order types:
  - **Goods Out**: depot → customer (collection block omitted, uses operational address)
  - **Goods In**: third-party → depot (collection block populated)
  - **Transport Order**: third-party ↔ third-party (both blocks populated)
- Enforces PUR cut-off (20:00 for next working day booking)
- Retrieves labels via `GET Orders/{waybill}.json` after 3-5s delay with retry support
- Label formats: **PDF** (testing), **ZPL** (thermal), **PNG** (image)
- Stores WayBill (booking_ref), OrderNumber, and label on the transport leg
- Posts label to picking chatter with tracking link

## Setup

1. Obtain APC Hypaship credentials for the Training environment
2. Inventory → Configuration → Delivery Methods → create/open the **APC Overnight** carrier
3. On the *APC Overnight Configuration* tab:
   - Set Environment = Training (switch to Live after testing)
   - Enter email/password
   - Pick label format (PDF for testing, ZPL for production)
   - Set default ReadyAt/ClosedAt times
4. Test with **Test Connection** button
5. Ship a delivery order; the label appears in the picking chatter

## Leg-native booking (transport_booking_core)

- Addresses come from the leg (`from_*` pickup = shipper, `to_*` drop-off = recipient)
- Service code resolved from `carrier_service_id.apc_product_code` or account rules
- Configure carrier: `Booking Mode = API Booking`, `Transport Provider = APC`

## Documents

- `apc_kb/APC_API_Integration_Guide_V3.1.2.pdf` — Official API guide
- `apc_kb/APC_API_Label_Retrieval.md` — Label retrieval documentation
- `doc/apc_uk_shipping_kb.md` — Internal integration notes