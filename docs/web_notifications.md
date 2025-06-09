# Web Notifications

Glimpser can send browser notifications while the interface is open or closed.
When first visiting the site the browser asks for permission and registers a
Service Worker. The worker subscribes to push messages which the server stores
via the `/register_push` route. Older browsers that lack push support continue
to receive updates over `/stream_notifications` using Server-Sent Events.

Send a POST request to `/send_notification` with a JSON body containing
`title` and `body` fields. Connected browsers display the message using the
standard Notification API.

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"title": "Update", "body": "Motion detected"}' \
     http://localhost:5000/send_notification
```

The feature works on desktop and mobile browsers. Push notifications appear even
when the page is closed. To remove a subscription send a POST request to
`/unregister_push` with the same subscription object.
