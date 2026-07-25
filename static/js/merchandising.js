(() => {
  "use strict";

  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
    } else {
      callback();
    }
  };

  ready(() => {
    document.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-product-quick-view-target]");
      if (trigger) {
        const dialog = document.getElementById(trigger.dataset.productQuickViewTarget || "");
        if (dialog instanceof HTMLDialogElement) {
          dialog.showModal();
        }
        return;
      }

      const dialog = event.target instanceof HTMLDialogElement ? event.target : null;
      if (dialog && event.target === dialog) {
        const bounds = dialog.getBoundingClientRect();
        const inside =
          event.clientX >= bounds.left &&
          event.clientX <= bounds.right &&
          event.clientY >= bounds.top &&
          event.clientY <= bounds.bottom;
        if (!inside) dialog.close();
      }
    });
  });
})();
