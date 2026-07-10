/*
 * TWTF Tool Engine — shared calculator runtime.
 * Reads a JSON config embedded per-tool (see layouts/partials/tools/calculator.html),
 * computes a cost estimate generically, and reports GA4 events. New calculators
 * plug in by adding a data/tools/<id>.json config; this file does not change.
 */
(function () {
  "use strict";

  function fmtMoney(value, currency) {
    var symbol = !currency || currency === "USD" ? "$" : "";
    return symbol + Math.round(value).toLocaleString("en-US");
  }

  function gaEvent(name, params) {
    if (typeof window.gtag === "function") {
      window.gtag("event", name, params || {});
    }
  }

  function clamp(value, min, max) {
    if (typeof min === "number") value = Math.max(min, value);
    if (typeof max === "number") value = Math.min(max, value);
    return value;
  }

  function computeEstimate(config, values) {
    var total = 0;
    var multiplier = 1;
    var breakdown = [];

    if (config.base_fee) {
      total += config.base_fee;
      breakdown.push({ label: "Base fee", amount: config.base_fee });
    }

    if (config.distance_field) {
      var f = config.distance_field;
      var distance = clamp(Number(values[f.id]) || 0, f.min, f.max);
      var distanceCost = distance * (config.per_mile_rate || 0);
      if (config.per_mile_rate) {
        total += distanceCost;
        breakdown.push({ label: distance + " miles × $" + config.per_mile_rate + "/mi", amount: distanceCost });
      }
    }

    (config.select_fields || []).forEach(function (field) {
      var option = (field.options || []).filter(function (o) { return o.value === values[field.id]; })[0];
      if (!option) return;
      if (typeof option.fee === "number" && option.fee !== 0) {
        total += option.fee;
        breakdown.push({ label: field.label + ": " + option.label, amount: option.fee });
      }
      if (typeof option.multiplier === "number" && option.multiplier !== 1) {
        multiplier *= option.multiplier;
        breakdown.push({ label: field.label + ": " + option.label, multiplier: option.multiplier });
      }
    });

    (config.toggle_fields || []).forEach(function (field) {
      if (values[field.id]) {
        total += field.fee;
        breakdown.push({ label: field.label, amount: field.fee });
      }
    });

    total *= multiplier;

    if (config.storage_field) {
      var sf = config.storage_field;
      var days = clamp(Number(values[sf.id]) || 0, 0, sf.max);
      var storageTotal = days * sf.per_day;
      if (storageTotal > 0) {
        total += storageTotal;
        breakdown.push({ label: days + " storage day(s) × $" + sf.per_day + "/day", amount: storageTotal });
      }
    }

    var range = config.range || { low_multiplier: 0.85, high_multiplier: 1.25, min_spread: 35 };
    var low = total * range.low_multiplier;
    var high = Math.max(low + range.min_spread, total * range.high_multiplier);

    return { total: total, low: low, high: high, breakdown: breakdown };
  }

  function readValues(root) {
    var values = {};
    root.querySelectorAll("[data-field]").forEach(function (el) {
      var id = el.getAttribute("data-field");
      values[id] = el.type === "checkbox" ? el.checked : el.value;
    });
    return values;
  }

  function render(root, config, result) {
    var rangeEl = root.querySelector("[data-result-range]");
    var breakdownEl = root.querySelector("[data-result-breakdown]");
    if (rangeEl) {
      rangeEl.textContent = fmtMoney(result.low, config.currency) + " – " + fmtMoney(result.high, config.currency);
    }
    if (breakdownEl) {
      breakdownEl.innerHTML = "";
      result.breakdown.forEach(function (line) {
        var li = document.createElement("li");
        if (typeof line.amount === "number") {
          li.textContent = line.label + ": +" + fmtMoney(line.amount, config.currency);
        } else if (line.multiplier) {
          li.textContent = line.label + " (×" + line.multiplier + ")";
        } else {
          li.textContent = line.label;
        }
        breakdownEl.appendChild(li);
      });
    }
  }

  function initCalculator(root) {
    var configEl = root.querySelector("[data-tool-config]");
    if (!configEl) return;
    var config;
    try {
      config = JSON.parse(configEl.textContent);
    } catch (e) {
      return;
    }

    var toolId = config.id || root.getAttribute("data-tool-engine") || "tool";
    var openFired = false;
    var completeFired = false;

    function fireOpen() {
      if (openFired) return;
      openFired = true;
      gaEvent("calculator_open", { tool_id: toolId });
    }

    function update() {
      var values = readValues(root);
      var result = computeEstimate(config, values);
      render(root, config, result);
      gaEvent("estimate_generated", { tool_id: toolId });
      if (!completeFired) {
        completeFired = true;
        gaEvent("calculator_complete", { tool_id: toolId });
      }
    }

    root.querySelectorAll("[data-field]").forEach(function (el) {
      el.addEventListener("focus", fireOpen, { once: true });
      el.addEventListener("input", function () {
        fireOpen();
        update();
      });
      el.addEventListener("change", function () {
        gaEvent("field_change", { tool_id: toolId, field_id: el.getAttribute("data-field") });
      });
    });

    update();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var roots = document.querySelectorAll("[data-tool-engine]");
    if (!roots.length) return;

    roots.forEach(initCalculator);

    var primaryToolId = roots[0].getAttribute("data-tool-engine") || "tool";
    document.querySelectorAll(".related-guides a").forEach(function (a) {
      a.addEventListener("click", function () {
        gaEvent("related_article_click", { tool_id: primaryToolId, href: a.getAttribute("href") });
      });
    });
  });
})();
