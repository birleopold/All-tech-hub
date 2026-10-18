/* Field notes are saved only on explicit request, never replayed silently.
 * Browser IndexedDB holds per-user drafts. No customer records are cached.
 */
(function () {
  "use strict";
  var roots = document.querySelectorAll("[data-offline-job-notes]");
  if (!roots.length) return;
  if (!window.indexedDB || !window.crypto || !window.crypto.randomUUID) {
    roots.forEach(function (root) {
      var status = root.querySelector("[data-offline-status]");
      if (status) status.textContent = "Offline storage is unavailable in this browser. Use the normal online note form.";
      root.querySelectorAll("button").forEach(function (button) { button.disabled = true; });
    });
    return;
  }
  var DB = "leosoft-field-notes-v1";
  var STORE = "drafts";
  var EXPIRY_MS = 7 * 24 * 60 * 60 * 1000;

  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB, 1);
      req.onupgradeneeded = function () {
        if (!req.result.objectStoreNames.contains(STORE)) {
          req.result.createObjectStore(STORE, { keyPath: "id" });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }
  function operation(type, value) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, type === "list" ? "readonly" : "readwrite");
        var object = tx.objectStore(STORE);
        var req = type === "list" ? object.getAll() :
          type === "put" ? object.put(value) : object.delete(value);
        req.onsuccess = function () { resolve(req.result); };
        req.onerror = function () { reject(req.error); };
        tx.oncomplete = function () { db.close(); };
        tx.onerror = function () { db.close(); };
      });
    });
  }
  function pending(owner, job) {
    return operation("list").then(async function (items) {
      var now = Date.now();
      for (var i = 0; i < items.length; i++) {
        if (typeof items[i].created !== "number" || now - items[i].created >= EXPIRY_MS) {
          await operation("delete", items[i].id);
        }
      }
      return items.filter(function (d) {
        return d.owner === owner && d.job === job && typeof d.created === "number" &&
          now - d.created < EXPIRY_MS;
      }).sort(function (a, b) { return a.created - b.created; });
    });
  }
  roots.forEach(function (root) {
    var owner = root.dataset.offlineOwner;
    var job = root.dataset.offlineJob;
    var version = root.dataset.offlineVersion;
    var jobOpen = root.dataset.offlineOpen === "yes";
    var endpoint = root.dataset.offlineEndpoint;
    var textarea = root.querySelector("[data-offline-text]");
    var save = root.querySelector("[data-offline-save]");
    var sync = root.querySelector("[data-offline-sync]");
    var clear = root.querySelector("[data-offline-discard]");
    var rebase = root.querySelector("[data-offline-review]");
    var status = root.querySelector("[data-offline-status]");
    var count = root.querySelector("[data-offline-count]");
    var preview = root.querySelector("[data-offline-preview]");
    var form = root.querySelector("form");
    if (!owner || !job || !version || !endpoint || !textarea || !form) return;
    var busy = false;
    var conflict = false;
    var serverConflict = false;
    var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');

    function say(message) { status.textContent = message; }
    function refresh() {
      return pending(owner, job).then(function (drafts) {
        count.textContent = String(drafts.length);
        var stale = drafts.some(function (draft) { return draft.base !== version; });
        sync.disabled = !jobOpen || !drafts.length || busy || !navigator.onLine || stale || serverConflict;
        save.disabled = !jobOpen || busy;
        clear.disabled = !drafts.length || busy;
        rebase.hidden = !jobOpen || (!stale && !serverConflict && !conflict) || !drafts.length;
        rebase.textContent = serverConflict ? "Reload latest job details" :
          "I've reviewed the latest job and notes";
        if (preview) {
          preview.replaceChildren();
          drafts.forEach(function (draft) {
            var item = document.createElement("li");
            item.className = "list-group-item text-break";
            item.textContent = draft.body;
            preview.appendChild(item);
          });
        }
        if (stale && !serverConflict && !busy) {
          say("The job changed since this draft was saved. Review the current job and notes before syncing.");
        }
      }).catch(function () { say("Offline storage unavailable. Do not close this unsaved note."); });
    }
    save.addEventListener("click", function () {
      var body = textarea.value.trim();
      if (!jobOpen) { say("This job is closed. You can discard saved drafts."); return; }
      if (!body || body.length > 3000) {
        say("Write an internal note between 1 and 3,000 characters."); return;
      }
      busy = true; save.disabled = true;
      pending(owner, job).then(function (drafts) {
        if (drafts.length >= 20) throw Error("Device queue limit reached (20). Sync or discard notes.");
        return operation("put", {
          id: crypto.randomUUID(), owner: owner, job: job,
          body: body, base: version, created: Date.now()
        });
      }).then(function () {
        textarea.value = "";
        say("Saved on this device only. Review and sync when online; not yet sent to LEOSOFT.");
      }).catch(function (e) {
        say("Could not save offline: " + (e.message || "storage unavailable"));
      }).finally(function () {
        busy = false; save.disabled = false; refresh();
      });
    });
    sync.addEventListener("click", async function () {
      if (busy || !navigator.onLine || !jobOpen) {
        say("This job must be open and online to sync."); return;
      }
      busy = true; conflict = false; await refresh();
      try {
        var drafts = await pending(owner, job);
        if (serverConflict || drafts.some(function (draft) { return draft.base !== version; })) {
          conflict = true;
          say("Review the latest job details and saved drafts first. Nothing was sent.");
          return;
        }
        for (var i = 0; i < drafts.length; i++) {
          var draft = drafts[i];
          var payload = new FormData();
          payload.append("operation_id", draft.id);
          payload.append("body", draft.body);
          payload.append("base_version", draft.base);
          if (csrf) payload.append("csrfmiddlewaretoken", csrf.value);
          var response = await fetch(endpoint, {
            method: "POST", body: payload, credentials: "same-origin",
            cache: "no-store", headers: { "Accept": "application/json" }
          });
          var result;
          try { result = await response.json(); }
          catch (_) { throw Error("Session expired or the server did not respond normally."); }
          if (response.ok && (result.code === "saved" || result.code === "already_saved")) {
            await operation("delete", draft.id);
            say("Synced " + (i + 1) + " of " + drafts.length + " internal notes.");
          } else if (result.code === "job_changed") {
            conflict = true;
            serverConflict = true;
            say("Job information changed. Review the current job and its notes before authorising replay. Drafts were preserved.");
            break;
          } else {
            say(result.message || "Sync failed. Drafts remain on this device.");
            break;
          }
        }
        if (!conflict && !(await pending(owner, job)).length) {
          say("All queued notes saved. Reload this page to see them in the timeline.");
        }
      } catch (e) {
        say("Connection or server error. Drafts were kept; no automatic retry. " + (e.message || ""));
      } finally { busy = false; refresh(); }
    });
    rebase.addEventListener("click", async function () {
      if (serverConflict) { window.location.reload(); return; }
      if (!jobOpen) return;
      if (!window.confirm(
        "Have you reviewed this job's latest details and notes? Only then retry these private notes. This action does NOT move status or stock."
      )) return;
      busy = true;
      try {
        var drafts = await pending(owner, job);
        for (var i = 0; i < drafts.length; i++) {
          drafts[i].base = version;
          await operation("put", drafts[i]);
        }
        conflict = false;
        say("Drafts reviewed against the version shown on this page. Press Sync to submit.");
      } finally { busy = false; refresh(); }
    });
    clear.addEventListener("click", async function () {
      if (!window.confirm("Permanently discard this job's unsynced device notes?")) return;
      var drafts = await pending(owner, job);
      for (var i = 0; i < drafts.length; i++) await operation("delete", drafts[i].id);
      conflict = false; say("Unsynced notes discarded from this device."); refresh();
    });
    window.addEventListener("online", refresh);
    window.addEventListener("offline", function () { say("Offline. You may save internal notes to this device."); refresh(); });
    refresh();
  });
}());
