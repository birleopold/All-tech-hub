/* Staff workspace conveniences: staff_refresh.js
 *
 * 1. Press "/" or Ctrl/Cmd+K to jump to the staff search box.
 * 2. Remember which sidebar groups the person opened or closed.
 * 3. Scroll the sidebar so the current page is visible.
 *
 * Everything is optional: if storage or an element is missing, the page
 * still works exactly as before.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "staff-nav-groups-v1";

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  function initSearchShortcut() {
    var search = document.getElementById("staff-global-search");
    if (!search) return;

    document.addEventListener("keydown", function (event) {
      if (event.defaultPrevented || event.isComposing || !search.getClientRects().length) return;
      var slash = event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey;
      var palette = (event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "k";
      if (!slash && !palette) return;
      if (isTypingTarget(document.activeElement)) return;

      event.preventDefault();
      search.focus();
      search.select();
    });
  }

  function readState() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (error) {
      return {};
    }
  }

  function writeState(state) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
      /* Storage can be blocked; the menu simply will not be remembered. */
    }
  }

  function initNavMemory() {
    var groups = document.querySelectorAll(".staff-sidebar-shell .staff-nav-group");
    if (!groups.length) return;

    var state = readState();

    groups.forEach(function (group) {
      var label = group.querySelector("summary span");
      var key = label ? label.textContent.trim() : "";
      if (!key) return;

      /* The server opens the group that holds the current page; that always wins. */
      var holdsCurrentPage = !!group.querySelector('[aria-current="page"]');
      if (!holdsCurrentPage && Object.prototype.hasOwnProperty.call(state, key)) {
        group.open = !!state[key];
      }

      group.addEventListener("toggle", function () {
        state[key] = group.open;
        writeState(state);
      });
    });
  }

  function revealCurrentPage() {
    var current = document.querySelector(
      ".staff-sidebar-shell .staff-nav-link[aria-current='page']"
    );
    var sidebar = document.querySelector(".staff-sidebar-scroll");
    if (current && sidebar && sidebar.clientHeight) {
      var itemBounds = current.getBoundingClientRect();
      var sidebarBounds = sidebar.getBoundingClientRect();
      if (itemBounds.bottom > sidebarBounds.bottom) {
        sidebar.scrollTop += itemBounds.bottom - sidebarBounds.bottom;
      } else if (itemBounds.top < sidebarBounds.top) {
        sidebar.scrollTop -= sidebarBounds.top - itemBounds.top;
      }
    }
  }

  function init() {
    initSearchShortcut();
    initNavMemory();
    revealCurrentPage();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
