---
title: "Search Guides"
type: "page"
description: "Search all car breakdown and roadside emergency guides on Tow With The Flow."
---

<div class="search-results">
  <input type="text" id="search-input" placeholder="Search guides... e.g. towing cost, battery dead, overheating" autocomplete="off">
  <div id="search-results-list"></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js"></script>
<script>
(function() {
  var q = new URLSearchParams(window.location.search).get('q') || '';
  var input = document.getElementById('search-input');
  var list = document.getElementById('search-results-list');
  if (q) input.value = q;

  fetch('/index.json')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var fuse = new Fuse(data, {
        keys: ['title', 'description', 'content'],
        threshold: 0.35,
        includeScore: true
      });

      function render(results) {
        if (!results.length) {
          list.innerHTML = '<p style="color:var(--text-dim); padding: 1rem 0;">No results found. Try different keywords.</p>';
          return;
        }
        list.innerHTML = results.map(function(r) {
          var item = r.item || r;
          return '<div class="search-result-item">' +
            '<h3><a href="' + item.permalink + '">' + item.title + '</a></h3>' +
            '<p>' + (item.description || '') + '</p>' +
            '</div>';
        }).join('');
      }

      if (q) render(fuse.search(q));

      input.addEventListener('input', function() {
        var val = input.value.trim();
        if (val.length < 2) { list.innerHTML = ''; return; }
        render(fuse.search(val));
      });
    })
    .catch(function() {
      list.innerHTML = '<p style="color:var(--text-dim);">Search unavailable. Try browsing <a href="/posts/">all guides</a>.</p>';
    });
})();
</script>
