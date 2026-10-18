// One explicitly shared tab; video goes directly between signed-in displays.
const ROOT = "/youtube-follow";
const RTC = { iceServers: [] };

export async function followRequest(path, method = "GET", body = {}) {
  const controller = new AbortController();
  let timedOut = false,
    timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      reject(new Error("Connection check timed out. Retrying…"));
      controller.abort();
    }, 6000);
  });
  const operation = (async () => {
    const response = await fetch(ROOT + path, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      ...(method === "GET"
        ? {}
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
    if (!response.ok) {
      const error = new Error(
        response.status === 401
          ? "Sign in to Glimpser on this display."
          : response.status === 429
            ? "Three displays are already connected."
            : response.status === 409
              ? "A tab is already shared. Stop it before sharing another."
              : "Connection interrupted. Retrying…",
      );
      error.status = response.status;
      throw error;
    }
    const result = await response.json();
    // A browser may ignore abort even after the server allocated a lease.
    // Release late allocations rather than consuming another display slot.
    if (timedOut && method === "POST" && /^[a-f0-9]{32}$/.test(result?.id)) {
      if (path === "/publish") forget(`/publish/${result.id}`);
      else if (path.startsWith("/connect/")) forget(`/peer/${result.id}`);
    }
    return result;
  })();
  try {
    // Abort alone is insufficient on kiosk browsers with unsettled fetch/JSON.
    return await Promise.race([operation, deadline]);
  } finally {
    clearTimeout(timer);
  }
}

export function gatherDescription(peer, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    let timer;
    const finish = () => {
      if (peer.signalingState === "closed")
        return done(new Error("Connection closed"));
      if (peer.iceGatheringState === "complete") done();
    };
    const done = (error) => {
      clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", finish);
      peer.removeEventListener("signalingstatechange", finish);
      if (error) reject(error);
      else resolve(peer.localDescription.toJSON());
    };
    peer.addEventListener("icegatheringstatechange", finish);
    peer.addEventListener("signalingstatechange", finish);
    timer = setTimeout(() => {
      // A slow secondary interface must not discard usable local candidates.
      // Negotiation is non-trickle, so send the bounded set already gathered.
      if (peer.localDescription?.sdp?.includes("a=candidate:")) done();
      else done(new Error("Local video connection timed out"));
    }, timeoutMs);
    finish();
  });
}

function forget(path) {
  if (!path) return;
  // Navigation must not wait for cleanup; abandoned sessions also expire.
  void fetch(ROOT + path, {
    method: "DELETE",
    credentials: "same-origin",
    keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }).catch(() => {});
}

