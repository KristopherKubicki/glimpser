import { jest } from "@jest/globals";

const html = `
  <button class="tab-link"></button>
  <div class="tab-content"></div>
  <table id="captions-table"><tbody>
    <tr>
      <td>t</td>
      <td class="caption-cell">
        <span class="caption-text">hello</span>
        <button class="speech-btn" type="button">▶</button>
      </td>
    </tr>
  </tbody></table>
`;

document.body.innerHTML = html;

let initCaptions;

beforeAll(async () => {
  ({ initCaptions } = await import("../../app/static/js/captions.js"));
});

describe("speech synthesis support", () => {
  beforeEach(() => {
    document.body.innerHTML = html;
    jest.clearAllMocks();
  });

  test("buttons hidden without support", () => {
    delete window.speechSynthesis;
    initCaptions();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(
      document.querySelector(".speech-btn").classList.contains("hidden"),
    ).toBe(true);
  });

  test("click speaks when supported", () => {
    window.speechSynthesis = { cancel: jest.fn(), speak: jest.fn() };
    window.SpeechSynthesisUtterance = function (t) {
      this.text = t;
    };
    window.AudioContext = function () {
      return {
        createOscillator: () => ({
          connect: jest.fn(),
          start: jest.fn(),
          stop: jest.fn(),
          onended: null,
          frequency: {},
        }),
        createGain: () => ({
          connect: jest.fn(),
          gain: { setValueAtTime: jest.fn() },
        }),
        destination: {},
        close: jest.fn(),
      };
    };

    initCaptions();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const btn = document.querySelector(".speech-btn");
    btn.click();
    expect(window.speechSynthesis.speak).toHaveBeenCalled();
  });
});
