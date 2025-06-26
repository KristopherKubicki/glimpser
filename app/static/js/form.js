export function initFormValidation() {
  window.validateForm = function validateForm() {
    const name = document.getElementById("name").value.trim();
    const url = document.getElementById("url").value.trim();
    const frequency = parseInt(document.getElementById("frequency").value);
    const timeout = parseInt(document.getElementById("timeout").value);
    const objectFilter = document.getElementById("object_filter").value.trim();
    const objectConfidence = parseFloat(
      document.getElementById("object_confidence").value,
    );
    const popupXpath = document.getElementById("popup_xpath").value.trim();
    const dedicatedXpath = document
      .getElementById("dedicated_xpath")
      .value.trim();

    if (name === "" || url === "") {
      alert("Template Name and URL are required fields.");
      return false;
    }

    if (!/^https?:\/\//.test(url)) {
      alert("URL must start with http:// or https://");
      return false;
    }

    const submitBtn = document.querySelector(
      "input[type='submit'][data-url-ok]",
    );
    if (submitBtn && submitBtn.dataset.urlOk === "false") {
      if (!confirm("URL check failed. Add anyway?")) {
        return false;
      }
    }

    if (frequency < 0 || frequency > 43200) {
      alert("Frequency must be between 0 and 43200 minutes (30 days).");
      return false;
    }

    if (frequency >= 43200) {
      if (
        !confirm(
          `Warning: The frequency is set to ${frequency} minutes (more than 30 days). Are you sure you want to continue?`,
        )
      ) {
        return false;
      }
    }

    if (timeout < 3 || timeout > 59) {
      alert("Timeout must be between 3 and 59 seconds.");
      return false;
    }

    if (frequency > 0 && timeout >= frequency * 60) {
      alert("Timeout must be less than the frequency.");
      return false;
    }

    if (objectFilter !== "" && (objectConfidence < 0 || objectConfidence > 1)) {
      alert(
        "Object Confidence must be between 0 and 1 when Object Filter is specified.",
      );
      return false;
    }

    if (
      (popupXpath !== "" && !popupXpath.startsWith("//")) ||
      (dedicatedXpath !== "" && !dedicatedXpath.startsWith("//"))
    ) {
      alert("XPath expressions must start with '//'.");
      return false;
    }

    return true;
  };

  window.initAddSettingValidation = initAddSettingValidation;
}

export function initAddSettingValidation() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("add-setting-form");
    if (!form) return;
    form.addEventListener("submit", (e) => {
      const name = document.getElementById("new_name").value.trim();
      const value = document.getElementById("new_value").value.trim();
      const error = document.getElementById("setting-error");
      if (!name || !value || !/^[A-Z_]+$/.test(name)) {
        e.preventDefault();
        if (error) {
          error.textContent =
            "Name must use A-Z characters/underscores and value is required.";
          error.classList.remove("hidden");
        }
      }
    });
  });
}
