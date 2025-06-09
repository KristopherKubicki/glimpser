# Notifications Page

Glimpser stores browser notifications in a new `notifications` table. The `/notifications` route lists recent messages with controls to mark each one as read or delete it. Entries show the timestamp, title and body.

Use `/send_notification` to queue a message for connected browsers. Every POST creates a record in the database so alerts can be reviewed later.
