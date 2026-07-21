(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
      return;
    }
    fn();
  }

  function updateQueryParameter(name, value) {
    var url = new URL(window.location.href);
    if (value) {
      url.searchParams.set(name, value);
    } else {
      url.searchParams.delete(name);
    }
    url.searchParams.delete("page");
    var query = url.searchParams.toString();
    window.location.assign(url.pathname + (query ? "?" + query : "") + url.hash);
  }

  function selectFulfillmentOption(radio) {
    document.querySelectorAll(".fulfillment-option").forEach(function (label) {
      label.classList.remove("border-primary", "bg-primary-subtle");
    });
    if (!radio || !radio.checked) {
      return;
    }
    var option = radio.closest(".fulfillment-option");
    if (option) {
      option.classList.add("border-primary", "bg-primary-subtle");
    }
  }

  function setActiveProductThumbnail(button) {
    document.querySelectorAll(".pd-thumb").forEach(function (thumb) {
      thumb.setAttribute("aria-pressed", "false");
      thumb.classList.remove("border-primary");
    });
    button.setAttribute("aria-pressed", "true");
    button.classList.add("border-primary");
  }

  ready(function () {
    document.querySelectorAll("[data-print-page]").forEach(function (button) {
      button.addEventListener("click", function () {
        window.print();
      });
    });

    var accountCustomerField = document.querySelector("[data-account-payment-field]");
    var accountCustomer = accountCustomerField ? accountCustomerField.querySelector("select, input") : null;
    if (accountCustomer) {
      accountCustomer.addEventListener("change", function () {
        updateQueryParameter("customer", accountCustomer.value);
      });
    }

    var savedSearchModal = document.getElementById("saveSearchModal");
    var savedParamsInput = document.getElementById("saved-params-input");
    function syncSavedSearchParams() {
      if (savedParamsInput) {
        savedParamsInput.value = window.location.search || "";
      }
    }
    if (savedSearchModal) {
      savedSearchModal.addEventListener("show.bs.modal", syncSavedSearchParams);
    }
    syncSavedSearchParams();

    var fulfillmentRadios = document.querySelectorAll(".fulfillment-option input[type='radio']");
    fulfillmentRadios.forEach(function (radio) {
      radio.addEventListener("change", function () {
        selectFulfillmentOption(radio);
      });
      if (radio.checked) {
        selectFulfillmentOption(radio);
      }
    });

    var productImage = document.getElementById("pd-main-img") || document.querySelector("#pd-main-wrap img");
    document.querySelectorAll(".pd-thumb").forEach(function (button, index) {
      if (!button.hasAttribute("aria-pressed")) {
        button.setAttribute("aria-pressed", index === 0 ? "true" : "false");
      }
      button.addEventListener("click", function () {
        var src = button.getAttribute("data-src");
        if (!src || !productImage) {
          return;
        }

        var alt = button.getAttribute("data-alt") || button.getAttribute("aria-label") || "Product image";
        if (productImage.tagName === "IMG") {
          var picture = productImage.closest("picture");
          if (picture) {
            picture.querySelectorAll("source").forEach(function (source) {
              source.remove();
            });
          }
          productImage.removeAttribute("srcset");
          productImage.src = src;
          productImage.alt = alt;
          setActiveProductThumbnail(button);
          return;
        }

        var image = document.createElement("img");
        image.src = src;
        image.className = "img-fluid w-100 product-detail-image";
        image.alt = alt;
        image.id = "pd-main-img";
        image.decoding = "async";
        productImage.replaceWith(image);
        productImage = image;
        setActiveProductThumbnail(button);
      });
    });

    var variantSelect = document.getElementById("variant_id");
    var priceLabel = document.getElementById("pd-price-label");
    var quantityInput = document.getElementById("quantity");
    if (priceLabel) {
      priceLabel.setAttribute("aria-live", "polite");
      priceLabel.setAttribute("aria-atomic", "true");
    }
    if (variantSelect) {
      variantSelect.addEventListener("change", function () {
        var option = variantSelect.options[variantSelect.selectedIndex];
        if (!option) {
          return;
        }

        if (priceLabel && option.dataset.price) {
          priceLabel.textContent = option.dataset.currency + " " + option.dataset.price;
        }

        if (!quantityInput) {
          return;
        }
        var tracksStock = option.dataset.track === "1";
        var stock = Number.parseInt(option.dataset.stock || "0", 10);
        if (tracksStock && Number.isFinite(stock) && stock > 0) {
          quantityInput.max = String(stock);
          if (Number.parseInt(quantityInput.value || "1", 10) > stock) {
            quantityInput.value = String(stock);
          }
        } else {
          quantityInput.removeAttribute("max");
        }
      });
    }

    var stockAlertType = document.getElementById("stock-alert-type");
    var stockAlertPrice = document.getElementById("stock-alert-price");
    function syncStockAlertFields() {
      if (!stockAlertType || !stockAlertPrice) {
        return;
      }
      var isPriceAlert = stockAlertType.value === "price_drop";
      stockAlertPrice.required = isPriceAlert;
      stockAlertPrice.disabled = !isPriceAlert;
      stockAlertPrice.setAttribute("aria-required", isPriceAlert ? "true" : "false");
      if (!isPriceAlert) {
        stockAlertPrice.value = "";
      }
    }
    if (stockAlertType && stockAlertPrice) {
      stockAlertType.addEventListener("change", syncStockAlertFields);
      syncStockAlertFields();
    }
  });
})();
