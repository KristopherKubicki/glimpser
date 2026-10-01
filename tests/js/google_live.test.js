import { jest } from "@jest/globals";
import {
  connectGoogleLive,
  normalizeGoogleAnswer,
} from "../../app/static/js/google_live.js";
const flush = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve();
};
afterEach(() => {
  jest.restoreAllMocks();
  delete global.RTCPeerConnection;
});
test("normalizes legacy Google SDP without changing video codec lines", () => {
  const answer = normalizeGoogleAnswer(
    "m=video 9 RTP/SAVPF 96\na=sendrecv\nm=application 9 DTLS/SCTP 5000\na=sctpmap:5000 webrtc-datachannel 1024\n",
  );
  expect(answer).toContain("a=sendonly\r\n");
  expect(answer).toContain("UDP/DTLS/SCTP webrtc-datachannel");
  expect(answer).toContain("a=sctp-port:5000");
  expect(answer).toContain("m=video 9 RTP/SAVPF 96");
});
test("a late start response after disposal is explicitly stopped", async () => {
  let answer;
  const pending = new Promise((resolve) => (answer = resolve));
  const close = jest.fn();
  global.RTCPeerConnection = class {
    constructor() {
      this.iceGatheringState = "complete";
      this.localDescription = { sdp: "offer" };
    }
    addTransceiver() {}
    createDataChannel() {}
    createOffer() {
      return Promise.resolve({});
    }
    setLocalDescription() {
      return Promise.resolve();
    }
    close() {
      close();
    }
  };
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        token: "scoped",
        profile: "test",
        device_id: "door",
      }),
    })
    .mockReturnValueOnce(pending)
    .mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  const video = document.createElement("video");
  const error = jest.fn();
  const session = connectGoogleLive(video, "Front_door_doorbell", error);
  await flush();
  expect(fetch).toHaveBeenCalledTimes(2);
  session.dispose();
  answer({
    ok: true,
    json: async () => ({
      ok: true,
      media_session_id: "late",
      answer_sdp: "answer",
    }),
  });
  await flush();
  expect(close).toHaveBeenCalled();
  expect(fetch.mock.calls[2][0]).toContain("/stop?");
  expect(JSON.parse(fetch.mock.calls[2][1].body).media_session_id).toBe("late");
  expect(error).not.toHaveBeenCalled();
});
test("unsupported browsers fail without requesting camera credentials", async () => {
  global.fetch = jest.fn();
  const error = jest.fn();
  connectGoogleLive(document.createElement("video"), "Door", error);
  await flush();
  expect(error).toHaveBeenCalledTimes(1);
  expect(fetch).not.toHaveBeenCalled();
});

test("audio and video tracks sharing one stream only initiate playback once", async () => {
  let peer;
  global.RTCPeerConnection = class {
    constructor() {
      peer = this;
      this.iceGatheringState = "complete";
      this.localDescription = { sdp: "offer" };
    }
    addTransceiver() {}
    createDataChannel() {}
    createOffer() {
      return Promise.resolve({});
    }
    setLocalDescription() {
      return Promise.resolve();
    }
    setRemoteDescription() {
      return Promise.resolve();
    }
    close() {}
  };
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        token: "scoped",
        profile: "test",
        device_id: "door",
      }),
    })
    .mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        media_session_id: "session",
        answer_sdp: "answer",
      }),
    });
  const video = document.createElement("video");
  video.play = jest.fn().mockResolvedValue();
  const stream = { getTracks: () => [] };
  const session = connectGoogleLive(video, "Door", jest.fn());
  await flush();
  peer.ontrack({ streams: [stream] });
  peer.ontrack({ streams: [stream] });
  expect(video.play).toHaveBeenCalledTimes(1);
  session.dispose();
  await flush();
});
