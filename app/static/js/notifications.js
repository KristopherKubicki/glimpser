export function initNotifications() {
  if (!("Notification" in window)) return;

  if (Notification.permission === "default") {
    Notification.requestPermission().catch(console.error);
  }

  const source = new EventSource("/stream_notifications");
  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (Notification.permission === "granted") {
        new Notification(data.title, { body: data.body });
      }
    } catch (err) {
      console.error("Failed to parse notification", err);
    }
  };
}
