// Small progressive-enhancement script. Pages work without it except the
// deliberately JS-driven demos (confirm dialogs, notifications, popup, help form).
(function () {
  "use strict";

  // Confirmation dialog before destructive form submits: <form data-confirm="...">
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // Dynamic content: notifications load after a server-side delay.
  var loadBtn = document.getElementById("load-notifications");
  if (loadBtn) {
    loadBtn.addEventListener("click", function () {
      var status = document.getElementById("notifications-status");
      var list = document.getElementById("notifications-list");
      list.innerHTML = "";
      loadBtn.disabled = true;
      status.textContent = "Loading notifications…";
      fetch("/api/v1/notifications?delay_ms=" + loadBtn.dataset.delayMs, { credentials: "same-origin" })
        .then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); })
        .then(function (items) {
          items.forEach(function (n) {
            var li = document.createElement("li");
            li.id = "notification-" + n.id;          // random id: do not use in locators
            li.className = "notification notification-" + n.level;
            li.setAttribute("data-testid", "notification-item");
            li.textContent = n.message;
            list.appendChild(li);
          });
          status.textContent = items.length + " notifications loaded";
        })
        .catch(function (err) { status.textContent = "Failed to load notifications (" + err.message + ")"; })
        .finally(function () { loadBtn.disabled = false; });
    });
  }

  // Popup window.
  var popupBtn = document.getElementById("open-help-popup");
  if (popupBtn) {
    popupBtn.addEventListener("click", function () {
      window.open("/help", "helpPopup", "width=640,height=520");
    });
  }

  // Help page (shown in iframe and popup): fake "send message".
  var contact = document.getElementById("contact-form");
  if (contact) {
    contact.addEventListener("submit", function (event) {
      event.preventDefault();
      var msg = document.getElementById("contact-message").value.trim();
      document.getElementById("contact-status").textContent =
        msg ? "Thanks! Your message has been sent." : "Please enter a message.";
    });
  }
})();
