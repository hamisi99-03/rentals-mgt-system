/* Theme application: instant switching without reload, brand colour override. */
(function () {
  "use strict";

  var root = document.documentElement;
  var darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function resolveMode(mode) {
    if (mode === "system") {
      return darkQuery.matches ? "dark" : "light";
    }
    return mode === "dark" ? "dark" : "light";
  }

  function readTheme() {
    return {
      mode: root.dataset.themeMode || root.dataset.mode || "system",
      palette: root.dataset.palette || "ocean",
      density: root.dataset.density || "comfortable",
      textSize: root.dataset.textSize || "medium"
    };
  }

  function applyTheme(theme) {
    root.dataset.themeMode = theme.mode;
    root.dataset.mode = resolveMode(theme.mode);
    root.dataset.palette = theme.palette;
    root.dataset.density = theme.density;
    root.dataset.textSize = theme.textSize;
    document.dispatchEvent(new CustomEvent("themechange", { detail: theme }));
  }

  function parseHex(hex) {
    if (!hex) return null;
    var value = hex.trim().replace(/^#/, "");
    if (value.length === 3) {
      value = value[0] + value[0] + value[1] + value[1] + value[2] + value[2];
    }
    if (!/^[0-9a-fA-F]{6}$/.test(value)) return null;
    return [
      parseInt(value.slice(0, 2), 16),
      parseInt(value.slice(2, 4), 16),
      parseInt(value.slice(4, 6), 16)
    ];
  }

  function channelLuminance(channel) {
    var c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  function luminance(rgb) {
    return (
      0.2126 * channelLuminance(rgb[0]) +
      0.7152 * channelLuminance(rgb[1]) +
      0.0722 * channelLuminance(rgb[2])
    );
  }

  function contrastRatio(a, b) {
    var l1 = luminance(a);
    var l2 = luminance(b);
    var lighter = Math.max(l1, l2);
    var darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function applyBrand(brand) {
    var rgb = parseHex(brand);
    if (!rgb) {
      root.style.removeProperty("--accent");
      root.style.removeProperty("--accent-contrast");
      return;
    }
    var styles = getComputedStyle(root);
    var light = styles.getPropertyValue("--on-accent-light").trim();
    var dark = styles.getPropertyValue("--on-accent-dark").trim();
    var lightRgb = parseHex(light);
    var darkRgb = parseHex(dark);
    if (!lightRgb || !darkRgb) return;
    var text = contrastRatio(rgb, lightRgb) >= contrastRatio(rgb, darkRgb) ? light : dark;
    root.style.setProperty("--accent", brand);
    root.style.setProperty("--accent-contrast", text);
  }

  function updateSaveState(message, isError) {
    var status = document.getElementById("theme-save-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("text-danger", !!isError);
    status.classList.toggle("text-faint", !isError);
  }

  function saveTheme(theme) {
    var endpoint = root.dataset.themeEndpoint;
    if (!endpoint) return;
    var token = document.querySelector('meta[name="csrf-token"]');
    var headers = { "Content-Type": "application/json" };
    if (token) headers["X-CSRFToken"] = token.content;
    fetch(endpoint, {
      method: "POST",
      headers: headers,
      credentials: "same-origin",
      body: JSON.stringify(theme)
    })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        updateSaveState("Appearance saved", false);
      })
      .catch(function () {
        updateSaveState("Could not save appearance. Use Save.", true);
      });
  }

  function initAppearance() {
    var controls = document.querySelectorAll("[data-theme-control]");
    if (!controls.length) return;

    controls.forEach(function (control) {
      control.addEventListener("change", function () {
        var theme = readTheme();
        var key = control.dataset.themeControl;
        if (key === "mode") theme.mode = control.value;
        if (key === "palette") theme.palette = control.value;
        if (key === "density") theme.density = control.value;
        if (key === "text_size") theme.textSize = control.value;
        applyTheme(theme);
        applyBrand(root.dataset.brandColor);
        saveTheme(theme);
      });
    });
  }

  darkQuery.addEventListener("change", function () {
    if (readTheme().mode === "system") {
      root.dataset.mode = resolveMode("system");
      document.dispatchEvent(new CustomEvent("themechange", { detail: readTheme() }));
    }
  });

  window.AppTheme = {
    apply: applyTheme,
    applyBrand: applyBrand,
    read: readTheme,
    save: saveTheme
  };

  applyTheme(readTheme());
  if (root.dataset.brandColor) {
    applyBrand(root.dataset.brandColor);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAppearance);
  } else {
    initAppearance();
  }
})();
