(() => {
  "use strict";

  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  };

  ready(() => {
    const form = document.querySelector("[data-catalogue-bulk-form]");
    if (!form) return;

    const checkboxes = Array.from(form.querySelectorAll("[data-bulk-product]"));
    const selectButton = form.querySelector("[data-select-visible]");
    const clearButton = form.querySelector("[data-clear-visible]");
    const submitButton = form.querySelector("[data-bulk-submit]");
    const status = form.querySelector("[data-bulk-selection-status]");

    const updateStatus = () => {
      const selected = checkboxes.filter((checkbox) => checkbox.checked).length;
      if (submitButton) submitButton.disabled = selected === 0;
      if (status) {
        status.textContent = selected
          ? `${selected} product${selected === 1 ? "" : "s"} selected on this page.`
          : "No products selected.";
      }
    };

    selectButton?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = true;
      });
      updateStatus();
    });

    clearButton?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      updateStatus();
    });

    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateStatus));
    updateStatus();
  });
})();
