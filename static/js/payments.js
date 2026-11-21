/* Live allocation preview for the payment form. */
(function () {
  "use strict";

  var form = document.querySelector("[data-payment-form]");
  if (!form) return;

  var endpoint = form.dataset.previewUrl;
  var currency = form.dataset.currency || "";
  var body = document.getElementById("allocation-body");
  var creditEl = document.getElementById("allocation-credit");
  var summaryEl = form.querySelector("[data-tenant-summary]");
  var summaryUnits = form.querySelector("[data-summary-units]");
  var summaryRent = form.querySelector("[data-summary-rent]");
  var summaryOutstanding = form.querySelector("[data-summary-outstanding]");
  var summaryInvoices = form.querySelector("[data-summary-invoices]");
  var tenant = form.querySelector('[name="tenant"]');
  var amount = form.querySelector('[name="amount"]');
  var withholding = form.querySelector('[name="withholding_amount"]');
  var hasWithholding = form.querySelector('[name="has_withholding"]');
  var timer = null;

  function money(value) {
    var number = Number(value || 0);
    return currency + " " + number.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function displayDate(value) {
    var date = new Date(value + "T00:00:00");
    if (isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
  }

  function renderSummary(summary) {
    if (!summaryEl) return;
    if (!summary) {
      summaryEl.style.display = "none";
      return;
    }
    summaryEl.style.display = "";
    if (summaryUnits) summaryUnits.textContent = summary.units;
    if (summaryRent) summaryRent.textContent = money(summary.monthly_rent);
    if (summaryOutstanding) {
      summaryOutstanding.textContent = money(summary.outstanding);
    }
    if (summaryInvoices) summaryInvoices.textContent = summary.open_invoices;
  }

  function emptyRow(message) {
    var row = document.createElement("tr");
    var cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "table-empty";
    cell.textContent = message;
    row.appendChild(cell);
    return row;
  }

  function render(data) {
    renderSummary(data.summary);
    body.innerHTML = "";
    if (!data.allocations.length) {
      body.appendChild(
        emptyRow("No open invoices; the whole amount becomes credit.")
      );
    } else {
      data.allocations.forEach(function (allocation) {
        var row = document.createElement("tr");

        var invoiceCell = document.createElement("td");
        var link = document.createElement("a");
        link.className = "table-link";
        link.target = "_blank";
        link.rel = "noopener";
        link.href = "/billing/invoices/" + allocation.invoice_id + "/";
        link.textContent = allocation.invoice_number;
        invoiceCell.appendChild(link);

        var dueCell = document.createElement("td");
        dueCell.className = "nowrap";
        dueCell.textContent = displayDate(allocation.due_date);

        var balanceCell = document.createElement("td");
        balanceCell.className = "is-numeric";
        balanceCell.textContent = money(allocation.balance);

        var amountCell = document.createElement("td");
        amountCell.className = "is-numeric";
        var input = document.createElement("input");
        input.className = "input allocation-input";
        input.type = "number";
        input.step = "0.01";
        input.min = "0";
        input.name = "allocation_" + allocation.invoice_id;
        input.value = allocation.amount;
        input.setAttribute("aria-label", "Allocate to " + allocation.invoice_number);
        amountCell.appendChild(input);

        row.appendChild(invoiceCell);
        row.appendChild(dueCell);
        row.appendChild(balanceCell);
        row.appendChild(amountCell);
        body.appendChild(row);
      });
    }
    creditEl.textContent = money(data.credit);
  }

  function refresh() {
    if (!tenant.value) {
      if (summaryEl) summaryEl.style.display = "none";
      body.innerHTML = "";
      body.appendChild(
        emptyRow("Choose a tenant and amount to see invoices.")
      );
      creditEl.textContent = money(0);
      return;
    }
    var params = new URLSearchParams({
      tenant: tenant.value,
      amount: amount.value || "0",
      withholding_amount: withholding.value || "0",
      has_withholding: hasWithholding && hasWithholding.checked ? "on" : ""
    });
    fetch(endpoint + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("preview failed");
        return response.json();
      })
      .then(render)
      .catch(function () {
        /* keep the server-rendered preview on failure */
      });
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(refresh, 250);
  }

  [tenant, amount, withholding, hasWithholding].forEach(function (control) {
    if (!control) return;
    control.addEventListener("input", schedule);
    control.addEventListener("change", schedule);
  });
})();
