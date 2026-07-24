(() => {
  "use strict";

  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
    } else {
      callback();
    }
  };

  const createElement = (tagName, className, text) => {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  ready(() => {
    const globalSearch = document.getElementById("market-global-search");
    const heroSearch = document.getElementById("market-hero-search-input");
    const suggestionCache = new Map();

    const setupSearchAutocomplete = (form, formIndex) => {
      const input = form.querySelector("[data-market-search-input]");
      const results = form.querySelector("[data-market-search-results]");
      const status = form.querySelector("[data-market-search-status]");
      const endpoint = form.dataset.suggestionsUrl;
      if (!input || !results || !endpoint) return;

      let timer = 0;
      let controller = null;
      let options = [];
      let activeIndex = -1;

      const setExpanded = (expanded) => {
        input.setAttribute("aria-expanded", expanded ? "true" : "false");
        results.hidden = !expanded;
        if (!expanded) {
          input.removeAttribute("aria-activedescendant");
          activeIndex = -1;
          options.forEach((option) => option.classList.remove("is-active"));
        }
      };

      const closeResults = () => setExpanded(false);

      const setActiveOption = (index) => {
        if (!options.length) return;
        activeIndex = (index + options.length) % options.length;
        options.forEach((option, optionIndex) => {
          const active = optionIndex === activeIndex;
          option.classList.toggle("is-active", active);
          option.setAttribute("aria-selected", active ? "true" : "false");
          if (active) {
            input.setAttribute("aria-activedescendant", option.id);
            option.scrollIntoView({ block: "nearest" });
          }
        });
      };

      const appendHeading = (section, label, count) => {
        const heading = createElement("div", "market-search-results__heading");
        heading.append(createElement("span", "", label));
        if (count !== undefined) heading.append(createElement("span", "", String(count)));
        section.append(heading);
      };

      const appendOption = ({ url, name, meta, image, icon, price }) => {
        const option = createElement("a", "market-search-option");
        option.href = url;
        option.id = `market-search-option-${formIndex}-${options.length}`;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");

        if (image) {
          const imageElement = createElement("img", "market-search-option__image");
          imageElement.src = image;
          imageElement.alt = "";
          imageElement.loading = "lazy";
          imageElement.decoding = "async";
          option.append(imageElement);
        } else {
          const iconBox = createElement("span", "market-search-option__icon");
          const iconElement = createElement("i", `bi ${icon || "bi-search"}`);
          iconElement.setAttribute("aria-hidden", "true");
          iconBox.append(iconElement);
          option.append(iconBox);
        }

        const copy = createElement("span", "market-search-option__copy");
        copy.append(createElement("strong", "", name));
        if (meta) copy.append(createElement("small", "", meta));
        option.append(copy);
        if (price) option.append(createElement("span", "market-search-option__price", price));

        results.append(option);
        options.push(option);
      };

      const renderSuggestions = (payload) => {
        results.replaceChildren();
        options = [];
        activeIndex = -1;

        const products = Array.isArray(payload.products) ? payload.products : [];
        const categories = Array.isArray(payload.categories) ? payload.categories : [];
        const brands = Array.isArray(payload.brands) ? payload.brands : [];

        if (products.length) {
          const section = createElement("section", "market-search-results__section");
          appendHeading(section, "Products and services", products.length);
          results.append(section);
          products.forEach((product) => {
            const metaParts = [product.brand, product.category, product.condition].filter(Boolean);
            appendOption({
              url: product.url,
              name: product.name,
              meta: metaParts.join(" · "),
              image: product.image,
              icon: product.kind === "service" ? "bi-tools" : "bi-laptop",
              price: `${product.currency} ${Number(product.price).toLocaleString()}`,
            });
          });
        }

        if (categories.length) {
          const section = createElement("section", "market-search-results__section");
          appendHeading(section, "Categories", categories.length);
          results.append(section);
          categories.forEach((category) => {
            appendOption({
              url: category.url,
              name: category.name,
              meta: `${category.count} matching item${category.count === 1 ? "" : "s"}`,
              icon: "bi-grid",
            });
          });
        }

        if (brands.length) {
          const section = createElement("section", "market-search-results__section");
          appendHeading(section, "Brands", brands.length);
          results.append(section);
          brands.forEach((brand) => {
            appendOption({
              url: brand.url,
              name: brand.name,
              meta: `${brand.count} product${brand.count === 1 ? "" : "s"}`,
              icon: "bi-patch-check",
            });
          });
        }

        if (!options.length) {
          results.append(
            createElement(
              "div",
              "market-search-empty",
              `No quick matches for “${payload.query || input.value.trim()}”. Try the full catalogue search.`,
            ),
          );
        }

        const footer = createElement("a", "market-search-results__footer");
        footer.href = payload.search_url || `${form.action}?q=${encodeURIComponent(input.value.trim())}`;
        footer.append(createElement("span", "", `Search the full catalogue for “${payload.query || input.value.trim()}”`));
        const footerIcon = createElement("i", "bi bi-arrow-right");
        footerIcon.setAttribute("aria-hidden", "true");
        footer.append(footerIcon);
        results.append(footer);

        options = Array.from(results.querySelectorAll("[role='option']"));
        if (status) {
          status.textContent = options.length
            ? `${options.length} search suggestions available.`
            : "No quick suggestions available. Submit to search the full catalogue.";
        }
        setExpanded(true);
      };

      const showLoading = () => {
        results.replaceChildren(createElement("div", "market-search-loading", "Searching catalogue…"));
        options = [];
        if (status) status.textContent = "Searching catalogue.";
        setExpanded(true);
      };

      const loadSuggestions = async () => {
        const query = input.value.trim();
        if (query.length < 2) {
          closeResults();
          return;
        }

        const cacheKey = query.toLocaleLowerCase();
        if (suggestionCache.has(cacheKey)) {
          renderSuggestions(suggestionCache.get(cacheKey));
          return;
        }

        controller?.abort();
        controller = new AbortController();
        showLoading();
        try {
          const url = new URL(endpoint, window.location.origin);
          url.searchParams.set("q", query);
          const response = await fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
            signal: controller.signal,
          });
          if (!response.ok) throw new Error(`Suggestion request failed: ${response.status}`);
          const payload = await response.json();
          suggestionCache.set(cacheKey, payload);
          if (input.value.trim().toLocaleLowerCase() === cacheKey) renderSuggestions(payload);
        } catch (error) {
          if (error.name === "AbortError") return;
          closeResults();
        }
      };

      input.addEventListener("input", () => {
        window.clearTimeout(timer);
        if (input.value.trim().length < 2) {
          closeResults();
          return;
        }
        timer = window.setTimeout(loadSuggestions, 180);
      });

      input.addEventListener("focus", () => {
        if (input.value.trim().length >= 2 && results.childElementCount) setExpanded(true);
      });

      input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
          if (results.hidden) loadSuggestions();
          event.preventDefault();
          setActiveOption(activeIndex + 1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setActiveOption(activeIndex - 1);
        } else if (event.key === "Enter" && activeIndex >= 0 && options[activeIndex]) {
          event.preventDefault();
          window.location.assign(options[activeIndex].href);
        } else if (event.key === "Escape") {
          event.preventDefault();
          closeResults();
        } else if (event.key === "Tab") {
          closeResults();
        }
      });

      form.addEventListener("submit", () => closeResults());
      document.addEventListener("pointerdown", (event) => {
        if (!form.contains(event.target)) closeResults();
      });
    };

    document.querySelectorAll("[data-market-search-form]").forEach(setupSearchAutocomplete);

    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target?.isContentEditable;
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
      if (filterKeys.some((key) => parameters.has(key))) mobileFilter.open = true;
    }

    [globalSearch, heroSearch].filter(Boolean).forEach((input) => {
      input.addEventListener("search", () => {
        if (!input.value.trim()) input.form?.requestSubmit();
      });
    });

    document.querySelectorAll("form[data-market-quick-add]").forEach((form) => {
      form.addEventListener("submit", () => {
        const button = form.querySelector("button[type='submit']");
        if (!button) return;
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span class="visually-hidden">Adding to cart…</span>';
      });
    });
  });
})();
