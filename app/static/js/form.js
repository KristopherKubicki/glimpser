export function initFormValidation() {
  window.validateForm = function validateForm() {
    const err = document.getElementById("template-error");
    if (err) {
      err.textContent = "";
      err.classList.add("hidden");
    }
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

    const showError = (msg) => {
      if (err) {
        err.textContent = msg;
        err.classList.remove("hidden");
      } else {
        alert(msg);
      }
    };

    if (name === "" || url === "") {
      showError("Template Name and URL are required fields.");
      return false;
    }

    if (!/^https?:\/\//.test(url)) {
      showError("URL must start with http:// or https://");
      return false;
    }

    if (frequency < 0 || frequency > 43200) {
      showError("Frequency must be between 0 and 43200 minutes (30 days).");
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
      showError("Timeout must be between 3 and 59 seconds.");
      return false;
    }

    if (frequency > 0 && timeout >= frequency * 60) {
      showError("Timeout must be less than the frequency.");
      return false;
    }

    if (objectFilter !== "" && (objectConfidence < 0 || objectConfidence > 1)) {
      showError(
        "Object Confidence must be between 0 and 1 when Object Filter is specified.",
      );
      return false;
    }

    if (
      (popupXpath !== "" && !popupXpath.startsWith("//")) ||
      (dedicatedXpath !== "" && !dedicatedXpath.startsWith("//"))
    ) {
      showError("XPath expressions must start with '//'.");
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
