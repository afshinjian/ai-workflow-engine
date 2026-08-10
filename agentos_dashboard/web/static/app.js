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

  function clientToken() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    var bytes = new Uint8Array(16);
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      window.crypto.getRandomValues(bytes);
    } else {
      for (var i = 0; i < bytes.length; i += 1) {
        bytes[i] = Math.floor(Math.random() * 256);
      }
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    var hex = Array.prototype.map.call(bytes, function (value) {
      return value.toString(16).padStart(2, "0");
    }).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" +
      hex.slice(16, 20) + "-" + hex.slice(20);
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return Promise.resolve().then(function () {
        return navigator.clipboard.writeText(text);
      });
    }
    return Promise.resolve().then(function () {
      var textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        if (!document.execCommand("copy")) {
          throw new Error("copy command was refused");
        }
      } finally {
        document.body.removeChild(textarea);
      }
    });
  }

  function downloadMarkdown(filename, markdown) {
    var blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  function renderPromptResult(box, data) {
    box.textContent = "";
    box.classList.remove("empty-state");
    var heading = document.createElement("h3");
    heading.textContent = "Generated prompt for " + data.stage_id + " (sha256 " + data.sha256.slice(0, 12) + "…)";
    var pre = document.createElement("pre");
    pre.className = "mono";
    pre.textContent = data.markdown;
    var copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.textContent = "Copy";
    copyButton.addEventListener("click", function () {
      copyButton.disabled = true;
      status.textContent = "Copying…";
      copyToClipboard(data.markdown)
        .then(function () {
          status.textContent = "Copied prompt bytes to the clipboard.";
        })
        .catch(function () {
          status.textContent = "Copy failed — no prompt bytes were copied.";
        })
        .finally(function () {
          copyButton.disabled = false;
        });
    });
    var exportButton = document.createElement("button");
    exportButton.type = "button";
    exportButton.textContent = "Export .md";
    exportButton.addEventListener("click", function () {
      try {
        downloadMarkdown(data.filename, data.markdown);
        status.textContent = "Export started with the previewed prompt bytes.";
      } catch (error) {
        status.textContent = "Export failed — no download was started.";
      }
    });
    var status = document.createElement("p");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    box.appendChild(heading);
    box.appendChild(pre);
    box.appendChild(copyButton);
    box.appendChild(exportButton);
    box.appendChild(status);
  }

  function renderPromptRefusal(box, message) {
    box.textContent = "";
    box.classList.add("empty-state");
    var paragraph = document.createElement("p");
    paragraph.textContent = "Refused: " + message;
    box.appendChild(paragraph);
  }

  function wireGeneratePromptButtons() {
    var buttons = document.querySelectorAll("[data-action='generate-prompt']");
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        var stageId = button.getAttribute("data-stage-id") || "";
        if (!window.confirm("Generate a prompt for " + stageId + "?")) {
          return;
        }
        var box = document.getElementById("prompt-result");
        if (!box) {
          return;
        }
        button.disabled = true;
        renderPromptRefusal(box, "generation in progress…");
        fetch("/dash/api/v1/prompts/generate", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": readCookie("dash_csrf") || "",
          },
          credentials: "same-origin",
          body: JSON.stringify({ stage_id: stageId, client_token: clientToken() }),
        })
          .then(function (response) {
            return response.json().then(function (body) {
              return { response: response, body: body };
            });
          })
          .then(function (result) {
            var body = result.body;
            if (result.response.ok && body && body.ok && body.data) {
              renderPromptResult(box, body.data);
            } else {
              var message = body && body.error && body.error.message
                ? body.error.message
                : "the server rejected the request";
              renderPromptRefusal(box, message);
            }
          })
          .catch(function () {
            renderPromptRefusal(box, "generation request failed — no prompt was generated");
          })
          .finally(function () {
            button.disabled = false;
          });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", wireRefreshButton);
  document.addEventListener("DOMContentLoaded", wireAcknowledgeForms);
  document.addEventListener("DOMContentLoaded", wireGeneratePromptButtons);
})();
