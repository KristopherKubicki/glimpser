# Web Notifications

Glimpser can now send browser notifications while the interface is open.  
The page requests permission on load and listens to `/stream_notifications` 
using Server-Sent Events.

Send a POST request to `/send_notification` with a JSON body containing
`title` and `body` fields. Connected browsers display the message using the
standard Notification API.

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"title": "Update", "body": "Motion detected"}' \
     http://localhost:5000/send_notification
```

The feature works on desktop and mobile browsers as long as the Glimpser page
remains open or in the background.
