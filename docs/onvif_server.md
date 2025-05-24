# ONVIF Server

Glimpser can expose a minimal ONVIF compatible device. When enabled, the
application responds to WS-Discovery probes and provides a very small HTTP
service that supports the `GetCapabilities` request and a simple event
subscription endpoint.

## Configuration

Set the following options either in the settings database or as environment
variables before starting Glimpser:

- `ONVIF_ENABLE` – set to `True` to start the server.
- `ONVIF_PORT` – HTTP port for the device service (default `50080`).

The UDP discovery service always listens on port `3702` on the configured host.

## Usage

When the server is running, ONVIF clients on the same machine can discover it via
WS‑Discovery. Subscribing to `http://<host>:<port>/onvif/event_service` will
receive motion events whenever Glimpser detects movement.

## Integration

Point your ONVIF compatible software at the reported XAddr from discovery. Only
the basic capabilities are implemented so not all clients may work, but most can
subscribe to motion events.
