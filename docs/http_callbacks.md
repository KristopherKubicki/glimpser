# HTTP Callback Guide

Glimpser can notify external services when motion is detected or when a
new caption is generated. This is handled by the `send_http_callback`
function in `app/utils/http_callbacks.py`.

## How Callbacks Work

Whenever a template has a `callback_url` defined, Glimpser sends an HTTP
`POST` request to that URL. The request body is JSON with two fields:

- `event` – either `"caption"` or `"motion"`
- `payload` – a dictionary containing details about the event

The relevant code is shown below:

```python
# app/utils/http_callbacks.py
send_http_callback(
    url,
    event_type,
    payload,
    *,
    timeout=5,
    headers=None,
    retries=0,
)
```

Scheduling tasks assemble the payload and call this function whenever an
image is processed or motion is detected.

Example payload from `app/utils/scheduling.py`:

```python
payload = {
    "name": name,
    "caption": template.get("last_caption"),
    "timestamp": lctime,
    "motion": bool(lsum),
}
send_http_callback(template.get("callback_url"), event, payload)
```

You can override the timeout, provide headers, and enable retries:

```python
send_http_callback(
    template.get("callback_url"),
    event,
    payload,
    timeout=10,
    headers={"Authorization": "Bearer TOKEN"},
    retries=2,
)
```

## Configuring a Callback URL

1. Open the Glimpser web interface and edit a template.
2. Enter the destination URL in the **Callback URL** field.
3. Save the template. Glimpser will begin posting events to that URL.

You can also set `callback_url` directly in the settings database if you
manage templates programmatically.

## Example JSON Payload

A caption event might look like this:

```json
{
  "event": "caption",
  "payload": {
    "name": "front_door",
    "caption": "No activity detected",
    "timestamp": "2024-08-30 12:00:00",
    "motion": false
  }
}
```

Use this structure to integrate Glimpser with home automation systems,
webhooks, or other services.
