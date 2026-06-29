document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('document-form');
  var primarySave = document.getElementById('primary-save-button');
  var secondarySave = document.getElementById('secondary-save-button');

  if (!form || !primarySave || !secondarySave) {
    return;
  }

  if (!document.getElementById('download-pdf-save-button')) {
    var downloadButton = document.createElement('button');
    downloadButton.type = 'submit';
    downloadButton.name = 'save_action';
    downloadButton.value = 'pdf';
    downloadButton.id = 'download-pdf-save-button';
    downloadButton.className = 'btn btn-success';
    downloadButton.textContent = primarySave.textContent.indexOf('Create') !== -1
      ? 'Create and download PDF'
      : 'Save and download PDF';
    secondarySave.insertAdjacentElement('afterend', downloadButton);
  }

  var customerSelect = document.getElementById('id_customer');
  var customerName = document.getElementById('id_customer_name');
  var errorSummaryId = 'document-client-error-summary';

  function activeLineRows() {
    return Array.prototype.slice.call(form.querySelectorAll('tr.line-form-row')).filter(function (row) {
      var deleteBox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
      return !(deleteBox && deleteBox.checked);
    });
  }

  function fieldValue(row, suffix) {
    var field = row.querySelector('[name$="-' + suffix + '"]');
    return field ? field.value.trim() : '';
  }

  function fieldBySuffix(row, suffix) {
    return row.querySelector('[name$="-' + suffix + '"]');
  }

  function markInvalid(field, message) {
    if (!field) {
      return;
    }
    field.classList.add('is-invalid');
    field.setAttribute('aria-invalid', 'true');

    var feedback = field.parentElement.querySelector('.client-invalid-feedback[data-for="' + field.name + '"]');
    if (!feedback) {
      feedback = document.createElement('div');
      feedback.className = 'invalid-feedback d-block client-invalid-feedback';
      feedback.dataset.for = field.name;
      field.insertAdjacentElement('afterend', feedback);
    }
    feedback.textContent = message;
  }

  function clearClientErrors() {
    var summary = document.getElementById(errorSummaryId);
    if (summary) {
      summary.remove();
    }
    Array.prototype.forEach.call(form.querySelectorAll('.is-invalid'), function (field) {
      field.classList.remove('is-invalid');
      field.removeAttribute('aria-invalid');
    });
    Array.prototype.forEach.call(form.querySelectorAll('.client-invalid-feedback'), function (node) {
      node.remove();
    });
  }

  function showErrorSummary(errors) {
    var existing = document.getElementById(errorSummaryId);
    if (existing) {
      existing.remove();
    }

    var summary = document.createElement('div');
    summary.id = errorSummaryId;
    summary.className = 'alert alert-danger border-danger shadow-sm';
    summary.setAttribute('role', 'alert');
    summary.setAttribute('tabindex', '-1');

    var title = document.createElement('h2');
    title.className = 'h5';
    title.textContent = 'There is a problem';
    summary.appendChild(title);

    var help = document.createElement('p');
    help.className = 'mb-2';
    help.textContent = 'The document has not been saved yet. Correct the items below and press the save button again.';
    summary.appendChild(help);

    var list = document.createElement('ul');
    list.className = 'mb-0';
    errors.forEach(function (error) {
      var item = document.createElement('li');
      var link = document.createElement('a');
      link.href = '#' + error.field.id;
      link.textContent = error.message;
      link.addEventListener('click', function (event) {
        event.preventDefault();
        error.field.focus({ preventScroll: true });
        error.field.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      item.appendChild(link);
      list.appendChild(item);
    });
    summary.appendChild(list);

    form.insertAdjacentElement('afterbegin', summary);
    summary.focus({ preventScroll: true });
    summary.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function ensureWalkInName() {
    if (customerSelect && customerName && !customerSelect.value && !customerName.value.trim()) {
      customerName.value = 'Walk-in customer';
    }
  }

  function isCommissionSource(sourceType) {
    return sourceType === 'external' || sourceType === 'consignment';
  }

  function isOutsourcedServiceSource(sourceType) {
    return sourceType === 'service';
  }

  function refreshCommissionHints() {
    activeLineRows().forEach(function (row) {
      var sourceField = fieldBySuffix(row, 'source_type');
      var unitCostField = fieldBySuffix(row, 'unit_cost');
      var supplierField = fieldBySuffix(row, 'supplier_name');
      if (!sourceField || !unitCostField || !supplierField) {
        return;
      }

      var hint = row.querySelector('.commission-line-hint');
      if (isCommissionSource(sourceField.value)) {
        unitCostField.placeholder = 'Neighbor / owner price';
        supplierField.placeholder = 'Neighbor or owner name';
        if (!hint) {
          hint = document.createElement('div');
          hint.className = 'small text-success mt-2 commission-line-hint';
          sourceField.insertAdjacentElement('afterend', hint);
        }
        hint.textContent = 'Commission item: reports count only your markup as business income. Put the neighbor/owner price in Unit cost.';
      } else if (isOutsourcedServiceSource(sourceField.value)) {
        unitCostField.placeholder = 'Subcontractor fee';
        supplierField.placeholder = 'Technician / subcontractor name';
        if (!hint) {
          hint = document.createElement('div');
          hint.className = 'small text-success mt-2 commission-line-hint';
          sourceField.insertAdjacentElement('afterend', hint);
        }
        hint.textContent = 'Outsourced service: enter the subcontractor name and fee only when someone else will execute this service. Reports will count only your balance as recognised income.';
      } else if (hint) {
        hint.remove();
      }
    });
  }

  function validateDocumentBeforeSubmit() {
    clearClientErrors();
    ensureWalkInName();
    refreshCommissionHints();

    var errors = [];
    var validLineFound = false;

    activeLineRows().forEach(function (row) {
      var descriptionField = fieldBySuffix(row, 'description');
      var quantityField = fieldBySuffix(row, 'quantity');
      var priceField = fieldBySuffix(row, 'unit_price');
      var sourceField = fieldBySuffix(row, 'source_type');
      var costField = fieldBySuffix(row, 'unit_cost');
      var supplierField = fieldBySuffix(row, 'supplier_name');

      var description = fieldValue(row, 'description');
      var quantity = Number(fieldValue(row, 'quantity'));
      var priceRaw = fieldValue(row, 'unit_price');
      var price = Number(priceRaw);
      var sourceType = sourceField ? sourceField.value : '';
      var costRaw = fieldValue(row, 'unit_cost');
      var cost = Number(costRaw);
      var supplier = fieldValue(row, 'supplier_name');
      var hasAnyLineValue = description || fieldValue(row, 'product') || fieldValue(row, 'product_variant') || fieldValue(row, 'quantity') || priceRaw;
      var hasOutsourcedServiceDetails = isOutsourcedServiceSource(sourceType) && (supplier || (costRaw !== '' && cost > 0));

      if (description && quantity > 0 && priceRaw !== '' && price >= 0) {
        validLineFound = true;
      }

      if (hasAnyLineValue) {
        if (!description) {
          errors.push({ field: descriptionField, message: 'Enter an item or service description.' });
          markInvalid(descriptionField, 'Enter an item or service description.');
        }
        if (!(quantity > 0)) {
          errors.push({ field: quantityField, message: 'Enter a quantity greater than zero.' });
          markInvalid(quantityField, 'Enter a quantity greater than zero.');
        }
        if (priceRaw === '' || !(price >= 0)) {
          errors.push({ field: priceField, message: 'Enter a unit price of zero or more.' });
          markInvalid(priceField, 'Enter a unit price of zero or more.');
        }
        if (isCommissionSource(sourceType)) {
          if (!supplier) {
            errors.push({ field: supplierField, message: 'Enter the neighbor or owner name for commission items.' });
            markInvalid(supplierField, 'Enter the neighbor or owner name.');
          }
          if (costRaw === '' || !(cost >= 0)) {
            errors.push({ field: costField, message: 'Enter the neighbor or owner price in Unit cost.' });
            markInvalid(costField, 'Enter the neighbor or owner price.');
          }
          if (priceRaw !== '' && costRaw !== '' && price < cost) {
            errors.push({ field: priceField, message: 'Selling price is below the neighbor price; this creates a loss.' });
            markInvalid(priceField, 'Selling price is below the neighbor price.');
          }
        }
        if (hasOutsourcedServiceDetails) {
          if (!supplier) {
            errors.push({ field: supplierField, message: 'Enter the technician or subcontractor name for outsourced services.' });
            markInvalid(supplierField, 'Enter the technician or subcontractor name.');
          }
          if (costRaw === '' || !(cost > 0)) {
            errors.push({ field: costField, message: 'Enter the subcontractor fee in Unit cost.' });
            markInvalid(costField, 'Enter the subcontractor fee.');
          }
          if (priceRaw !== '' && costRaw !== '' && price < cost) {
            errors.push({ field: priceField, message: 'Service charge is below the subcontractor fee; this creates a loss.' });
            markInvalid(priceField, 'Service charge is below the subcontractor fee.');
          }
        }
      }
    });

    if (!validLineFound) {
      var firstDescription = form.querySelector('[name$="-description"]');
      var firstQuantity = form.querySelector('[name$="-quantity"]');
      var firstPrice = form.querySelector('[name$="-unit_price"]');
      errors.push({ field: firstDescription, message: 'Add at least one complete line item before saving.' });
      markInvalid(firstDescription, 'Add at least one complete line item before saving.');
      markInvalid(firstQuantity, 'Quantity is required.');
      markInvalid(firstPrice, 'Unit price is required.');
    }

    errors = errors.filter(function (error) { return error.field; });
    if (errors.length) {
      showErrorSummary(errors);
      return false;
    }
    return true;
  }

  form.addEventListener('change', refreshCommissionHints);
  refreshCommissionHints();

  form.addEventListener('submit', function (event) {
    if (!validateDocumentBeforeSubmit()) {
      event.preventDefault();
      event.stopPropagation();
    }
  });
});
