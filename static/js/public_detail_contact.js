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
    const galleryStage = document.getElementById("pd-main-wrap");
    const mainImage = () => galleryStage?.querySelector("img.product-detail-image, picture img, img") || null;

    const setActiveThumbnail = (activeButton) => {
      document.querySelectorAll(".product-gallery-thumbs .pd-thumb").forEach((button) => {
        const isActive = button === activeButton;
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
        button.classList.toggle("is-active", isActive);
      });
    };

    const replaceMainImage = (button) => {
      const src = button.dataset.src;
      if (!src || !galleryStage) return;

      const alt = button.dataset.alt || button.getAttribute("aria-label") || "Product image";
      let image = mainImage();

      if (image) {
        const picture = image.closest("picture");
        picture?.querySelectorAll("source").forEach((source) => source.remove());
        image.removeAttribute("srcset");
        image.removeAttribute("sizes");
        image.src = src;
        image.alt = alt;
      } else {
        image = document.createElement("img");
        image.src = src;
        image.alt = alt;
        image.id = "pd-main-img";
        image.className = "product-detail-image";
        image.decoding = "async";
        const placeholder = galleryStage.querySelector(".product-detail-placeholder");
        if (placeholder) {
          placeholder.replaceWith(image);
        } else {
          galleryStage.prepend(image);
        }
      }

      setActiveThumbnail(button);
      zoomButton?.setAttribute("aria-label", `Open a larger view of ${alt}`);
    };

    document.querySelectorAll(".product-gallery-thumbs .pd-thumb").forEach((button, index) => {
      button.type = "button";
      if (!button.hasAttribute("aria-pressed")) {
        button.setAttribute("aria-pressed", index === 0 ? "true" : "false");
      }
      button.addEventListener(
        "click",
        (event) => {
          event.preventDefault();
          event.stopPropagation();
          event.stopImmediatePropagation();
          replaceMainImage(button);
        },
        { capture: true },
      );
    });

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
