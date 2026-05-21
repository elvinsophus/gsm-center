# Multipart SMS Handling

GSM networks may deliver a long SMS as multiple concatenated parts. Parts can
arrive out of order, and the listener process may restart between parts, so
gsm-center treats each part as durable input instead of relying on process
memory.

## Metadata

Multipart SMS metadata is read from the SMS user data header when available.
Both 8-bit and 16-bit concatenation references are supported:

- IEI `0x00`: 8-bit reference, total parts, sequence number
- IEI `0x08`: 16-bit reference, total parts, sequence number

If the modem library exposes equivalent parsed attributes instead of raw UDH,
gsm-center also accepts those attributes.

## Storage

Single-part inbound SMS messages are inserted directly into `sms`.

Multipart inbound SMS parts are inserted into `received_sms_part`, keyed by:

- own number
- sender
- concatenation reference
- sequence number

The unique key makes repeated delivery of the same part idempotent. Once all
sequences from `1..total` are present, gsm-center joins the part content in
sequence order, inserts one final received row into `sms`, and marks the source
parts as assembled.

## Restarts

On loop startup, each `GSMCenter` asks its store to assemble any complete
multipart groups already present in SQLite for that own number. This covers the
case where some parts arrived before a supervisor restart and the remaining
parts arrive later.

The SMS received hook runs only for the completed message, not for individual
parts.
