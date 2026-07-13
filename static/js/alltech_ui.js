(function () {
  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
      return;
    }
    fn();
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
        if (accountCustomer.value) {
          window.location.search = "?customer=" + encodeURIComponent(accountCustomer.value);
        }
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

    document.querySelectorAll(".fulfillment-option input[type='radio']").forEach(function (radio) {
      radio.addEventListener("change", function () {
        document.querySelectorAll(".fulfillment-option").forEach(function (label) {
          label.classList.remove("border-primary", "bg-primary-subtle");
        });
        if (radio.checked) {
          var option = radio.closest(".fulfillment-option");
          if (option) {
            option.classList.add("border-primary", "bg-primary-subtle");
          }
        }
      });
    });

    var productImage = document.getElementById("pd-main-img");
    document.querySelectorAll(".pd-thumb").forEach(function (button) {
      button.addEventListener("click", function () {
        var src = button.getAttribute("data-src");
        if (!src || !productImage) {
          return;
        }
        if (productImage.tagName === "IMG") {
          productImage.src = src;
          return;
        }
        var image = document.createElement("img");
        image.src = src;
        image.className = "img-fluid w-100 product-detail-image";
        image.alt = "";
        image.id = "pd-main-img";
        productImage.replaceWith(image);
        productImage = image;
      });
    });

    var variantSelect = document.getElementById("variant_id");
    var priceLabel = document.getElementById("pd-price-label");
    if (variantSelect && priceLabel) {
      variantSelect.addEventListener("change", function () {
        var option = variantSelect.options[variantSelect.selectedIndex];
        if (!option || !option.dataset.price) {
          return;
        }
        priceLabel.textContent = option.dataset.currency + " " + option.dataset.price;
      });
    }
  });
})();
