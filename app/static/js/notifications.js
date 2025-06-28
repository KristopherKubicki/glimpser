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

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.ready
      .then((reg) =>
        reg.pushManager.getSubscription().then((sub) => {
          if (sub) return null;
          return reg.pushManager
            .subscribe({
              userVisibleOnly: true,
              applicationServerKey: window.VAPID_PUBLIC_KEY,
            })
            .then((subscription) =>
              fetch("/register_push", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(subscription),
              }),
            );
        }),
      )
      .catch(console.error);
  }
}
