export function initAutocomplete() {
  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("search-input");
    if (!input) return;

    let datalist = document.getElementById("search-suggestions");
    if (!datalist) {
      datalist = document.createElement("datalist");
      datalist.id = "search-suggestions";
      document.body.appendChild(datalist);
    }
    input.setAttribute("list", "search-suggestions");

    let aborter;
    input.addEventListener("input", () => {
      const term = input.value.trim();
      if (aborter) aborter.abort();
      if (!term) {
        datalist.innerHTML = "";
        return;
      }
      aborter = new AbortController();
      fetch(`/search_suggestions?q=${encodeURIComponent(term)}`, {
        signal: aborter.signal,
      })
        .then((res) => res.json())
        .then((items) => {
          datalist.innerHTML = items
            .map((s) => `<option value="${s}"></option>`)
            .join("");
        })
        .catch((err) => {
          if (err.name !== "AbortError") console.error(err);
        });
    });
  });
}
