(() => {
  "use strict";

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-copy-asset]");
    if (!button) return;
    const target = document.getElementById(button.dataset.copyAsset || "");
    if (!target || !navigator.clipboard) return;

    navigator.clipboard.writeText(target.textContent || "").then(() => {
      const original = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = original;
      }, 1500);
    });
  });
})();
