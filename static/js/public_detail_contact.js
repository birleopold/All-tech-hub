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
    const thumbnails = Array.from(
      document.querySelectorAll(".product-gallery-thumbs .pd-thumb"),
    );
    const mainImage = () =>
      galleryStage?.querySelector("img.product-detail-image, picture img, img") || null;
    let activeThumbnailIndex = 0;
    let touchStartX = null;

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
      const nextIndex = thumbnails.indexOf(activeButton);
      if (nextIndex >= 0) activeThumbnailIndex = nextIndex;
      thumbnails.forEach((button) => {
        const isActive = button === activeButton;
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
        button.classList.toggle("is-active", isActive);
      });
      activeButton?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "nearest",
        inline: "nearest",
      });
    };

    const finishImageTransition = () => {
      window.setTimeout(() => galleryStage?.classList.remove("is-changing"), 40);
    };

    const replaceMainImage = (button) => {
      const src = button.dataset.src;
      if (!src || !galleryStage) return;

      const alt = button.dataset.alt || button.getAttribute("aria-label") || "Product image";
      let image = mainImage();
      galleryStage.classList.add("is-changing");

      if (image) {
        const picture = image.closest("picture");
        picture?.querySelectorAll("source").forEach((source) => source.remove());
        image.removeAttribute("srcset");
        image.removeAttribute("sizes");
        image.addEventListener("load", finishImageTransition, { once: true });
        image.src = src;
        image.alt = alt;
        if (image.complete) finishImageTransition();
      } else {
        image = document.createElement("img");
        image.src = src;
        image.alt = alt;
        image.id = "pd-main-img";
        image.className = "product-detail-image";
        image.decoding = "async";
        image.addEventListener("load", finishImageTransition, { once: true });
        const placeholder = galleryStage.querySelector(".product-detail-placeholder");
        if (placeholder) {
          placeholder.replaceWith(image);
        } else {
          galleryStage.prepend(image);
        }
      }

      setActiveThumbnail(button);
      zoomButton?.setAttribute("aria-label", `Open a larger view of ${alt}`);
      galleryStage.setAttribute(
        "aria-label",
        `${alt}. Image ${activeThumbnailIndex + 1} of ${thumbnails.length}.`,
      );
    };

    const showThumbnailAt = (index) => {
      if (!thumbnails.length) return;
      const normalizedIndex = (index + thumbnails.length) % thumbnails.length;
      replaceMainImage(thumbnails[normalizedIndex]);
    };

    thumbnails.forEach((button, index) => {
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

    if (thumbnails.length) {
      const initiallyActive =
        thumbnails.find((button) => button.getAttribute("aria-pressed") === "true") ||
        thumbnails[0];
      setActiveThumbnail(initiallyActive);
    }

    if (galleryStage && thumbnails.length > 1) {
      galleryStage.tabIndex = 0;
      galleryStage.setAttribute(
        "aria-label",
        `Product image gallery. Image 1 of ${thumbnails.length}. Use left and right arrow keys to browse.`,
      );

      const createGalleryNavigationButton = (direction) => {
        const button = document.createElement("button");
        const previous = direction === "previous";
        button.type = "button";
        button.className = `product-gallery-nav product-gallery-nav--${direction}`;
        button.setAttribute(
          "aria-label",
          previous ? "Show previous product image" : "Show next product image",
        );
        button.innerHTML = `<i class="bi bi-chevron-${previous ? "left" : "right"}" aria-hidden="true"></i>`;
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          showThumbnailAt(activeThumbnailIndex + (previous ? -1 : 1));
        });
        galleryStage.append(button);
      };

      createGalleryNavigationButton("previous");
      createGalleryNavigationButton("next");

      galleryStage.addEventListener("keydown", (event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          showThumbnailAt(activeThumbnailIndex - 1);
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          showThumbnailAt(activeThumbnailIndex + 1);
        } else if (event.key === "Home") {
          event.preventDefault();
          showThumbnailAt(0);
        } else if (event.key === "End") {
          event.preventDefault();
          showThumbnailAt(thumbnails.length - 1);
        }
      });

      galleryStage.addEventListener(
        "touchstart",
        (event) => {
          touchStartX = event.changedTouches[0]?.clientX ?? null;
        },
        { passive: true },
      );
      galleryStage.addEventListener(
        "touchend",
        (event) => {
          if (touchStartX === null) return;
          const touchEndX = event.changedTouches[0]?.clientX ?? touchStartX;
          const movement = touchEndX - touchStartX;
          touchStartX = null;
          if (Math.abs(movement) < 45) return;
          showThumbnailAt(activeThumbnailIndex + (movement < 0 ? 1 : -1));
        },
        { passive: true },
      );
    }

    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (galleryStage && finePointer.matches && !reducedMotion.matches) {
      const resetGalleryMotion = () => {
        galleryStage.classList.remove("is-pointer-active");
        galleryStage.style.setProperty("--gallery-shift-x", "0px");
        galleryStage.style.setProperty("--gallery-shift-y", "0px");
        galleryStage.style.setProperty("--gallery-scale", "1");
        galleryStage.style.setProperty("--gallery-pointer-x", "50%");
        galleryStage.style.setProperty("--gallery-pointer-y", "50%");
      };

      galleryStage.addEventListener("pointerenter", () => {
        galleryStage.classList.add("is-pointer-active");
        galleryStage.style.setProperty("--gallery-scale", "1.045");
      });
      galleryStage.addEventListener("pointermove", (event) => {
        if (event.target.closest("button")) return;
        const rect = galleryStage.getBoundingClientRect();
        const xRatio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
        const yRatio = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
        galleryStage.style.setProperty("--gallery-pointer-x", `${xRatio * 100}%`);
        galleryStage.style.setProperty("--gallery-pointer-y", `${yRatio * 100}%`);
        galleryStage.style.setProperty("--gallery-shift-x", `${(xRatio - 0.5) * -8}px`);
        galleryStage.style.setProperty("--gallery-shift-y", `${(yRatio - 0.5) * -6}px`);
      });
      galleryStage.addEventListener("pointerleave", resetGalleryMotion);
      galleryStage.addEventListener("blur", resetGalleryMotion);
    }

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

    // The sticky mobile price and primary purchase panel must always show
    // the same *selected* configuration. Never submit an unselected variant.
    const productPriceLabel = document.getElementById("pd-price-label");
    const mobilePriceLabel = document.querySelector("[data-mobile-product-price]");
    const mobileVariantAction = document.querySelector("[data-mobile-variant-action]");
    const defaultProductPrice = productPriceLabel?.textContent || "";
    const defaultMobilePrice = mobilePriceLabel?.textContent || "";
    const productForm = document.getElementById("product-cart-form");
    const variantCurrency =
      variantSelect?.querySelector("option[data-currency]")?.dataset.currency || "UGX";
    const isService = document.body.classList.contains("public-service-detail");

    const syncSelectedVariant = () => {
      if (!variantSelect) return;
      const option = variantSelect.selectedOptions?.[0];
      const selected = Boolean(option?.value && !option.disabled);
      const amount = selected ? Number(option.dataset.price) : NaN;
      const priced = selected && Number.isFinite(amount) && amount > 0;
      const value = priced ? `${variantCurrency} ${moneyFormatter.format(amount)}` : "";

      if (productPriceLabel) {
        productPriceLabel.textContent = value || defaultProductPrice;
      }
      if (mobilePriceLabel) {
        mobilePriceLabel.textContent = value || defaultMobilePrice;
      }
      if (mobileVariantAction) {
        mobileVariantAction.textContent = selected
          ? (isService ? "Add service" : "Add to cart")
          : (isService ? "Choose service" : "Choose option");
      }
    };

    variantSelect?.addEventListener("change", () => {
      syncSelectedVariant();
      window.requestAnimationFrame(formatVisibleProductPrices);
    });
    syncSelectedVariant();

    mobileVariantAction?.addEventListener("click", (event) => {
      const option = variantSelect?.selectedOptions?.[0];
      if (!option?.value || option.disabled || !productForm) {
        // Leave the native #variant_id link usable even without JavaScript.
        variantSelect?.focus({ preventScroll: true });
        return;
      }
      event.preventDefault();
      const submitButton = productForm.querySelector('button[type="submit"]');
      if (typeof productForm.requestSubmit === "function") {
        productForm.requestSubmit(submitButton || undefined);
      } else {
        submitButton?.click();
      }
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
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
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
