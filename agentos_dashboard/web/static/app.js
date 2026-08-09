(function () {
  "use strict";

  function readCookie(name) {
    var pairs = ("; " + document.cookie).split("; " + name + "=");
    if (pairs.length === 2) {
      return pairs.pop().split(";").shift();
    }
    return null;
  }

  function wireRefreshButton() {
    var button = document.querySelector("[data-action='refresh-snapshot']");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      if (!window.confirm("Rebuild the repository snapshot now?")) {
        return;
      }
      fetch("/dash/api/v1/snapshot/refresh", {
        method: "POST",
        headers: { "X-CSRF-Token": readCookie("dash_csrf") || "" },
        credentials: "same-origin",
      }).then(function () {
        window.location.reload();
      });
    });
  }

  function wireAcknowledgeForms() {
    var forms = document.querySelectorAll("[data-action='acknowledge-finding']");
    forms.forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var fingerprint = form.getAttribute("data-fingerprint") || "";
        var note = form.querySelector("textarea[name='note']").value;
        if (!note || !window.confirm("Record this local acknowledgment note?")) {
          return;
        }
        fetch("/dash/api/v1/consistency/acknowledge", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": readCookie("dash_csrf") || "",
          },
          credentials: "same-origin",
          body: JSON.stringify({ fingerprint: fingerprint, note: note }),
        }).then(function () {
          window.location.reload();
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", wireRefreshButton);
  document.addEventListener("DOMContentLoaded", wireAcknowledgeForms);
})();
