/* Small UI helpers: dialogs, confirmations, flash messages, sidebar. */
(function () {
  "use strict";

  function openDialog(id) {
    var dialog = document.getElementById(id);
    if (dialog && typeof dialog.showModal === "function") {
      dialog.showModal();
    }
  }

  function closeDialog(dialog) {
    if (dialog && typeof dialog.close === "function") {
      dialog.close();
    }
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-dialog-open]");
    if (opener) {
      event.preventDefault();
      openDialog(opener.dataset.dialogOpen);
      return;
    }

    var closer = event.target.closest("[data-dialog-close]");
    if (closer) {
      event.preventDefault();
      closeDialog(closer.closest("dialog"));
      return;
    }

    var back = event.target.closest("[data-nav-back]");
    if (back) {
      event.preventDefault();
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.assign("/");
      }
      return;
    }

    var toggle = event.target.closest("[data-sidebar-toggle]");
    if (toggle) {
      event.preventDefault();
      var sidebar = document.querySelector(".sidebar");
      if (sidebar) sidebar.classList.toggle("is-open");
      return;
    }

    var menu = document.querySelector(".user-menu[open]");
    if (menu && !menu.contains(event.target)) {
      menu.removeAttribute("open");
    }

    var dismiss = event.target.closest("[data-flash-close]");
    if (dismiss) {
      var flash = dismiss.closest(".flash");
      if (flash) flash.remove();
    }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    var message = form.dataset.confirm;
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  document.querySelectorAll("dialog").forEach(function (dialog) {
    if (dialog.dataset.openOnLoad === "true") {
      openDialog(dialog.id);
    }
  });

  document.querySelectorAll(".flash").forEach(function (flash) {
    window.setTimeout(function () {
      flash.remove();
    }, 6500);
  });
})();

/* Idle lock: the server also enforces this on the next request. */
(function () {
  "use strict";

  var root = document.documentElement;
  var minutes = parseInt(root.dataset.idleMinutes || "0", 10);
  var lockUrl = root.dataset.lockUrl;
  var loginUrl = root.dataset.loginUrl;
  if (!minutes || !lockUrl || !loginUrl) return;

  var timer = null;
  var last = 0;

  function lock() {
    var token = document.querySelector('meta[name="csrf-token"]');
    var headers = {};
    if (token) headers["X-CSRFToken"] = token.content;
    fetch(lockUrl, { method: "POST", headers: headers, credentials: "same-origin" })
      .catch(function () {})
      .finally(function () {
        window.location.href = loginUrl + "?locked=1";
      });
  }

  function reset() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(lock, minutes * 60000);
  }

  ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "visibilitychange"].forEach(
    function (name) {
      window.addEventListener(
        name,
        function () {
          var now = Date.now();
          if (now - last > 1000) {
            last = now;
            reset();
          }
        },
        { passive: true }
      );
    }
  );

  reset();
})();
