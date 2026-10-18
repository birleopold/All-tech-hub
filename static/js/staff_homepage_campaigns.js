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
