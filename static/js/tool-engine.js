/*
 * TWTF Tool Engine — shared calculator runtime.
 *
 * Reads a JSON config embedded per-tool (see layouts/partials/tools/calculator.html),
 * computes a cost estimate generically, renders the "roadside coach" result
 * sections (confidence, factor explanations, phone script), and reports GA4
 * events. A future tool plugs in with a new data/tools/<id>.json config —
 * this file does not change.
 *
 * Config contract (all optional except id):
 *   id, currency, base_fee, per_mile_rate
 *   distance_field   { id, label, min, max, default, help }
 *   select_fields[]  { id, label, help, options: [{ value, label, fee?, multiplier?, variability? }] }
 *   toggle_fields[]  { id, label, fee, variability? }
 *   storage_field    { id, label, min, max, default, per_day, help, variability? }
 *   range            { low_multiplier, high_multiplier, min_spread }
 *   confidence_thresholds { high_max, moderate_max }  — sum of active "variability" weights
 *   factor_explanations   { <field_id>: "why this factor moves the price" }
 *   savings_tips[], common_mistakes[], before_tow_checklist[]  — static, rendered server-side
 *   phone_script     { intro, lines[] }  — lines may include {field_id_label} tokens
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

  function selectedOption(field, values) {
    return (field.options || []).filter(function (o) { return o.value === values[field.id]; })[0];
  }

  // Lowercase a label for mid-sentence use, but leave real acronyms alone
  // ("RV, motorhome, or trailer" should stay "RV...", not become "rV...").
  function toMidSentence(label) {
    var firstWord = (label.match(/^[A-Za-z]+/) || [""])[0];
    var isAcronym = firstWord.length > 1 && firstWord === firstWord.toUpperCase();
    return isAcronym ? label : label.charAt(0).toLowerCase() + label.slice(1);
  }

  // ---- Estimate math -------------------------------------------------------

  function computeEstimate(config, values) {
    var total = 0;
    var multiplier = 1;
    var breakdown = [];

    if (config.base_fee) {
      total += config.base_fee;
      breakdown.push({ label: "Base fee", amount: config.base_fee });
    }

    if (config.distance_field && config.per_mile_rate) {
      var f = config.distance_field;
      var distance = clamp(Number(values[f.id]) || 0, f.min, f.max);
      var distanceCost = distance * config.per_mile_rate;
      total += distanceCost;
      breakdown.push({ label: distance + " miles × $" + config.per_mile_rate + "/mi", amount: distanceCost });
    }

    (config.select_fields || []).forEach(function (field) {
      var option = selectedOption(field, values);
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

  // ---- Confidence: how many "variability" points are active -----------------

  var CONFIDENCE_COPY = {
    high: { emoji: "🟢", label: "High confidence", text: "This estimate is based on common pricing and should be fairly accurate." },
    moderate: { emoji: "🟡", label: "Moderate confidence", text: "Pricing varies depending on a few conditions here — ask the questions below before agreeing to anything." },
    low: { emoji: "🔴", label: "Lower confidence", text: "Your situation has several variables that affect price. Expect a wider range, and read the checklist before agreeing to anything." }
  };

  function computeConfidence(config, values) {
    var score = 0;
    (config.select_fields || []).forEach(function (field) {
      var option = selectedOption(field, values);
      if (option && typeof option.variability === "number") score += option.variability;
    });
    (config.toggle_fields || []).forEach(function (field) {
      if (values[field.id] && typeof field.variability === "number") score += field.variability;
    });
    if (config.storage_field && typeof config.storage_field.variability === "number") {
      var days = Number(values[config.storage_field.id]) || 0;
      if (days > 0) score += config.storage_field.variability;
    }
    var t = config.confidence_thresholds || { high_max: 0, moderate_max: 2 };
    var level = score <= t.high_max ? "high" : score <= t.moderate_max ? "moderate" : "low";
    return Object.assign({ level: level, score: score }, CONFIDENCE_COPY[level]);
  }

  // ---- Field-value reading + DOM rendering -----------------------------------

  function readValues(root) {
    var values = {};
    root.querySelectorAll("[data-field]").forEach(function (el) {
      var id = el.getAttribute("data-field");
      values[id] = el.type === "checkbox" ? el.checked : el.value;
    });
    return values;
  }

  function renderResult(root, config, result) {
    var rangeEl = root.querySelector("[data-result-range]");
    var likelyEl = root.querySelector("[data-result-likely]");
    var breakdownEl = root.querySelector("[data-result-breakdown]");

    if (rangeEl) rangeEl.textContent = fmtMoney(result.low, config.currency) + " – " + fmtMoney(result.high, config.currency);
    if (likelyEl) likelyEl.textContent = "Likely around " + fmtMoney(result.total, config.currency);

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

  function renderConfidence(root, confidence) {
    var el = root.querySelector("[data-result-confidence]");
    if (!el) return;
    el.className = "calc-confidence calc-confidence--" + confidence.level;
    el.setAttribute("role", "status");
    el.innerHTML = "";

    var emoji = document.createElement("span");
    emoji.className = "calc-confidence__emoji";
    emoji.setAttribute("aria-hidden", "true");
    emoji.textContent = confidence.emoji;

    var text = document.createElement("span");
    var strong = document.createElement("strong");
    strong.textContent = confidence.label;
    text.appendChild(strong);
    text.appendChild(document.createTextNode(" — " + confidence.text));

    el.appendChild(emoji);
    el.appendChild(text);
  }

  function renderFactors(root, config, values) {
    var container = root.querySelector("[data-result-factors]");
    if (!container) return;
    var explanations = config.factor_explanations || {};
    var items = [];

    if (config.distance_field && explanations[config.distance_field.id]) {
      items.push({ label: config.distance_field.label, text: explanations[config.distance_field.id] });
    }
    (config.select_fields || []).forEach(function (field) {
      if (explanations[field.id]) items.push({ label: field.label, text: explanations[field.id] });
    });
    (config.toggle_fields || []).forEach(function (field) {
      if (values[field.id] && explanations[field.id]) items.push({ label: field.label, text: explanations[field.id] });
    });
    if (config.storage_field && explanations[config.storage_field.id]) {
      var days = Number(values[config.storage_field.id]) || 0;
      if (days > 0) items.push({ label: config.storage_field.label, text: explanations[config.storage_field.id] });
    }

    container.innerHTML = "";
    items.forEach(function (item) {
      var li = document.createElement("li");
      var strong = document.createElement("strong");
      strong.textContent = item.label + ": ";
      li.appendChild(strong);
      li.appendChild(document.createTextNode(item.text));
      container.appendChild(li);
    });
  }

  function renderPhoneScript(root, config, values) {
    var container = root.querySelector("[data-phone-script]");
    if (!container || !config.phone_script) return;
    container.innerHTML = "";
    (config.phone_script.lines || []).forEach(function (line) {
      var text = line.replace(/\{(\w+)_label\}/g, function (match, fieldId) {
        var field = (config.select_fields || []).filter(function (f) { return f.id === fieldId; })[0];
        var option = field && selectedOption(field, values);
        if (!option) return match;
        return toMidSentence(option.label);
      });
      var li = document.createElement("li");
      li.textContent = text;
      container.appendChild(li);
    });
  }

  function pulse(el) {
    if (!el) return;
    el.classList.remove("is-updating");
    void el.offsetWidth; // force reflow so the animation restarts on repeat updates
    el.classList.add("is-updating");
  }

  // ---- Wiring ----------------------------------------------------------------

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
    var resultEl = root.querySelector(".calc-result");

    function computeAndRender() {
      var values = readValues(root);
      var result = computeEstimate(config, values);
      renderResult(root, config, result);
      renderConfidence(root, computeConfidence(config, values));
      renderFactors(root, config, values);
      renderPhoneScript(root, config, values);
      return result;
    }

    function fireOpen() {
      if (openFired) return;
      openFired = true;
      gaEvent("calculator_open", { tool_id: toolId });
    }

    function handleUserUpdate() {
      computeAndRender();
      pulse(resultEl);
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
        handleUserUpdate();
      });
      el.addEventListener("change", function () {
        gaEvent("field_change", { tool_id: toolId, field_id: el.getAttribute("data-field") });
      });
    });

    // Render the default estimate immediately (no blank state, no wait) —
    // but don't count a page load as "the user opened/completed" the tool.
    computeAndRender();
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
