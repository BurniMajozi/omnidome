# Twilio Functions (Voice + SMS)

This folder contains starter Twilio Function endpoints for outbound calls and bulk SMS.

## Files

- `functions/make-call.protected.js`: place outbound calls.
- `functions/send-sms.protected.js`: send a single SMS.
- `functions/broadcast-sms.protected.js`: send SMS to multiple recipients.

## Deploy (high level)

1. Create a Twilio Serverless Service.
2. Add each file under `functions/` to the Service.
3. In the Twilio Service environment variables, set:
   - `DEFAULT_CALLER_ID` (optional, fallback for outbound calls)
   - `DEFAULT_SMS_FROM` (optional, fallback for outbound SMS)
4. Deploy the Service and note the base URL:
   - `https://<service-name>-<random>.twil.io`

## Gateway wiring

Set these in `.env` for the gateway proxy:

- `TWILIO_VOICE_FUNCTIONS_URL=https://<service-name>-<random>.twil.io`
- `TWILIO_SMS_FUNCTIONS_URL=https://<service-name>-<random>.twil.io`

Then call:

- `POST /api/voice/make-call`
- `POST /api/sms/send-sms`
- `POST /api/sms/broadcast-sms`
