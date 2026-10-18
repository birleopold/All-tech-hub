(function () {
  "use strict";
  var preview = document.querySelector("[data-campaign-preview]");
  if (!preview) return;
  document.querySelectorAll("[data-campaign-preview-mode]").forEach(function (button) {
    button.addEventListener("click", function () {
      var mobile = button.dataset.campaignPreviewMode === "mobile";
      preview.classList.toggle("is-mobile", mobile);
      document.querySelectorAll("[data-campaign-preview-mode]").forEach(function (item) {
        var chosen = item === button;
        item.classList.toggle("active", chosen);
        item.setAttribute("aria-pressed", String(chosen));
      });
    });
  });
  // Preview a newly selected image locally. This does not upload, publish,
  // persist or share the file until the staff member saves the actual form.
  var imageInput = document.querySelector('[name="creative_image"]');
  var altInput = document.querySelector('[name="image_alt"]');
  var media = preview.querySelector("[data-campaign-preview-image]");
  var savedMedia = media ? media.innerHTML : "";
  var pendingObjectURL = null;

  function revokePendingPreview() {
    if (pendingObjectURL) {
      URL.revokeObjectURL(pendingObjectURL);
      pendingObjectURL = null;
    }
  }

  imageInput?.addEventListener("change", function () {
    if (!media) return;
    revokePendingPreview();
    var file = imageInput.files && imageInput.files[0];
    if (!file) {
      media.innerHTML = savedMedia;
      return;
    }
    if (!file.type.startsWith("image/")) {
      media.innerHTML = savedMedia;
      return;
    }
    pendingObjectURL = URL.createObjectURL(file);
    var img = document.createElement("img");
    img.src = pendingObjectURL;
    img.alt = altInput?.value.trim() || "Selected campaign image preview";
    img.decoding = "async";
    media.replaceChildren(img);
  });

  altInput?.addEventListener("input", function () {
    var img = media?.querySelector("img");
    if (img) img.alt = altInput.value.trim() || "Campaign image preview";
  });
  window.addEventListener("pagehide", revokePendingPreview);

  ["eyebrow", "headline", "supporting_text", "button_label"].forEach(function (name) {
    var source = document.querySelector('[name="' + name + '"]');
    var target = preview.querySelector('[data-campaign-preview-field="' + name + '"]');
    if (!source || !target) return;
    source.addEventListener("input", function () {
      var text = source.value.trim() || ("eyebrow" === name ? "Featured at LEOSOFT" :
        "headline" === name ? "Your headline appears here" :
        "button_label" === name ? "Explore products" : "One short benefit for shoppers.");
      if (name === "button_label") {
        target.textContent = text + " →";
      } else {
        target.textContent = text;
      }
    });
  });
}());
