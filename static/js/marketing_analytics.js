(() => {
  "use strict";

  const body = document.body;
  if (!body) return;

  const ga4Id = (body.dataset.ga4Id || "").trim();
  const clarityId = (body.dataset.clarityId || "").trim();
  const requireConsent = body.dataset.analyticsConsentRequired === "1";
  const consentKey = "leosoft_analytics_consent";
  // Browsers and privacy modes may block storage. Keep consent opt-in even
  // when its choice cannot be persisted.
  const readConsent = () => {
    try {
      const value = window.localStorage.getItem(consentKey);
      return value === "granted" || value === "denied" ? value : null;
    } catch (_error) {
      return null;
    }
  };
  const saveConsent = (choice) => {
    try {
      if (choice) window.localStorage.setItem(consentKey, choice);
      else window.localStorage.removeItem(consentKey);
    } catch (_error) {
      // Do not silently enable tracking if the browser rejects storage.
    }
  };
  let integrationsLoaded = false;
  let vitalsObserved = false;

  const readJsonScript = (id) => {
    const node = document.getElementById(id);
    if (!node) return [];
    try {
      const value = JSON.parse(node.textContent || "[]");
      return Array.isArray(value) ? value : [];
    } catch (_error) {
      return [];
    }
  };

  const queuedEvents = [
    ...readJsonScript("growth-page-events"),
    ...readJsonScript("growth-pending-events"),
  ];

  const collectCatalogItems = () => {
    const cards = Array.from(document.querySelectorAll("[data-analytics-product-card]"));
    if (!cards.length) return;
    const items = cards.map((card, index) => ({
      item_id: card.dataset.itemId || "",
      item_name: card.dataset.itemName || "",
      item_category: card.dataset.itemCategory || "",
      price: Number(card.dataset.itemPrice || 0),
      index,
      quantity: 1,
    }));
    queuedEvents.push({
      name: "view_item_list",
      params: {
        item_list_id: "catalog",
        item_list_name: "LEOSOFT catalog",
        items,
      },
    });
  };

  collectCatalogItems();

  const sendEvent = (event) => {
    if (!event || !event.name || typeof window.gtag !== "function") return;
    window.gtag("event", event.name, event.params || {});
  };

  const flushEvents = () => {
    if (!ga4Id || typeof window.gtag !== "function") return;
    queuedEvents.splice(0).forEach(sendEvent);
  };

  const vitalRating = (name, value) => {
    const thresholds = {
      LCP: [2500, 4000],
      INP: [200, 500],
      CLS: [0.1, 0.25],
      FCP: [1800, 3000],
      TTFB: [800, 1800],
    }[name];
    if (!thresholds) return "unknown";
    if (value <= thresholds[0]) return "good";
    if (value <= thresholds[1]) return "needs_improvement";
    return "poor";
  };

  const queueVital = (name, value) => {
    if (!Number.isFinite(value) || value < 0) return;
    queuedEvents.push({
      name: "web_vital",
      params: {
        metric_name: name,
        metric_value: Number(value.toFixed(name === "CLS" ? 4 : 1)),
        metric_rating: vitalRating(name, value),
        page_path: window.location.pathname,
        non_interaction: true,
      },
    });
    if (integrationsLoaded) flushEvents();
  };

  const observeWebVitals = () => {
    if (vitalsObserved || !ga4Id || !("PerformanceObserver" in window)) return;
    vitalsObserved = true;

    const navigation = performance.getEntriesByType("navigation")[0];
    if (navigation && Number.isFinite(navigation.responseStart)) {
      queueVital("TTFB", navigation.responseStart);
    }
    const firstContentfulPaint = performance.getEntriesByName("first-contentful-paint")[0];
    if (firstContentfulPaint) queueVital("FCP", firstContentfulPaint.startTime);

    let latestLcp = 0;
    let cumulativeLayoutShift = 0;
    let worstInteraction = 0;
    const observers = [];

    const observe = (type, callback, options = {}) => {
      try {
        const observer = new PerformanceObserver(callback);
        observer.observe({ type, buffered: true, ...options });
        observers.push(observer);
      } catch (_error) {
        // Unsupported performance entry type.
      }
    };

    observe("largest-contentful-paint", (list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) latestLcp = last.startTime;
    });

    observe("layout-shift", (list) => {
      list.getEntries().forEach((entry) => {
        if (!entry.hadRecentInput) cumulativeLayoutShift += entry.value;
      });
    });

    observe("event", (list) => {
      list.getEntries().forEach((entry) => {
        if (entry.interactionId && entry.duration > worstInteraction) {
          worstInteraction = entry.duration;
        }
      });
    }, { durationThreshold: 40 });

    let finalised = false;
    const finalise = () => {
      if (finalised) return;
      finalised = true;
      if (latestLcp) queueVital("LCP", latestLcp);
      queueVital("CLS", cumulativeLayoutShift);
      if (worstInteraction) queueVital("INP", worstInteraction);
      observers.forEach((observer) => observer.disconnect());
    };

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") finalise();
    }, { once: true });
    window.addEventListener("pagehide", finalise, { once: true });
  };

  observeWebVitals();

  const loadGA4 = () => {
    if (!ga4Id) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function gtag() {
      window.dataLayer.push(arguments);
    };
    window.gtag("js", new Date());
    window.gtag("config", ga4Id, {
      send_page_view: true,
      allow_google_signals: false,
    });
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ga4Id)}`;
    script.addEventListener("load", flushEvents, { once: true });
    document.head.appendChild(script);
  };

  const loadClarity = () => {
    if (!clarityId) return;
    window.clarity = window.clarity || function clarity() {
      (window.clarity.q = window.clarity.q || []).push(arguments);
    };
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.clarity.ms/tag/${encodeURIComponent(clarityId)}`;
    document.head.appendChild(script);
  };

  const loadIntegrations = () => {
    if (integrationsLoaded) return;
    integrationsLoaded = true;
    loadGA4();
    loadClarity();
  };

  const banner = document.getElementById("analytics-consent-banner");
  const setConsent = (choice) => {
    saveConsent(choice);
    if (banner) banner.hidden = true;
    if (choice === "granted") loadIntegrations();
  };

  document.addEventListener("click", (event) => {
    const accept = event.target.closest("[data-analytics-consent-accept]");
    if (accept) {
      setConsent("granted");
      return;
    }
    const decline = event.target.closest("[data-analytics-consent-decline]");
    if (decline) {
      setConsent("denied");
      return;
    }
    const reset = event.target.closest("[data-analytics-consent-reset]");
    if (reset) {
      saveConsent(null);
      if (integrationsLoaded) {
        // Scripts loaded during this page cannot be reliably unloaded.
        // Reload without consent before offering another choice.
        window.location.reload();
      } else if (banner) {
        banner.hidden = false;
      }
      return;
    }

    const productLink = event.target.closest("[data-analytics-product-link]");
    if (productLink && typeof window.gtag === "function") {
      const card = productLink.closest("[data-analytics-product-card]");
      if (!card) return;
      sendEvent({
        name: "select_item",
        params: {
          item_list_id: "catalog",
          item_list_name: "LEOSOFT catalog",
          items: [{
            item_id: card.dataset.itemId || "",
            item_name: card.dataset.itemName || "",
            item_category: card.dataset.itemCategory || "",
            price: Number(card.dataset.itemPrice || 0),
            quantity: 1,
          }],
        },
      });
    }
  });

  if (!ga4Id && !clarityId) {
    if (banner) banner.hidden = true;
    return;
  }

  const choice = readConsent();
  if (!requireConsent || choice === "granted") {
    if (banner) banner.hidden = true;
    loadIntegrations();
  } else if (choice === "denied") {
    if (banner) banner.hidden = true;
  } else if (banner) {
    banner.hidden = false;
  }
})();
