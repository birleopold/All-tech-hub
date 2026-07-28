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
    const desktopMedia = window.matchMedia("(min-width: 1200px)");
    const searchForm = document.querySelector("[data-desktop-search-form]");
    const searchInput = searchForm?.querySelector("[data-market-search-input]");
    const discovery = searchForm?.querySelector("[data-desktop-search-discovery]");
    const recentSection = searchForm?.querySelector("[data-desktop-recent-section]");
    const recentList = searchForm?.querySelector("[data-desktop-recent-searches]");
    const recentKey = "leosoft-desktop-recent-searches";
    const mobileRecentKey = "leosoft-mobile-recent-searches";

    const readStoredList = (key) => {
      try {
        const value = JSON.parse(window.localStorage.getItem(key) || "[]");
        return Array.isArray(value)
          ? value.filter((item) => typeof item === "string" && item.trim()).slice(0, 6)
          : [];
      } catch (_error) {
        return [];
      }
    };

    const readRecentSearches = () => {
      const values = [...readStoredList(recentKey), ...readStoredList(mobileRecentKey)];
      const seen = new Set();
      return values.filter((item) => {
        const key = item.trim().toLocaleLowerCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, 6);
    };

    const writeRecentSearch = (query) => {
      const cleaned = String(query || "").trim();
      if (cleaned.length < 2) return;
      const values = readRecentSearches().filter(
        (item) => item.toLocaleLowerCase() !== cleaned.toLocaleLowerCase(),
      );
      values.unshift(cleaned);
      try {
        window.localStorage.setItem(recentKey, JSON.stringify(values.slice(0, 6)));
      } catch (_error) {
        // Search remains fully functional when storage is unavailable.
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
        const icon = document.createElement("i");
        icon.className = "bi bi-clock-history";
        icon.setAttribute("aria-hidden", "true");
        const label = document.createElement("span");
        label.textContent = query;
        button.append(icon, label);
        button.addEventListener("click", () => {
          if (!searchInput) return;
          searchInput.value = query;
          discovery.hidden = true;
          searchInput.focus();
          searchInput.dispatchEvent(new Event("input", { bubbles: true }));
        });
        recentList.append(button);
      });
    };

    const showDiscovery = () => {
      if (!desktopMedia.matches || !discovery || !searchInput) return;
      if (searchInput.value.trim().length >= 2) return;
      renderRecentSearches();
      discovery.hidden = false;
    };

    const hideDiscovery = () => {
      if (discovery) discovery.hidden = true;
    };

    searchInput?.addEventListener("focus", showDiscovery);
    searchInput?.addEventListener("click", showDiscovery);
    searchInput?.addEventListener("input", () => {
      if (searchInput.value.trim().length >= 2) hideDiscovery();
      else if (document.activeElement === searchInput) showDiscovery();
    });
    searchForm?.addEventListener("submit", () => writeRecentSearch(searchInput?.value));

    document.addEventListener("pointerdown", (event) => {
      if (searchForm && !searchForm.contains(event.target)) hideDiscovery();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && discovery && !discovery.hidden) {
        event.preventDefault();
        hideDiscovery();
        searchInput?.focus();
      }
    });
    desktopMedia.addEventListener?.("change", (event) => {
      if (!event.matches) hideDiscovery();
    });

    const catalogGrid = document.querySelector("[data-market-catalog-grid]");
    const viewButtons = Array.from(document.querySelectorAll("[data-market-view]"));
    const desktopViewKey = "leosoft-desktop-catalog-view";
    const supportedViews = new Set(["grid", "list", "compact"]);

    const applyCatalogView = (view, persist = true) => {
      if (!catalogGrid) return;
      const normalized = supportedViews.has(view) ? view : "grid";
      catalogGrid.classList.toggle("is-list", normalized === "list");
      catalogGrid.classList.toggle("is-compact", normalized === "compact");
      catalogGrid.dataset.currentView = normalized;
      viewButtons.forEach((button) => {
        const active = button.dataset.marketView === normalized;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      if (persist) {
        try {
          window.localStorage.setItem(desktopViewKey, normalized);
        } catch (_error) {
          // View switching still works without persistent storage.
        }
      }
    };

    if (catalogGrid && desktopMedia.matches) {
      let storedView = "grid";
      try {
        storedView = window.localStorage.getItem(desktopViewKey) || "grid";
      } catch (_error) {
        storedView = "grid";
      }
      applyCatalogView(storedView, false);
      viewButtons.forEach((button) => {
        button.addEventListener("click", () => {
          applyCatalogView(button.dataset.marketView || "grid");
        });
      });
    }

    const controlDeck = document.querySelector("[data-desktop-catalog-control]");
    if (controlDeck && desktopMedia.matches) {
      let ticking = false;
      const updateStickyState = () => {
        const top = Number.parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue(
            "--desktop-commerce-header-offset",
          ),
        );
        controlDeck.classList.toggle(
          "is-stuck",
          controlDeck.getBoundingClientRect().top <= (Number.isFinite(top) ? top + 2 : 94),
        );
        ticking = false;
      };
      window.addEventListener(
        "scroll",
        () => {
          if (ticking) return;
          ticking = true;
          window.requestAnimationFrame(updateStickyState);
        },
        { passive: true },
      );
      updateStickyState();
    }
  });
})();
