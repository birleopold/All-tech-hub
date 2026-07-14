(() => {
  "use strict";

  const body = document.body;
  if (!body) return;

  const ga4Id = (body.dataset.ga4Id || "").trim();
  const clarityId = (body.dataset.clarityId || "").trim();
  const requireConsent = body.dataset.analyticsConsentRequired === "1";
  const consentKey = "leosoft_analytics_consent";
  let integrationsLoaded = false;

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
    localStorage.setItem(consentKey, choice);
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
      localStorage.removeItem(consentKey);
      if (banner) banner.hidden = false;
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

  const choice = localStorage.getItem(consentKey);
  if (!requireConsent || choice === "granted") {
    if (banner) banner.hidden = true;
    loadIntegrations();
  } else if (choice === "denied") {
    if (banner) banner.hidden = true;
  } else if (banner) {
    banner.hidden = false;
  }
})();
