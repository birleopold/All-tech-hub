(function () {
  "use strict";

  document.documentElement.classList.add("public-js");

  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  }

  ready(function () {
    var navbar = document.querySelector(".site-navbar");
    var ticking = false;

    function syncNavbar() {
      if (navbar) {
        navbar.classList.toggle("is-scrolled", window.scrollY > 12);
      }
      ticking = false;
    }

    if (navbar) {
      syncNavbar();
      window.addEventListener(
        "scroll",
        function () {
          if (!ticking) {
            ticking = true;
            window.requestAnimationFrame(syncNavbar);
          }
        },
        { passive: true }
      );
    }

    var revealNodes = Array.from(document.querySelectorAll("[data-reveal]"));
    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!revealNodes.length || reducedMotion || !("IntersectionObserver" in window)) {
      revealNodes.forEach(function (node) {
        node.classList.add("is-visible");
      });
    } else {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) {
              return;
            }
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          });
        },
        { rootMargin: "0px 0px -8%", threshold: 0.08 }
      );

      revealNodes.forEach(function (node) {
        observer.observe(node);
      });
    }

    document.querySelectorAll("[data-auto-submit]").forEach(function (control) {
      control.addEventListener("change", function () {
        var form = control.form;
        if (!form) {
          return;
        }
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    });

    document.querySelectorAll(".public-product-card__media img, .public-catalog-card__media img").forEach(function (image) {
      function markLoaded() {
        image.classList.add("is-loaded");
      }
      if (image.complete) {
        markLoaded();
      } else {
        image.addEventListener("load", markLoaded, { once: true });
      }
    });

    var mobileFilter = document.querySelector(".public-mobile-filter");
    if (mobileFilter && window.location.search) {
      var params = new URLSearchParams(window.location.search);
      if (params.get("category") || params.get("sort") || params.get("kind")) {
        mobileFilter.open = true;
      }
    }
  });
})();
