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

  document.addEventListener("DOMContentLoaded", wireRefreshButton);
})();