export function createFollowReceiver(
  video,
  onState = () => {},
  request = followRequest,
) {
  let disposed = false,
    timer,
    peer = null,
    peerId = null,
    source = null;
  let held = false,
    blocked = false,
    previous = 0,
    changed = Date.now(),
    samples = 0,
    connectingAt = 0,
    verifiedAt = Date.now();
  let state = "";
  const report = (next) => {
    if (!disposed && next !== state) {
      state = next;
      onState(next, { picture: samples >= 2 || held, held, blocked });
    }
  };
  const reset = () => {
    peer?.close();
    peer = null;
    if (peerId) forget(`/peer/${peerId}`);
    peerId = null;
    source = null;
    held = false;
    blocked = false;
    samples = 0;
    previous = 0;
    video.pause();
    video.srcObject = null;
  };
  const play = () => {
    blocked = false;
    changed = Date.now();
    const stream = video.srcObject;
    void Promise.resolve(video.play()).catch(() => {
      if (disposed || video.srcObject !== stream || !stream) return;
      blocked = true;
      report("Tap Resume to play");
    });
  };
  const observeFrames = () => {
    const quality = video.getVideoPlaybackQuality?.();
    const progress = Number.isFinite(quality?.totalVideoFrames)
      ? quality.totalVideoFrames - (quality.droppedVideoFrames || 0)
      : video.currentTime;
    if (video.videoWidth && !video.paused && progress > previous) {
      samples++;
      changed = Date.now();
    }
    previous = progress;
  };
  const tick = async () => {
    try {
      const active = await request("/state");
      if (disposed) return;
      if (!active.source) {
        reset();
        report("Waiting for your YouTube tab");
        return;
      }
      if (source !== active.source || !peer) {
        reset();
        source = active.source;
        connectingAt = Date.now();
        report("Connecting to your shared tab…");
        const connection = new RTCPeerConnection(RTC);
        peer = connection;
        connection.addTransceiver("video", { direction: "recvonly" });
        connection.ontrack = (event) => {
          if (disposed || peer !== connection) return;
          video.srcObject = event.streams[0] || new MediaStream([event.track]);
          changed = Date.now();
          if (!held) play();
        };
        await connection.setLocalDescription(await connection.createOffer());
        const offer = await gatherDescription(connection);
        if (disposed || peer !== connection) return;
        const joined = await request(`/connect/${source}`, "POST", offer);
        if (disposed || peer !== connection) {
          forget(`/peer/${joined.id}`);
          return;
        }
        peerId = joined.id;
      }
      const connection = peer;
      const reply = await request(`/peer/${peerId}`, "POST");
      if (disposed || peer !== connection) return;
      if (reply.answer && !connection.remoteDescription)
        await connection.setRemoteDescription({
          type: "answer",
          sdp: reply.answer,
        });
      if (disposed) return;
      verifiedAt = Date.now();
      if (
        connection.connectionState === "failed" ||
        (!video.srcObject && Date.now() - connectingAt > 30000)
      )
        throw new Error("Shared tab unreachable. Retrying…");
      if (held) {
        report("Frame held · source continues");
        return;
      }
      // Autoplay needs a user gesture, not another connection negotiation.
      if (blocked) return;
      observeFrames();
      if (samples >= 2) report("Shared tab · live");
      if (video.srcObject && Date.now() - changed > 10000)
        throw new Error("Picture interrupted. Reconnecting…");
    } catch (error) {
      if (disposed) return;
      observeFrames();
      // Direct media can outlive a brief signaling outage. Keep it only while
      // frames advance and account/source verification is at most 20s old.
      if (
        (!error.status || error.status >= 500) &&
        peer?.connectionState === "connected" &&
        samples >= 2 &&
        Date.now() - verifiedAt < 20000 &&
        (held || (!blocked && Date.now() - changed < 10000))
      ) {
        report(
          held
            ? "Frame held · connection check retrying"
            : "Shared tab · connection check retrying",
        );
        return;
      }
      reset();
      report(error.message || "Connection interrupted. Retrying…");
      if (error.status === 401 || error.status === 403) {
        disposed = true;
        return;
      }
    } finally {
      if (!disposed) timer = setTimeout(tick, 2000);
    }
  };
  if (typeof RTCPeerConnection !== "function")
    report("This browser cannot receive shared video");
  else void tick();
  return {
    hold(value) {
      if (disposed || !video.srcObject || (value && samples < 2)) return;
      held = value;
      if (held) {
        video.pause();
        report("Frame held · source continues");
      } else {
        play();
        report("Resuming shared tab…");
      }
    },
    dispose() {
      disposed = true;
      clearTimeout(timer);
      reset();
    },
  };
}

// Both full-page and pinned players expose the same truthful playback controls.
export function updateFollowControls(root, button, message, playback) {
  root.classList.toggle("has-picture", playback.picture);
  button.disabled = !playback.picture && !playback.blocked;
  const resume = playback.held || playback.blocked;
  button.setAttribute("aria-pressed", String(playback.held));
  button.dataset.resume = String(resume);
  button.textContent = resume ? "Resume picture" : "Hold frame";
  root.querySelector("[data-follow-status]").textContent = message;
}

