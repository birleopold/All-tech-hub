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
    const body = document.body;
    const searchSheet = document.querySelector("[data-mobile-search-sheet]");
    const searchOpeners = Array.from(document.querySelectorAll("[data-mobile-search-open]"));
    const searchClosers = Array.from(document.querySelectorAll("[data-mobile-search-close]"));
    const searchInput = searchSheet?.querySelector("[data-mobile-search-input]");
    const recentList = searchSheet?.querySelector("[data-mobile-recent-searches]");
    const recentSection = searchSheet?.querySelector("[data-mobile-recent-section]");
    const recentKey = "leosoft-mobile-recent-searches";
    let lastSearchTrigger = null;

    const readRecentSearches = () => {
      try {
        const value = JSON.parse(window.localStorage.getItem(recentKey) || "[]");
        return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()).slice(0, 5) : [];
      } catch (_error) {
        return [];
      }
    };

    const writeRecentSearch = (query) => {
      const cleaned = String(query || "").trim();
      if (cleaned.length < 2) return;
      const values = readRecentSearches().filter((item) => item.toLocaleLowerCase() !== cleaned.toLocaleLowerCase());
      values.unshift(cleaned);
      try {
        window.localStorage.setItem(recentKey, JSON.stringify(values.slice(0, 5)));
      } catch (_error) {
        // Search remains usable when browser storage is unavailable.
      }
    };

    const renderRecentSearches = () => {
      if (!recentList || !recentSection) return;
      const values = readRecentSearches();
      recentList.replaceChildren();
      recentSection.hidden = !values.length;
      values.forEach((query) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = query;
        button.addEventListener("click", () => {
          if (!searchInput) return;
          searchInput.value = query;
          searchInput.focus();
          searchInput.dispatchEvent(new Event("input", { bubbles: true }));
        });
        recentList.append(button);
      });
    };

    const openSearchSheet = (trigger) => {
      if (!searchSheet) return;
      lastSearchTrigger = trigger || document.activeElement;
      renderRecentSearches();
      searchSheet.hidden = false;
      searchSheet.setAttribute("aria-hidden", "false");
      body.classList.add("mobile-commerce-sheet-open");
      searchOpeners.forEach((opener) => opener.setAttribute("aria-expanded", "true"));
      window.setTimeout(() => searchInput?.focus(), 30);
    };

    const closeSearchSheet = () => {
      if (!searchSheet || searchSheet.hidden) return;
      searchSheet.hidden = true;
      searchSheet.setAttribute("aria-hidden", "true");
      body.classList.remove("mobile-commerce-sheet-open");
      searchOpeners.forEach((opener) => opener.setAttribute("aria-expanded", "false"));
      if (lastSearchTrigger instanceof HTMLElement) lastSearchTrigger.focus();
    };

    searchOpeners.forEach((button) => button.addEventListener("click", () => openSearchSheet(button)));
    searchClosers.forEach((button) => button.addEventListener("click", closeSearchSheet));
    searchSheet?.querySelector("form")?.addEventListener("submit", () => writeRecentSearch(searchInput?.value));

    searchSheet?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSearchSheet();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        searchSheet.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    const mobileFilter = document.querySelector(".market-mobile-filter");
    const filterClose = mobileFilter?.querySelector("[data-mobile-filter-close]");
    const syncFilterState = () => {
      const open = Boolean(mobileFilter?.open);
      body.classList.toggle("market-mobile-filter-open", open);
      mobileFilter?.querySelector("summary")?.setAttribute("aria-expanded", open ? "true" : "false");
    };
    mobileFilter?.addEventListener("toggle", syncFilterState);
    filterClose?.addEventListener("click", () => {
      if (mobileFilter) mobileFilter.open = false;
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && mobileFilter?.open) {
        mobileFilter.open = false;
      }
    });

    const checkoutForm = document.querySelector("[data-mobile-checkout-form]");
    if (checkoutForm) {
      checkoutForm.addEventListener("submit", () => {
        const submitButtons = Array.from(
          document.querySelectorAll(`[form="${checkoutForm.id}"], #${checkoutForm.id} button[type="submit"]`),
        );
        submitButtons.forEach((button) => {
          button.disabled = true;
          button.setAttribute("aria-busy", "true");
          button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Placing order…';
        });
      });
    }

    const catalogGrid = document.querySelector("[data-market-catalog-grid]");
    if (catalogGrid && body.classList.contains("public-catalog-page")) {
      const scrollKey = `leosoft-catalog-scroll:${window.location.pathname}${window.location.search}`;
      const navigationEntry = window.performance?.getEntriesByType?.("navigation")?.[0];
      if (navigationEntry?.type === "back_forward") {
        try {
          const saved = Number(window.sessionStorage.getItem(scrollKey));
          if (Number.isFinite(saved) && saved > 0) {
            window.requestAnimationFrame(() => window.scrollTo({ top: saved, behavior: "auto" }));
          }
        } catch (_error) {
          // Native browser restoration remains available.
        }
      }
      catalogGrid.addEventListener("click", (event) => {
        const link = event.target.closest("a[href]");
        if (!link) return;
        try {
          window.sessionStorage.setItem(scrollKey, String(window.scrollY));
        } catch (_error) {
          // Navigation still works without session storage.
        }
      });
    }

    document.querySelectorAll(".mobile-commerce-page form").forEach((form) => {
      form.addEventListener("submit", () => {
        const submitter = form.querySelector('button[type="submit"]');
        if (!submitter || submitter.disabled || form === checkoutForm) return;
        submitter.setAttribute("aria-busy", "true");
      });
    });
  });
})();
