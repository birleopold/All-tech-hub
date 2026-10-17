(() => {
  "use strict";
  const form = document.querySelector("form[data-identity-url]");
  const status = document.getElementById("staff-identity-notice");
  if (!form || !status) return;
  const nameField = form.querySelector('[name="name"]');
  const skuField = form.querySelector('[name="sku"]');
  if (!nameField || !skuField) return;
  let timeout, controller, revision = 0;
  const display = text => status.replaceChildren(document.createTextNode(text));
  const query = async () => {
    controller?.abort();
    const version = ++revision;
    const name = nameField.value.trim(), sku = skuField.value.trim();
    if (name.length < 3 && !sku) {
      display("Enter a name or SKU to check for existing catalogue records.");
      return;
    }
    controller = new AbortController();
    const params = new URLSearchParams({name, sku});
    if (form.dataset.identityId) params.set("product_id", form.dataset.identityId);
    try {
      const response = await fetch(form.dataset.identityUrl + "?" + params,
        {signal: controller.signal, credentials: "same-origin"});
      if (!response.ok) throw new Error("Unable to check duplicates");
      const data = await response.json();
      if (version !== revision) return;
      const matches = Array.isArray(data.name_matches) ? data.name_matches : [];
      const conflict = data.sku_conflict;
      if (!matches.length && !conflict) {
        display("No exact duplicate found. Continue editing.");
        return;
      }
      status.replaceChildren();
      const title = document.createElement("strong");
      title.textContent = conflict ? "SKU already in use. Choose another SKU."
        : "Existing listing found. Check before creating another.";
      status.append(title);
      const list = document.createElement("ul");
      list.className = "mb-0 mt-2";
      const items = [
        ...(conflict ? [{...conflict, type: "SKU"}] : []),
        ...matches.map(row => ({...row, type: "Name"}))
      ];
      items.slice(0, 6).forEach(row => {
        const li = document.createElement("li"), a = document.createElement("a");
        a.href = row.url;
        a.textContent = row.type + ": " + row.name + (row.sku ? " (" + row.sku + ")" : "");
        li.append(a); list.append(li);
      });
      status.append(list);
    } catch (error) {
      if (error.name !== "AbortError" && version === revision) {
        display("Suggestions unavailable. SKU validation still runs when saving.");
      }
    }
  };
  const schedule = () => { clearTimeout(timeout); timeout = setTimeout(query, 350); };
  nameField.addEventListener("input", schedule);
  skuField.addEventListener("input", schedule);
  if (form.dataset.identityId) query();
})();