export async function startFollowPublisher(
  onState = () => {},
  request = followRequest,
  signal,
) {
  const cancelled = () => new DOMException("Sharing cancelled", "AbortError");
  if (signal?.aborted) throw cancelled();
  if (
    !globalThis.isSecureContext ||
    !navigator.mediaDevices?.getDisplayMedia ||
    typeof RTCPeerConnection !== "function"
  )
    throw new Error(
      "Open Glimpser over HTTPS in a desktop browser to share a tab.",
    );
  // Must run directly from the Share button, before any awaited network call.
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser", frameRate: 30 },
    audio: false,
    selfBrowserSurface: "exclude",
    monitorTypeSurfaces: "exclude",
    surfaceSwitching: "exclude",
  });
  // The native chooser may resolve after the operator has left this page.
  // Release that capture before registering it or connecting any receivers.
  if (signal?.aborted) {
    stream.getTracks().forEach((t) => t.stop());
    throw cancelled();
  }
  const track = stream.getVideoTracks()[0];
  if (track?.getSettings().displaySurface !== "browser") {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error(
      "Choose the YouTube browser tab, rather than a window or entire screen.",
    );
  }
  let id,
    disposed = false,
    timer,
    lastSuccess = Date.now();
  const peers = new Map();
  const stop = () => {
    if (disposed) return;
    disposed = true;
    clearTimeout(timer);
    stream.getTracks().forEach((t) => t.stop());
    peers.forEach((pc) => pc.close());
    peers.clear();
    if (id) forget(`/publish/${id}`);
    window.removeEventListener("pagehide", stop);
    signal?.removeEventListener("abort", stop);
    onState("Sharing stopped");
  };
  track.addEventListener("ended", stop, { once: true });
  signal?.addEventListener("abort", stop, { once: true });
  window.addEventListener("pagehide", stop, { once: true });
  const handle = {
    stop,
    get active() {
      return !disposed;
    },
  };
  try {
    const started = await request("/publish", "POST");
    id = started.id;
    if (disposed) {
      forget(`/publish/${id}`);
      return handle;
    }
  } catch (error) {
    stop();
    throw error;
  }
  const tick = async () => {
    try {
      const result = await request(`/publish/${id}`, "POST");
      if (disposed) return;
      lastSuccess = Date.now();
      const active = new Set(result.peers.map((row) => row.id));
      for (const [key, pc] of peers)
        if (!active.has(key)) {
          pc.close();
          peers.delete(key);
        }
      for (const row of result.peers) {
        if (disposed) return;
        if (!row.offer || peers.has(row.id)) continue;
        const pc = new RTCPeerConnection(RTC);
        peers.set(row.id, pc);
        try {
          stream.getVideoTracks().forEach((t) => pc.addTrack(t, stream));
          await pc.setRemoteDescription({ type: "offer", sdp: row.offer });
          await pc.setLocalDescription(await pc.createAnswer());
          const answer = await gatherDescription(pc);
          if (disposed) return;
          await request(`/publish/${id}/answer/${row.id}`, "POST", answer);
        } catch {
          pc.close();
          peers.delete(row.id);
        }
      }
      if (!disposed)
        onState(
          `Sharing your selected tab · ${[...peers.values()].filter((pc) => pc.connectionState === "connected").length} connected displays`,
        );
    } catch (error) {
      if (disposed) return;
      if (
        [401, 403, 404].includes(error.status) ||
        Date.now() - lastSuccess > 30000
      ) {
        stop();
        onState("Sharing stopped. Reconnect and choose your tab again.");
        return;
      }
      onState("Signaling interrupted. Retrying…");
    } finally {
      if (!disposed) timer = setTimeout(tick, 2000);
    }
  };
  void tick();
  return handle;
}

export function initFollowPage() {
  const root = document.querySelector("[data-youtube-follow]");
  if (!root) return;
  const video = root.querySelector("video");
  const share = root.querySelector("[data-follow-share]"),
    stop = root.querySelector("[data-follow-stop]");
  const sharing = root.querySelector("[data-follow-sharing]");
  const holdButton = root.querySelector("[data-follow-hold]");
  holdButton.disabled = true;
  let publisher = null,
    receiver = null,
    closed = false,
    generation = 0,
    captureController = null;
  const resetPicture = () => {
    updateFollowControls(root, holdButton, "Waiting for your YouTube tab", {
      picture: false,
      held: false,
      blocked: false,
    });
  };
  const receive = () => {
    receiver?.dispose();
    receiver = createFollowReceiver(video, (value, playback) => {
      updateFollowControls(root, holdButton, value, playback);
    });
  };
  if (!document.hidden) receive();
  share.addEventListener("click", async () => {
    const attempt = ++generation;
    captureController = new AbortController();
    share.disabled = true;
    try {
      const started = await startFollowPublisher(
        (value) => {
          if (closed || attempt !== generation) return;
          sharing.textContent = value;
          if (value.startsWith("Sharing stopped")) {
            share.disabled = false;
            stop.disabled = true;
          }
        },
        followRequest,
        captureController.signal,
      );
      if (closed || attempt !== generation) {
        started.stop();
        return;
      }
      publisher = started;
      stop.disabled = !started.active;
    } catch (error) {
      if (closed || attempt !== generation) return;
      sharing.textContent = error.message;
      share.disabled = false;
    }
  });
  stop.addEventListener("click", () => {
    publisher?.stop();
    publisher = null;
  });
  root
    .querySelector("[data-follow-hold]")
    .addEventListener("click", (event) => {
      const held = event.currentTarget.dataset.resume !== "true";
      receiver?.hold(held);
    });
  root
    .querySelector("[data-follow-fullscreen]")
    .addEventListener("click", () => {
      void root
        .querySelector(".youtube-follow-screen")
        .requestFullscreen?.()
        .catch(() => {});
    });
  const visibilityChanged = () => {
    if (document.hidden) {
      receiver?.dispose();
      receiver = null;
      resetPicture();
    } else if (!closed) receive();
  };
  document.addEventListener("visibilitychange", visibilityChanged);
  const pageShown = (event) => {
    if (!event.persisted) return;
    closed = false;
    if (!document.hidden && !receiver) receive();
  };
  const pageHidden = (event) => {
    closed = true;
    generation++;
    captureController?.abort();
    captureController = null;
    receiver?.dispose();
    receiver = null;
    publisher?.stop();
    publisher = null;
    share.disabled = false;
    stop.disabled = true;
    sharing.textContent = "Sharing stopped. Choose a tab to share again.";
    resetPicture();
    if (!event.persisted) {
      document.removeEventListener("visibilitychange", visibilityChanged);
      window.removeEventListener("pageshow", pageShown);
      window.removeEventListener("pagehide", pageHidden);
    }
  };
  window.addEventListener("pageshow", pageShown);
  window.addEventListener("pagehide", pageHidden);
}

