/* Progressive enhancement. Without this file every ticket is still its own page and every form still posts normally. */
(function () {
  "use strict";
  var workspace = document.getElementById("workspace");
  var help = document.getElementById("help");

  /* ---------- help dialog ---------- */
  var opener = null;
  function openHelp(target) {
    if (!help) return;
    opener = document.activeElement;
    if (help.showModal) help.showModal(); else help.setAttribute("open", "");
    help.scrollTop = 0;
    if (target) { var el = document.getElementById(target); if (el && el.scrollIntoView) el.scrollIntoView(); }
  }
  function closeHelp() {
    if (!help) return;
    if (help.close) help.close(); else help.removeAttribute("open");
    if (opener && opener.focus) opener.focus();
  }
  document.querySelectorAll("[data-open-help]").forEach(function (b) {
    b.hidden = false;
    b.addEventListener("click", function () { openHelp(b.getAttribute("data-open-help")); });
  });
  document.querySelectorAll("[data-close-help]").forEach(function (b) { b.addEventListener("click", closeHelp); });
  if (help) help.addEventListener("click", function (e) { if (e.target === help) closeHelp(); });

  if (!workspace) return;
  var panel = document.getElementById("panel");
  var queue = document.getElementById("queue");
  var lastRow = null;

  /* ---------- helpers ---------- */
  function withFragment(url, kind) {
    var u = new URL(url, location.href);
    u.searchParams.set("fragment", kind);
    return u.pathname + u.search;
  }
  function plainUrl(url) {
    var u = new URL(url, location.href);
    u.searchParams.delete("fragment");
    return u.pathname + u.search;
  }
  function currentQueueUrl() { return queue.getAttribute("data-queue-url") + location.search.replace(/^\?/, "?"); }

  function setSelected(id) {
    queue.querySelectorAll(".row-link").forEach(function (a) {
      var match = id && a.getAttribute("href") === "/tickets/" + id;
      if (match) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
  }

  function showPanel(html, focus) {
    panel.innerHTML = html;
    panel.hidden = false;
    workspace.classList.add("has-panel");
    wirePanel();
    var h = panel.querySelector("#p-title");
    if (focus && h) h.focus({ preventScroll: true });
    panel.scrollTop = 0;
  }
  function hidePanel(restore) {
    panel.hidden = true;
    panel.innerHTML = "";
    workspace.classList.remove("has-panel");
    setSelected(null);
    if (restore && lastRow && document.body.contains(lastRow)) lastRow.focus();
  }

  function refreshList() {
    var u = location.search;
    return fetch(withFragment(queue.getAttribute("data-queue-url") + u, "list"), { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        queue.innerHTML = html;
        var m = location.pathname.match(/^\/tickets\/(\d+)$/);
        setSelected(m ? m[1] : null);
      });
  }

  function openUrl(url, push) {
    var path = plainUrl(url);
    return fetch(withFragment(path, "1"), { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        showPanel(html, true);
        var m = path.match(/^\/tickets\/(\d+)$/);
        setSelected(m ? m[1] : null);
        if (push) history.pushState({ panel: true }, "", path);
        document.title = (panel.querySelector("#p-title") || {}).textContent + " | Help desk";
      })
      .catch(function () { location.href = path; });
  }

  function closePanel(push) {
    hidePanel(true);
    var base = queue.getAttribute("data-queue-url") || "/";
    if (push) history.pushState({}, "", base + location.search.replace(/^\?$/, ""));
    document.title = "Queue | Help desk";
  }

  /* ---------- clicks on the queue and the top bar ---------- */
  queue.addEventListener("click", function (e) {
    var a = e.target.closest("a.row-link");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    e.preventDefault();
    lastRow = a;
    openUrl(a.getAttribute("href"), true);
  });
  var newBtn = document.querySelector("[data-new]");
  if (newBtn) newBtn.addEventListener("click", function (e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    lastRow = newBtn;
    openUrl(newBtn.getAttribute("href"), true);
  });

  /* search + filters refresh just the list */
  var searchForm = document.querySelector("form.search");
  if (searchForm) searchForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var qs = new URLSearchParams(new FormData(searchForm));
    Array.from(qs.keys()).forEach(function (k) { if (qs.get(k) === "" && k !== "status") qs.delete(k); });
    var url = location.pathname.indexOf("/tickets/") === 0 || location.pathname === "/tickets/new"
      ? queue.getAttribute("data-queue-url") : location.pathname;
    history.replaceState({}, "", url + (qs.toString() ? "?" + qs : ""));
    refreshList();
  });
  /* the "show everything" / reset links inside the page also stay in the page */
  document.querySelectorAll(".filter-actions a, .empty a").forEach(bindLocal);
  queue.addEventListener("click", function (e) {
    var a = e.target.closest(".empty a");
    if (a) { e.preventDefault(); applyLocal(a); }
  });
  function bindLocal(a) { a.addEventListener("click", function (e) { e.preventDefault(); applyLocal(a); }); }
  function applyLocal(a) {
    var u = new URL(a.getAttribute("href"), location.href);
    var base = u.pathname;
    if (location.pathname.indexOf("/tickets/") === 0) base = base; /* keep ticket open */
    history.replaceState({}, "", location.pathname.indexOf("/tickets/") === 0 ? location.pathname + u.search : u.pathname + u.search);
    if (searchForm) {
      var sp = new URLSearchParams(u.search);
      searchForm.q.value = sp.get("q") || "";
      ["status", "category", "priority", "assignee"].forEach(function (n) { if (searchForm[n]) searchForm[n].value = sp.has(n) ? sp.get(n) : (n === "status" ? "active" : ""); });
      if (searchForm.overdue) searchForm.overdue.checked = sp.get("overdue") === "1";
    }
    refreshList();
  }

  /* ---------- inside the panel ---------- */
  function wirePanel() {
    panel.querySelectorAll("[data-close]").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); closePanel(true); });
    });
    panel.querySelectorAll("a.tag").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); location.href = a.href; });
    });
    panel.querySelectorAll("form[data-ajax]").forEach(function (f) {
      f.addEventListener("submit", function (e) {
        e.preventDefault();
        var btn = f.querySelector("button[type=submit]");
        if (btn) btn.disabled = true;
        var action = withFragment(f.getAttribute("action"), "1");
        fetch(action, { method: "POST", body: new URLSearchParams(new FormData(f)), headers: { "X-Requested-With": "fetch" } })
          .then(function (r) { return r.text().then(function (t) { return { url: r.url, text: t }; }); })
          .then(function (res) {
            var keepNote = f.classList.contains("note-form");
            showPanel(res.text, false);
            var m = new URL(res.url).pathname.match(/^\/tickets\/(\d+)$/);
            if (m && location.pathname !== "/tickets/" + m[1]) history.replaceState({ panel: true }, "", "/tickets/" + m[1]);
            if (m) setSelected(m[1]);
            refreshList();
            var msg = panel.querySelector(".flash");
            if (msg) { msg.setAttribute("tabindex", "-1"); msg.focus({ preventScroll: true }); }
            if (keepNote) { var n = panel.querySelector("#note-body"); if (n && !msg.classList.contains("error")) n.value = ""; }
          })
          .catch(function () { if (btn) btn.disabled = false; f.submit ? f.removeAttribute("data-ajax") : null; f.submit(); });
      });
    });
    var res = panel.querySelector(".res-field");
    var sel = panel.querySelector("form.update select[name=status]");
    if (res && sel) {
      var done = res.getAttribute("data-done").split(",");
      var sync = function () {
        var needs = done.indexOf(sel.value) !== -1;
        res.hidden = !needs && !res.querySelector("textarea").value;
      };
      sel.addEventListener("change", sync);
      sync();
    }
  }
  wirePanel();

  window.addEventListener("popstate", function () {
    var p = location.pathname;
    if (/^\/tickets\/(\d+|new)$/.test(p)) openUrl(p, false);
    else if (!panel.hidden) hidePanel(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden && !(help && help.open)) closePanel(true);
  });
  var m0 = location.pathname.match(/^\/tickets\/(\d+)$/);
  if (m0) setSelected(m0[1]);
})();
