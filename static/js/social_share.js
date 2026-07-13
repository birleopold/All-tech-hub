(() => {
  "use strict";

  const status = document.getElementById("share-status");

  const showStatus = (message) => {
    if (!status) return;
    status.textContent = message;
    window.setTimeout(() => {
      if (status.textContent === message) status.textContent = "";
    }, 4000);
  };

  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("Copy failed");
  };

  document.querySelectorAll("[data-share-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const url = button.dataset.shareUrl;
      if (!url) return;
      try {
        await copyText(url);
        showStatus("Marketing link copied. Paste it into any post, status, group or message.");
      } catch (error) {
        showStatus("Copy failed. Select and copy the address from your browser.");
      }
    });
  });

  document.querySelectorAll("[data-share-native]").forEach((button) => {
    button.addEventListener("click", async () => {
      const payload = {
        title: button.dataset.shareTitle || document.title,
        text: button.dataset.shareText || "",
        url: button.dataset.shareUrl || window.location.href,
      };

      if (navigator.share) {
        try {
          await navigator.share(payload);
          showStatus("Share panel opened successfully.");
        } catch (error) {
          if (error && error.name !== "AbortError") {
            showStatus("Sharing was not completed. You can use Copy link instead.");
          }
        }
        return;
      }

      try {
        await copyText(payload.url);
        showStatus("This browser has no app share panel, so the marketing link was copied instead.");
      } catch (error) {
        showStatus("Use the social buttons above or copy the address from your browser.");
      }
    });
  });
})();
