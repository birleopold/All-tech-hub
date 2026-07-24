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
    const galleryDialog = document.getElementById("product-gallery-dialog");
    const zoomButton = document.querySelector("[data-product-zoom]");
    const dialogImage = galleryDialog?.querySelector("[data-product-dialog-image]");
    const mainImage = () => document.querySelector("#pd-main-wrap img");

    const openGallery = () => {
      const source = mainImage();
      if (!galleryDialog || !dialogImage || !source) return;
      dialogImage.src = source.currentSrc || source.src;
      dialogImage.alt = source.alt || "Product image";
      if (typeof galleryDialog.showModal === "function") {
        galleryDialog.showModal();
      }
    };

    zoomButton?.addEventListener("click", openGallery);
    galleryDialog?.addEventListener("click", (event) => {
      if (event.target === galleryDialog) galleryDialog.close();
    });

    document.querySelectorAll(".pd-thumb").forEach((button) => {
      button.addEventListener("click", () => {
        window.setTimeout(() => {
          const source = mainImage();
          if (source && zoomButton) {
            zoomButton.setAttribute("aria-label", `Open a larger view of ${source.alt || "this image"}`);
          }
        }, 0);
      });
    });

    const contactType = document.getElementById("id_request_type");
    const subject = document.getElementById("id_subject");
    const message = document.getElementById("id_message");
    const intentButtons = document.querySelectorAll("[data-contact-intent]");

    const syncIntentButtons = () => {
      intentButtons.forEach((button) => {
        const active = Boolean(contactType && button.dataset.contactIntent === contactType.value);
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    };

    intentButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (!contactType) return;
        contactType.value = button.dataset.contactIntent || "other";
        contactType.dispatchEvent(new Event("change", { bubbles: true }));
        if (subject && !subject.value.trim() && button.dataset.subject) {
          subject.value = button.dataset.subject;
        }
        message?.focus({ preventScroll: true });
        document.getElementById("contact-form")?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
          block: "start",
        });
      });
    });

    contactType?.addEventListener("change", syncIntentButtons);
    syncIntentButtons();

    document.querySelectorAll("form[data-submit-progress]").forEach((form) => {
      form.addEventListener("submit", () => {
        const button = form.querySelector("button[type='submit']");
        if (!button) return;
        button.disabled = true;
        button.dataset.originalLabel = button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Sending…';
      });
    });
  });
})();
