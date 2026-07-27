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
    const moneyFormatter = new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    });

    const formatCurrencyText = (value) =>
      String(value || "").replace(
        /(\b[A-Z]{3}\s+)(\d+(?:\.\d+)?)/g,
        (_match, currency, amount) => `${currency}${moneyFormatter.format(Number(amount))}`,
      );

    const formatVisibleProductPrices = () => {
      const priceLabel = document.getElementById("pd-price-label");
      if (priceLabel) priceLabel.textContent = formatCurrencyText(priceLabel.textContent);

      document.querySelectorAll(".product-mobile-action__price").forEach((element) => {
        element.childNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) {
            node.textContent = formatCurrencyText(node.textContent);
          }
        });
      });

      const variantSelect = document.getElementById("variant_id");
      variantSelect?.querySelectorAll("option[data-price]").forEach((option) => {
        if (option.dataset.formattedPrice === "1") return;
        option.textContent = formatCurrencyText(option.textContent);
        option.dataset.formattedPrice = "1";
      });
    };

    formatVisibleProductPrices();

    const galleryDialog = document.getElementById("product-gallery-dialog");
    const zoomButton = document.querySelector("[data-product-zoom]");
    const dialogImage = galleryDialog?.querySelector("[data-product-dialog-image]");
    const galleryStage = document.getElementById("pd-main-wrap");
    const mainImage = () => galleryStage?.querySelector("img.product-detail-image, picture img, img") || null;

    // A Bootstrap stretched link must never escape a recently viewed card and
    // cover controls elsewhere on the page. Keep the cards isolated and use the
    // visible product-name links as normal links.
    document.querySelectorAll(".product-recent-card").forEach((card) => {
      card.style.position = "relative";
      card.style.isolation = "isolate";
    });
    document.querySelectorAll(".product-recent-card .stretched-link").forEach((link) => {
      link.classList.remove("stretched-link");
    });

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

    // Merchant and structured-data variant links use ?variant=<id>. Keep the
    // customer-facing selector aligned with the exact item represented by that URL.
    const requestedVariant = new URLSearchParams(window.location.search).get("variant");
    const variantSelect = document.getElementById("variant_id");
    if (variantSelect && requestedVariant && /^\d+$/.test(requestedVariant)) {
      const matchingOption = Array.from(variantSelect.options).find(
        (option) => option.value === requestedVariant,
      );
      if (matchingOption && !matchingOption.disabled) {
        variantSelect.value = requestedVariant;
        variantSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    variantSelect?.addEventListener("change", () => {
      window.requestAnimationFrame(formatVisibleProductPrices);
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