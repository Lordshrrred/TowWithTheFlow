/*
 * TWTF Tool Engine — shared runtime for every roadside tool.
 *
 * Two tool "kinds" share this one file:
 *   - "calculator"     (config.kind absent or "calculator") — live cost math
 *                        from simultaneous fields. See computeEstimate().
 *   - "decision-tool"  (config.kind === "decision-tool") — one branching
 *                        question at a time, ending at a fixed recommendation.
 *                        See initDecisionTool().
 *
 * Both kinds render into the SAME shared "Roadside Action Plan" DOM hooks
 * (confidence, factors, phone script, mistakes, checklist, next action) via
 * the generic render* functions below — a new tool of either kind plugs in
 * with a new data/tools/<id>.json config; this file does not change.
 *
 * Calculator config contract (all optional except id):
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
 *
 * Decision-tool config contract:
 *   id, kind: "decision-tool", start (question id)
 *   questions: { <id>: { text, options: [{ value, label, next }] } }
 *     — next is either another question id, or "result:<result id>"
 *   results: { <id>: {
 *     result_type, title, summary, confidence ("high"|"moderate"|"low"), confidence_text,
 *     not_to_do[], before_help_checklist[], phone_script { intro, lines[] }, next_action
 *   } }
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

  // ============================================================================
  // Shared "Roadside Action Plan" renderers — used by both calculator and
  // decision-tool. Each takes plain data (never reads config/state itself),
  // so either tool kind can build that data its own way and share the render.
  // ============================================================================

  var CONFIDENCE_COPY = {
    high: { emoji: "🟢", label: "High confidence", text: "This estimate is based on common pricing and should be fairly accurate." },
    moderate: { emoji: "🟡", label: "Moderate confidence", text: "Pricing varies depending on a few conditions here — ask the questions below before agreeing to anything." },
    low: { emoji: "🔴", label: "Lower confidence", text: "Your situation has several variables that affect price. Expect a wider range, and read the checklist before agreeing to anything." }
  };

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

  function toggleSection(container, hasContent) {
    if (!container) return;
    var section = container.closest("[data-plan-section]");
    if (section) section.hidden = !hasContent;
  }

  // items: [{ label, text }] — rendered as "<strong>label:</strong> text"
  function renderFactors(root, items) {
    var container = root.querySelector("[data-result-factors]");
    if (!container) return;
    container.innerHTML = "";
    (items || []).forEach(function (item) {
      var li = document.createElement("li");
      var strong = document.createElement("strong");
      strong.textContent = item.label + ": ";
      li.appendChild(strong);
      li.appendChild(document.createTextNode(item.text));
      container.appendChild(li);
    });
    toggleSection(container, (items || []).length > 0);
  }

  // Plain string list — reused for tips, mistakes/not-to-do, and checklists.
  function renderList(container, items) {
    if (!container) return;
    container.innerHTML = "";
    var list = items || [];
    list.forEach(function (text) {
      var li = document.createElement("li");
      li.textContent = text;
      container.appendChild(li);
    });
    toggleSection(container, list.length > 0);
  }

  function renderPhoneScript(root, intro, lines) {
    var introEl = root.querySelector("[data-script-intro]");
    var container = root.querySelector("[data-phone-script]");
    if (introEl) introEl.textContent = intro || "";
    if (!container) return;
    container.innerHTML = "";
    (lines || []).forEach(function (text) {
      var li = document.createElement("li");
      li.textContent = text;
      container.appendChild(li);
    });
    toggleSection(container, (lines || []).length > 0);
  }

  // mainText/secondaryText: the big headline + supporting line. breakdown is
  // calculator-only (itemized $ lines); pass null to leave it untouched/hidden.
  function renderResultSummary(root, currency, opts) {
    var mainEl = root.querySelector("[data-result-range]");
    var secondaryEl = root.querySelector("[data-result-likely]");
    var breakdownEl = root.querySelector("[data-result-breakdown]");

    if (mainEl) mainEl.textContent = opts.mainText;
    if (secondaryEl) secondaryEl.textContent = opts.secondaryText || "";

    if (breakdownEl) {
      breakdownEl.innerHTML = "";
      (opts.breakdown || []).forEach(function (line) {
        var li = document.createElement("li");
        if (typeof line.amount === "number") {
          li.textContent = line.label + ": +" + fmtMoney(line.amount, currency);
        } else if (line.multiplier) {
          li.textContent = line.label + " (×" + line.multiplier + ")";
        } else {
          li.textContent = line.label;
        }
        breakdownEl.appendChild(li);
      });
      toggleSection(breakdownEl, (opts.breakdown || []).length > 0);
    }
  }

  function pulse(el) {
    if (!el) return;
    el.classList.remove("is-updating");
    void el.offsetWidth; // force reflow so the animation restarts on repeat updates
    el.classList.add("is-updating");
  }

  // Shared by both tool kinds: lets someone paste the current phone script
  // into a text message or Notes app instead of re-typing it by hand.
  function initCopyScriptButton(root) {
    var btn = root.querySelector("[data-copy-script]");
    var container = root.querySelector("[data-phone-script]");
    if (!btn || !container) return;
    var originalLabel = btn.textContent;
    btn.addEventListener("click", function () {
      var lines = Array.prototype.map.call(container.querySelectorAll("li"), function (li) {
        return li.textContent;
      });
      if (!lines.length || !navigator.clipboard || !navigator.clipboard.writeText) return;
      navigator.clipboard.writeText(lines.join("\n")).then(function () {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = originalLabel; }, 1800);
      }).catch(function () {});
    });
  }

  // ============================================================================
  // Calculator: live estimate math from simultaneous fields
  // ============================================================================

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

  function calculatorFactorItems(config, values) {
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
    return items;
  }

  function resolveCalculatorTokens(line, config, values) {
    return line.replace(/\{(\w+)_label\}/g, function (match, fieldId) {
      var field = (config.select_fields || []).filter(function (f) { return f.id === fieldId; })[0];
      var option = field && selectedOption(field, values);
      return option ? toMidSentence(option.label) : match;
    });
  }

  function readValues(root) {
    var values = {};
    root.querySelectorAll("[data-field]").forEach(function (el) {
      var id = el.getAttribute("data-field");
      values[id] = el.type === "checkbox" ? el.checked : el.value;
    });
    return values;
  }

  // The state field's help text promises it "points you to the right local
  // rules and guides" — this is what actually delivers on that, instead of
  // the field silently doing nothing once picked.
  function renderStateNote(root, config, values) {
    var field = config.state_field;
    var note = root.querySelector("[data-state-note]");
    if (!field || !note || !field.law_link) return;
    var option = selectedOption(field, values);
    if (!option || option.generic) {
      note.hidden = true;
      return;
    }
    note.innerHTML = "";
    var link = document.createElement("a");
    link.href = field.law_link;
    link.textContent = (field.law_link_text || "See towing law basics for") + " " + option.label;
    note.appendChild(link);
    note.hidden = false;
  }

  function initCalculator(root, config) {
    var toolId = config.id || root.getAttribute("data-tool-engine") || "tool";
    var openFired = false;
    var completeFired = false;
    var resultEl = root.querySelector(".calc-result");

    function computeAndRender() {
      var values = readValues(root);
      var result = computeEstimate(config, values);
      renderResultSummary(root, config.currency, {
        mainText: fmtMoney(result.low, config.currency) + " – " + fmtMoney(result.high, config.currency),
        secondaryText: "Likely around " + fmtMoney(result.total, config.currency),
        breakdown: result.breakdown
      });
      renderConfidence(root, computeConfidence(config, values));
      renderFactors(root, calculatorFactorItems(config, values));
      renderStateNote(root, config, values);
      if (config.phone_script) {
        var lines = (config.phone_script.lines || []).map(function (line) {
          return resolveCalculatorTokens(line, config, values);
        });
        renderPhoneScript(root, config.phone_script.intro, lines);
      }
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

  // ============================================================================
  // Decision tool: one branching question at a time, ending at a fixed result
  // ============================================================================

  function confidenceFromResult(result) {
    var level = result.confidence || "moderate";
    var copy = CONFIDENCE_COPY[level] || CONFIDENCE_COPY.moderate;
    return { level: level, emoji: copy.emoji, label: copy.label, text: result.confidence_text || copy.text };
  }

  function initDecisionTool(root, config) {
    var toolId = config.id || root.getAttribute("data-tool-engine") || "tool";
    var flowEl = root.querySelector("[data-question-container]");
    var flowWrap = root.querySelector("[data-decision-flow]");
    var progressEl = root.querySelector("[data-decision-progress]");
    var planEl = root.querySelector("[data-roadside-plan]");
    var backBtn = root.querySelector("[data-decision-back]");
    var restartBtn = root.querySelector("[data-decision-restart]");
    if (!flowEl || !config.questions || !config.results) return;

    var path = []; // answers so far: { questionText, label }, for the "why" trail
    var questionStack = []; // question ids visited, for Back
    var openFired = false;

    function fireOpen() {
      if (openFired) return;
      openFired = true;
      gaEvent("tool_open", { tool_id: toolId });
      gaEvent("decision_started", { tool_id: toolId });
    }

    function renderQuestion(questionId) {
      var q = config.questions[questionId];
      if (!q) return;
      flowEl.innerHTML = "";

      if (progressEl) {
        progressEl.textContent = "Question " + (questionStack.length + 1);
      }

      var heading = document.createElement("h3");
      heading.className = "decision-step__question";
      heading.textContent = q.text;
      heading.setAttribute("tabindex", "-1");
      flowEl.appendChild(heading);

      var optionsWrap = document.createElement("div");
      optionsWrap.className = "decision-step__options";
      (q.options || []).forEach(function (opt) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "decision-option";
        btn.textContent = opt.label;
        btn.addEventListener("click", function () {
          fireOpen();
          questionStack.push(questionId);
          path.push({ questionText: q.text, label: opt.label });
          advance(opt.next);
        });
        optionsWrap.appendChild(btn);
      });
      flowEl.appendChild(optionsWrap);

      if (backBtn) backBtn.hidden = questionStack.length === 0;
      heading.focus();
    }

    function advance(next) {
      if (next.indexOf("result:") === 0) {
        showResult(next.slice("result:".length));
      } else {
        renderQuestion(next);
      }
    }

    function showResult(resultId) {
      var result = config.results[resultId];
      if (!result) return;

      if (flowWrap) flowWrap.hidden = true;
      if (planEl) planEl.hidden = false;

      renderConfidence(root, confidenceFromResult(result));
      renderResultSummary(root, config.currency, {
        mainText: result.title,
        secondaryText: result.summary,
        breakdown: null
      });
      renderFactors(root, path.map(function (step) {
        return { label: step.questionText, text: step.label };
      }));
      if (result.phone_script) {
        renderPhoneScript(root, result.phone_script.intro, result.phone_script.lines || []);
      }
      renderList(root.querySelector("[data-result-mistakes]"), result.not_to_do);
      renderList(root.querySelector("[data-result-checklist]"), result.before_help_checklist);
      var nextEl = root.querySelector("[data-result-next]");
      if (nextEl) nextEl.textContent = result.next_action || "";

      var planTitle = root.querySelector(".roadside-plan__title");
      if (planTitle) planTitle.focus();

      gaEvent("decision_completed", { tool_id: toolId, result_type: result.result_type });
    }

    function goBack() {
      if (!questionStack.length) return;
      path.pop();
      var prevId = questionStack.pop();
      renderQuestion(prevId);
    }

    function restart() {
      path = [];
      questionStack = [];
      if (planEl) planEl.hidden = true;
      if (flowWrap) flowWrap.hidden = false;
      renderQuestion(config.start);
    }

    if (backBtn) backBtn.addEventListener("click", goBack);
    if (restartBtn) restartBtn.addEventListener("click", restart);

    renderQuestion(config.start);
  }

  // ============================================================================
  // Wiring
  // ============================================================================

  function readToolConfig(root) {
    var configEl = root.querySelector("[data-tool-config]");
    if (!configEl) return null;
    try {
      return JSON.parse(configEl.textContent);
    } catch (e) {
      return null;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var roots = document.querySelectorAll("[data-tool-engine]");
    if (!roots.length) return;

    roots.forEach(function (root) {
      var config = readToolConfig(root);
      if (!config) return;
      if (config.kind === "decision-tool") {
        initDecisionTool(root, config);
      } else {
        initCalculator(root, config);
      }
      initCopyScriptButton(root);
    });

    var primaryRoot = roots[0];
    var primaryToolId = primaryRoot.getAttribute("data-tool-engine") || "tool";
    var isDecisionTool = primaryRoot.getAttribute("data-tool-kind") === "decision-tool";
    var clickEventName = isDecisionTool ? "related_resource_click" : "related_article_click";
    document.querySelectorAll(".related-guides a").forEach(function (a) {
      a.addEventListener("click", function () {
        gaEvent(clickEventName, { tool_id: primaryToolId, href: a.getAttribute("href") });
      });
    });
  });
})();