export function initPinnedFollow() {
  const shell = document.querySelector(".landing-stage-shell");
  const controls = document.querySelector("[data-landing-review-controls]");
  const profile = shell?.dataset.landingProfile;
  if (!controls || !["office", "living"].includes(profile)) return;
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/css/youtube_follow.css?v=20261016-2";
  document.head.append(style);
  const open = document.createElement("a");
  open.href = ROOT;
  open.className = "landing-review-link";
  open.textContent = "My YouTube";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "landing-review-button";
  toggle.textContent = "Pin YouTube";
  toggle.setAttribute("aria-pressed", "false");
  controls.append(open, toggle);
  const panel = document.createElement("aside");
  panel.className = "youtube-follow-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "My YouTube pinned picture");
  panel.innerHTML =
    '<header><a href="/youtube-follow">My YouTube</a><button type="button" data-follow-close aria-label="Close pinned YouTube">Close</button></header><div class="youtube-follow-picture"><video autoplay muted playsinline aria-label="Shared YouTube tab"></video></div><header><button type="button" data-follow-hold aria-pressed="false" disabled>Hold frame</button></header><p data-follow-status role="status"></p>';
  document.body.append(panel);
  const video = panel.querySelector("video"),
    holdButton = panel.querySelector("[data-follow-hold]");
  let receiver = null,
    enabled = false,
    suspended = false;
  const key = `glimpser.youtube-follow.${profile}`;
  const start = () => {
    receiver?.dispose();
    receiver = null;
    document.body.classList.remove("has-youtube-follow");
    panel.classList.remove("has-picture");
    panel.hidden = !enabled;
    updateFollowControls(panel, holdButton, "Waiting for your YouTube tab", {
      picture: false,
      held: false,
      blocked: false,
    });
    if (!enabled || document.hidden || suspended) return;
    receiver = createFollowReceiver(video, (message, playback) => {
      updateFollowControls(panel, holdButton, message, playback);
      document.body.classList.toggle("has-youtube-follow", playback.picture);
    });
  };
  const setEnabled = (value) => {
    enabled = value;
    toggle.setAttribute("aria-pressed", String(value));
    try {
      localStorage.setItem(key, String(value));
    } catch {
      /* Session-only. */
    }
    start();
  };
  toggle.addEventListener("click", () => setEnabled(!enabled));
  holdButton.addEventListener("click", () => {
    receiver?.hold(holdButton.dataset.resume !== "true");
  });
  panel.querySelector("[data-follow-close]").addEventListener("click", () => {
    setEnabled(false);
    toggle.focus();
  });
  let stored = false;
  try {
    stored = localStorage.getItem(key) === "true";
  } catch {
    /* Session-only. */
  }
  const query = new URL(location.href);
  const requested = query.searchParams.get("youtube") === "pin";
  if (requested) {
    query.searchParams.delete("youtube");
    history.replaceState(
      history.state,
      "",
      query.pathname + query.search + query.hash,
    );
  }
  setEnabled(requested || stored);
  document.addEventListener("visibilitychange", start);
  const pageShown = (event) => {
    if (!event.persisted) return;
    suspended = false;
    // A visibility event may follow; start() always releases the old receiver.
    start();
  };
  const pageHidden = (event) => {
    suspended = true;
    start();
    if (!event.persisted) {
      panel.remove();
      style.remove();
      open.remove();
      toggle.remove();
      document.removeEventListener("visibilitychange", start);
      window.removeEventListener("pageshow", pageShown);
      window.removeEventListener("pagehide", pageHidden);
    }
  };
  window.addEventListener("pageshow", pageShown);
  window.addEventListener("pagehide", pageHidden);
}
