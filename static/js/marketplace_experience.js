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
    const globalSearch = document.getElementById("market-global-search");
    const heroSearch = document.getElementById("market-hero-search-input");

    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const isTyping = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
      if (event.key === "/" && !isTyping && globalSearch) {
        event.preventDefault();
        globalSearch.focus();
        globalSearch.select();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && globalSearch) {
        event.preventDefault();
        globalSearch.focus();
        globalSearch.select();
      }
    });

    document.querySelectorAll("[data-market-auto-submit]").forEach((field) => {
      field.addEventListener("change", () => field.form?.requestSubmit());
    });

    const catalogGrid = document.querySelector("[data-market-catalog-grid]");
    const viewButtons = document.querySelectorAll("[data-market-view]");
    const storageKey = "leosoft-catalog-view";

    const setCatalogView = (view) => {
      if (!catalogGrid) return;
      const listView = view === "list";
      catalogGrid.classList.toggle("is-list", listView);
      catalogGrid.dataset.currentView = listView ? "list" : "grid";
      viewButtons.forEach((button) => {
        const active = button.dataset.marketView === catalogGrid.dataset.currentView;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      try {
        window.localStorage.setItem(storageKey, catalogGrid.dataset.currentView);
      } catch (_error) {
        // Storage may be unavailable in private browsing; the layout still works.
      }
    };

    if (catalogGrid) {
      let storedView = "grid";
      try {
        storedView = window.localStorage.getItem(storageKey) || "grid";
      } catch (_error) {
        storedView = "grid";
      }
      setCatalogView(storedView);
      viewButtons.forEach((button) => {
        button.addEventListener("click", () => setCatalogView(button.dataset.marketView || "grid"));
      });
    }

    document.querySelectorAll("[data-market-scroll-target]").forEach((button) => {
      button.addEventListener("click", () => {
        const selector = button.dataset.marketScrollTarget;
        const target = selector ? document.querySelector(selector) : null;
        if (!target) return;
        target.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
          block: "nearest",
          inline: "start",
        });
      });
    });

    const mobileFilter = document.querySelector(".market-mobile-filter");
    if (mobileFilter && window.location.search) {
      const parameters = new URLSearchParams(window.location.search);
      const filterKeys = ["brand", "condition", "min_price", "max_price", "available", "collection"];
      if (filterKeys.some((key) => parameters.has(key))) {
        mobileFilter.open = true;
      }
    }

    [globalSearch, heroSearch].filter(Boolean).forEach((input) => {
      input.addEventListener("search", () => {
        if (!input.value.trim()) input.form?.requestSubmit();
      });
    });
  });
})();
