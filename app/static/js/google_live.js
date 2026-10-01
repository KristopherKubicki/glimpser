// Google SDM uses audio/video/data-channel offers, even for muted viewing.
export function normalizeGoogleAnswer(sdp) {
  return (
    sdp
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .split("\n")
      .flatMap((raw) => {
        const line = raw.trim();
        if (!line) return [];
        if (line === "a=sendrecv") return ["a=sendonly"];
        const app = line.match(/^m=application\s+(\d+)\s+DTLS\/SCTP\s+\d+/i);
        if (app)
          return [`m=application ${app[1]} UDP/DTLS/SCTP webrtc-datachannel`];
        const sctp = line.match(/^a=sctpmap:(\d+)\s+\S+(?:\s+(\d+))?/i);
        if (sctp)
          return [
            `a=sctp-port:${sctp[1]}`,
            ...(sctp[2] ? [`a=max-message-size:${sctp[2]}`] : []),
          ];
        return [line];
      })
      .join("\r\n") + "\r\n"
  );
}

export function connectGoogleLive(video, camera, onError) {
  let disposed = false,
    peer = null,
    config = null,
    session = "",
    iceTimer = null,
    finishIce = null;
  const post = async (action, body, keepalive = false) => {
    const response = await fetch(
      `/integrations/google/webrtc/${action}?token=${encodeURIComponent(config.token)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...config, ...body }),
        keepalive,
      },
    );
    const data = await response.json();
    if (!response.ok || !data.ok)
      throw new Error("Google live session unavailable");
    return data;
  };
  const stopRemote = () => {
    if (!session || !config) return;
    const id = session;
    session = "";
    void post("stop", { media_session_id: id }, true).catch(() => {});
  };
  const dispose = () => {
    disposed = true;
    finishIce?.();
    clearTimeout(iceTimer);
    peer?.close();
    peer = null;
    video.srcObject?.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
    stopRemote();
  };
  const start = async () => {
    if (typeof RTCPeerConnection !== "function")
      throw new Error("WebRTC unavailable");
    const response = await fetch(
      `/kiosk_live_config?camera=${encodeURIComponent(camera)}`,
      { cache: "no-store" },
    );
    if (!response.ok) throw new Error("Google live unavailable");
    config = await response.json();
    if (disposed) return;
    peer = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });
    const activePeer = peer;
    peer.addTransceiver("audio", { direction: "recvonly" });
    peer.addTransceiver("video", { direction: "recvonly" });
    peer.createDataChannel("glimpser");
    peer.ontrack = (event) => {
      if (disposed) return;
      if (event.streams?.[0] && video.srcObject !== event.streams[0]) {
        video.srcObject = event.streams[0];
        Promise.resolve(video.play()).catch((error) => {
          if (!disposed && error.name !== "AbortError") onError(error);
        });
      }
    };
    peer.onconnectionstatechange = () => {
      if (
        !disposed &&
        ["failed", "closed"].includes(activePeer.connectionState)
      )
        onError();
    };
    await peer.setLocalDescription(await peer.createOffer());
    if (disposed) return;
    await new Promise((resolve) => {
      if (activePeer.iceGatheringState === "complete") return resolve();
      const done = () => {
        clearTimeout(iceTimer);
        activePeer.removeEventListener("icegatheringstatechange", change);
        resolve();
      };
      const change = () => {
        if (activePeer.iceGatheringState === "complete") done();
      };
      finishIce = done;
      activePeer.addEventListener("icegatheringstatechange", change);
      iceTimer = setTimeout(done, 6000);
    });
    if (disposed) return;
    // Do not abort this request on scene exit: a late session must still be stopped.
    const result = await post("start", {
      offer_sdp: activePeer.localDescription.sdp,
    });
    session = result.media_session_id;
    if (disposed) {
      stopRemote();
      return;
    }
    await activePeer.setRemoteDescription({
      type: "answer",
      sdp: normalizeGoogleAnswer(result.answer_sdp),
    });
  };
  void start().catch((error) => {
    if (!disposed) onError(error);
    dispose();
  });
  return { dispose };
}
