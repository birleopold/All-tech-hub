(() => {
  "use strict";

  function csrfToken(scope = document) {
    return scope.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
  }

  function applicationServerKey(publicKey) {
    const padded = publicKey
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(publicKey.length / 4) * 4, "=");
    return Uint8Array.from(atob(padded), value => value.charCodeAt(0));
  }

  async function enablePush(publicKeyUrl, subscribeUrl, csrf) {
    if (
      !("serviceWorker" in navigator) ||
      !("PushManager" in window) ||
      !("Notification" in window)
    ) {
      throw new Error("Push notifications are not supported by this browser.");
    }
    if (Notification.permission === "denied") {
      throw new Error("Notifications are blocked in this browser's site settings.");
    }

    const keyResponse = await fetch(publicKeyUrl, { credentials: "same-origin" });
    if (!keyResponse.ok) throw new Error("Could not load notification settings.");
    const { public_key: publicKey } = await keyResponse.json();
    if (!publicKey) {
      throw new Error("Phone notifications are not configured on the server yet.");
    }

    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Notification permission was not granted.");
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey(publicKey),
      });
    }

    const saveResponse = await fetch(subscribeUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      body: JSON.stringify(subscription.toJSON()),
    });
    if (!saveResponse.ok) throw new Error("Could not register this device.");
    return true;
  }

  function initDesktopHandoff() {
    const startButton = document.getElementById("phone-photo-start");
    const modalElement = document.getElementById("phonePhotoModal");
    if (!startButton || !modalElement) return;

    const startUrl = modalElement.dataset.startUrl;
    const publicKeyUrl = modalElement.dataset.publicKeyUrl;
    const subscribeUrl = modalElement.dataset.subscribeUrl;
    const csrf = csrfToken();
    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    let pollTimer;

    async function startHandoff() {
      modal.show();
      document.getElementById("phone-photo-loading").classList.remove("d-none");
      document.getElementById("phone-photo-ready").classList.add("d-none");
      document.getElementById("phone-photo-error").classList.add("d-none");

      try {
        const pushEnabled = await enablePush(
          publicKeyUrl,
          subscribeUrl,
          csrf
        ).catch(() => false);
        const response = await fetch(startUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrf },
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Could not start phone photo upload.");
        }

        document.getElementById("phone-photo-url").value = data.url;
        const qrResponse = await fetch(data.qr_url, {
          credentials: "same-origin",
        });
        const qr = await qrResponse.json();
        if (!qrResponse.ok || !qr.image) {
          throw new Error(qr.error || "Could not generate the QR code.");
        }
        document.getElementById("phone-photo-qr").src = qr.image;
        document.getElementById("phone-photo-push-result").textContent =
          data.push_sent
            ? "Notification sent to your registered phone."
            : pushEnabled
              ? "Notifications are enabled on this device. Scan the QR code on your phone to register that phone."
              : "No registered phone yet. Scan the QR code or copy the secure link.";

        document.getElementById("phone-photo-loading").classList.add("d-none");
        document.getElementById("phone-photo-ready").classList.remove("d-none");

        const poll = async () => {
          const statusResponse = await fetch(data.status_url, {
            credentials: "same-origin",
            cache: "no-store",
          });
          if (!statusResponse.ok) return;
          const status = await statusResponse.json();
          document.getElementById("phone-photo-count").textContent = status.count;
          const thumbnails = document.getElementById("phone-photo-thumbnails");
          thumbnails.replaceChildren();
          status.images.forEach(item => {
            const col = document.createElement("div");
            col.className = "col-3";
            const image = document.createElement("img");
            image.src = item.url;
            image.alt = item.alt_text || "";
            image.className = "img-fluid rounded border";
            col.appendChild(image);
            thumbnails.appendChild(col);
          });
        };

        await poll();
        clearInterval(pollTimer);
        pollTimer = setInterval(poll, 3000);
      } catch (error) {
        document.getElementById("phone-photo-loading").classList.add("d-none");
        const box = document.getElementById("phone-photo-error");
        box.textContent = error.message;
        box.classList.remove("d-none");
      }
    }

    startButton.addEventListener("click", startHandoff);
    document.getElementById("phone-photo-copy").addEventListener("click", async () => {
      const value = document.getElementById("phone-photo-url").value;
      try {
        await navigator.clipboard.writeText(value);
      } catch {
        const input = document.getElementById("phone-photo-url");
        input.select();
        document.execCommand("copy");
      }
    });
    modalElement.addEventListener("hidden.bs.modal", () => clearInterval(pollTimer));
    if (new URLSearchParams(window.location.search).get("photos") === "phone") {
      startHandoff();
    }
  }

  function initMobileUploader() {
    const root = document.getElementById("phone-photo-mobile");
    const form = document.getElementById("phone-photo-form");
    if (!root || !form) return;

    const input = document.getElementById("phone-photos");
    const preview = document.getElementById("phone-photo-preview");
    const message = document.getElementById("phone-photo-message");
    const pushButton = document.getElementById("enable-phone-push");
    const csrf = csrfToken(form);

    pushButton.addEventListener("click", async () => {
      pushButton.disabled = true;
      try {
        await enablePush(
          root.dataset.publicKeyUrl,
          root.dataset.subscribeUrl,
          csrf
        );
        pushButton.textContent = "Notifications enabled on this phone";
        message.textContent =
          "This phone will receive future product photo requests.";
        message.className = "alert alert-success mt-3";
      } catch (error) {
        message.textContent = error.message;
        message.className = "alert alert-warning mt-3";
        pushButton.disabled = false;
      }
    });

    input.addEventListener("change", () => {
      preview.replaceChildren();
      [...input.files].forEach(file => {
        const col = document.createElement("div");
        col.className = "col-4";
        const image = document.createElement("img");
        image.className = "img-fluid rounded";
        image.alt = "";
        image.src = URL.createObjectURL(file);
        col.appendChild(image);
        preview.appendChild(col);
      });
    });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      message.className = "alert d-none mt-3";
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Upload failed.");
        message.textContent =
          data.count +
          " photo(s) uploaded. You can add more or return to the computer.";
        message.className = "alert alert-success mt-3";
        form.reset();
        preview.replaceChildren();
      } catch (error) {
        message.textContent = error.message;
        message.className = "alert alert-danger mt-3";
      } finally {
        button.disabled = false;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initDesktopHandoff();
    initMobileUploader();
  });
})();
