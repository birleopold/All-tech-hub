/* Recipient acknowledgement pad: mouse, finger or stylus, with file fallback. */
(function () {
  "use strict";
  function ready() {
    var form = document.querySelector("[data-job-handover-form]");
    if (!form) { return; }
    var canvas = form.querySelector("[data-job-handover-pad]");
    var clear = form.querySelector("[data-job-handover-clear]");
    var image = form.querySelector('input[name="signature_upload"]');
    var encoded = form.querySelector('input[name="signature_data"]');
    var warning = form.querySelector("[data-job-handover-warning]");
    if (!canvas || !encoded) { return; }
    var ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) { return; }

    var isDrawing = false;
    var hasInk = false;
    var activePointer = null;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = 2.8;
    ctx.strokeStyle = "#172033";

    function point(clientX, clientY) {
      var rect = canvas.getBoundingClientRect();
      return {
        x: (clientX - rect.left) * canvas.width / rect.width,
        y: (clientY - rect.top) * canvas.height / rect.height
      };
    }
    function start(x, y) {
      var p = point(x, y);
      isDrawing = true;
      hasInk = true;
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(p.x + 0.1, p.y + 0.1);
      ctx.stroke();
    }
    function move(x, y) {
      if (!isDrawing) { return; }
      var p = point(x, y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    }
    function finish() {
      isDrawing = false;
      activePointer = null;
    }
    if (window.PointerEvent) {
      canvas.addEventListener("pointerdown", function (event) {
        if (activePointer !== null) { return; }
        event.preventDefault();
        activePointer = event.pointerId;
        start(event.clientX, event.clientY);
        if (canvas.setPointerCapture) { canvas.setPointerCapture(event.pointerId); }
      });
      canvas.addEventListener("pointermove", function (event) {
        if (activePointer !== event.pointerId) { return; }
        event.preventDefault();
        move(event.clientX, event.clientY);
      });
      function endPointer(event) {
        if (activePointer === event.pointerId) { finish(); }
      }
      canvas.addEventListener("pointerup", endPointer);
      canvas.addEventListener("pointercancel", endPointer);
      canvas.addEventListener("lostpointercapture", finish);
    } else {
      canvas.addEventListener("mousedown", function (event) {
        event.preventDefault();
        start(event.clientX, event.clientY);
      });
      window.addEventListener("mousemove", function (event) {
        if (isDrawing) { move(event.clientX, event.clientY); }
      });
      window.addEventListener("mouseup", finish);
      canvas.addEventListener("touchstart", function (event) {
        event.preventDefault();
        if (!isDrawing && event.touches.length) {
          start(event.touches[0].clientX, event.touches[0].clientY);
        }
      }, { passive: false });
      canvas.addEventListener("touchmove", function (event) {
        event.preventDefault();
        if (event.touches.length) {
          move(event.touches[0].clientX, event.touches[0].clientY);
        }
      }, { passive: false });
      canvas.addEventListener("touchend", finish);
      canvas.addEventListener("touchcancel", finish);
    }

    clear.addEventListener("click", function () {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hasInk = false;
      encoded.value = "";
      if (warning) { warning.classList.add("d-none"); }
    });
    form.addEventListener("submit", function (event) {
      var uploaded = image && image.files && image.files.length > 0;
      encoded.value = "";
      if (!uploaded && !hasInk) {
        event.preventDefault();
        if (warning) {
          warning.textContent = "Ask the recipient to sign, or upload their signature image.";
          warning.classList.remove("d-none");
        }
        return;
      }
      if (!uploaded && hasInk) {
        encoded.value = canvas.toDataURL("image/png");
      }
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ready);
  } else { ready(); }
}());
