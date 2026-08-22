(() => {
  "use strict";

  const form = document.querySelector("[data-checkout-pricing]");
  const ratesNode = document.getElementById("checkout-delivery-rates");
  if (!form || !ratesNode) return;

  let rates;
  try {
    rates = JSON.parse(ratesNode.textContent || "{}");
  } catch {
    return;
  }

  const zone = form.querySelector('[name="delivery_zone"]');
  if (!zone) return;
  const zoneField = form.querySelector("[data-delivery-zone-field]");
  const deliveryRow = document.querySelector("[data-checkout-delivery]");
  const deliveryAmount = document.querySelector("[data-checkout-delivery-amount]");
  const taxAmount = document.querySelector("[data-checkout-tax]");
  const totals = document.querySelectorAll("[data-checkout-total]");
  const baseTotal = Number(form.dataset.baseTotal || 0);
  const baseTax = Number(form.dataset.baseTax || 0);
  const taxRate = Number(form.dataset.taxRate || 0) / 100;
  const currency = form.dataset.currency || "UGX";
  const numberFormat = new Intl.NumberFormat("en-UG", {
    maximumFractionDigits: 0,
  });
  const money = (value) => `${currency} ${numberFormat.format(value)}`;

  function refresh() {
    const selected = form.querySelector('[name="fulfillment_type"]:checked');
    const delivery = !selected || selected.value === "delivery";
    const hasZone = Boolean(zone.value);
    const fee = delivery && hasZone ? Number(rates[zone.value] || 0) : 0;
    const deliveryTax = fee * taxRate;

    if (zoneField) zoneField.hidden = !delivery;
    zone.disabled = !delivery;
    zone.required = delivery;
    if (deliveryRow) deliveryRow.hidden = !delivery;
    if (deliveryAmount) {
      deliveryAmount.textContent = hasZone ? money(fee) : "Choose your delivery area";
    }
    if (taxAmount) taxAmount.textContent = money(baseTax + deliveryTax);
    totals.forEach((total) => {
      total.textContent = money(baseTotal + fee + deliveryTax);
    });
  }

  form.addEventListener("change", refresh);
  refresh();
})();
