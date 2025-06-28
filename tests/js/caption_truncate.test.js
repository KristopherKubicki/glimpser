import { jest } from "@jest/globals";

document.body.innerHTML = `
  <table id="camera-table"><tbody>
    <tr class="camera-row">
      <td><div class="templateDiv" style="height:60px"></div></td>
      <td>
        <form class="caption-box">
          <div class="chat-box">
            <div class="chat-prompt"><textarea style="height:40px"></textarea></div>
            <div class="chat-response"><div class="last-caption">long text</div></div>
          </div>
        </form>
      </td>
    </tr>
  </tbody></table>
  <input id="grid-width-slider" type="range" value="100">
`;

let updateTableLayout;

beforeAll(async () => {
  ({ updateTableLayout } = await import("../../app/static/js/templates.js"));
});

test("caption clamps when space limited", () => {
  const caption = document.querySelector(".last-caption");
  Object.defineProperty(caption, "scrollHeight", { value: 120 });
  updateTableLayout(100);
  expect(caption.classList.contains("ellipsis")).toBe(true);
  expect(caption.style.maxHeight).not.toBe("");
});
