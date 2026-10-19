/* Searchable dropdowns.
   ------------------------------------------------------------------
   Turns a long <select> -- the Institution / Organization dropdowns, where
   the list runs to hundreds of names -- into a combobox with a search box
   that filters the list as you type, on a phone exactly as on a desktop.

   The native <select> is kept, and keeps its name, value, required flag and
   "change" event: it is simply made invisible and laid over by a button, so
   everything already wired to it (assets/js/signup.js,
   assets/js/institutions.js, the dashboards' modal scripts, the server) goes
   on working untouched, and a browser with no JavaScript still gets the
   plain dropdown. Mark a select with data-searchable-select to enhance it.

   Options:
     data-search-placeholder  placeholder for the search box
     data-other-input         id of the companion "Other" free-text box; a
                              search that found nothing hands it what was
                              typed, so the name is not typed twice.
*/
(function () {
  "use strict";

  var OTHER_VALUE = "__other__";
  var MAX_VISIBLE = 120;

  // Copied off the native select so the button matches whatever the page
  // styles its own form controls like -- public site or dashboard, light
  // theme or dark -- with no per-page CSS of our own.
  var LOOK = [
    "fontFamily", "fontSize", "fontWeight", "fontStyle", "letterSpacing", "lineHeight",
    "color", "backgroundColor",
    "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
    "borderTopStyle", "borderRightStyle", "borderBottomStyle", "borderLeftStyle",
    "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor",
    "borderTopLeftRadius", "borderTopRightRadius", "borderBottomLeftRadius", "borderBottomRightRadius",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "minHeight", "boxShadow",
  ];

  var seq = 0;
  var open = null; // only one panel is ever open

  /* Folds case, accents and runs of whitespace, so "universite" matches
     "Université" and "  ghana " matches "Ghana". */
  function normalize(value) {
    var text = String(value == null ? "" : value).toLowerCase();
    if (text.normalize) {
      text = text.normalize("NFD").replace(/[̀-ͯ]/g, "");
    }
    return text.replace(/\s+/g, " ").trim();
  }

  /* Every word of the query has to appear somewhere in the option, so
     "ghana uni" finds "University of Ghana" and word order does not
     matter. */
  function matches(haystack, tokens) {
    for (var i = 0; i < tokens.length; i += 1) {
      if (haystack.indexOf(tokens[i]) === -1) return false;
    }
    return true;
  }

  function isTransparent(color) {
    return !color || color === "transparent" || /rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)/.test(color);
  }

  /* The nearest background the panel can sit on without the page showing
     through it. */
  function solidBackground(element) {
    for (var node = element; node && node.nodeType === 1; node = node.parentElement) {
      var color = window.getComputedStyle(node).backgroundColor;
      if (!isTransparent(color)) return color;
    }
    return "#fff";
  }

  /* The nearest ancestor that would clip the panel -- the dashboards open
     these fields inside a modal that scrolls (.acct-modal), so "the room
     below" is not simply the room left in the window. */
  function clipBox(element) {
    for (var node = element.parentElement; node && node !== document.body; node = node.parentElement) {
      var overflow = window.getComputedStyle(node).overflowY;
      if (overflow === "auto" || overflow === "scroll" || overflow === "hidden") {
        return node.getBoundingClientRect();
      }
    }
    return null;
  }

  function labelFor(select) {
    var wrapping = select.closest("label");
    if (wrapping) return wrapping;
    return select.id ? document.querySelector('label[for="' + select.id + '"]') : null;
  }

  function SearchableSelect(select) {
    seq += 1;
    this.id = "ss-" + seq;
    this.select = select;
    this.items = [];
    this.activeIndex = -1;
    this.build();
    this.bind();
    this.syncFromSelect();
  }

  SearchableSelect.prototype.build = function () {
    var select = this.select;
    var styles = window.getComputedStyle(select);

    var wrap = document.createElement("div");
    wrap.className = "ss";
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("ss-native");
    // Not display:none: a required control that isn't rendered can't be
    // focused, and browsers then refuse to submit the form at all (silently,
    // bar a console warning). Left in place and invisible, it keeps native
    // validation -- and its message bubble lands on the field.
    select.setAttribute("tabindex", "-1");
    select.setAttribute("aria-hidden", "true");

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "ss-trigger";
    trigger.id = this.id + "-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    LOOK.forEach(function (prop) { trigger.style[prop] = styles[prop]; });
    if (select.disabled) trigger.disabled = true;

    var label = document.createElement("span");
    label.className = "ss-value";
    label.id = this.id + "-value";
    var caret = document.createElement("span");
    caret.className = "ss-caret";
    caret.setAttribute("aria-hidden", "true");
    trigger.appendChild(label);
    trigger.appendChild(caret);

    // Keep the field's own label on the button, ahead of the chosen value.
    var fieldLabel = labelFor(select);
    if (fieldLabel) {
      if (!fieldLabel.id) fieldLabel.id = this.id + "-label";
      trigger.setAttribute("aria-labelledby", fieldLabel.id + " " + label.id);
    }

    var panel = document.createElement("div");
    panel.className = "ss-panel";
    panel.hidden = true;
    panel.style.backgroundColor = solidBackground(select.parentElement || select);
    panel.style.color = styles.color;
    panel.style.borderColor = styles.borderTopColor;

    var searchRow = document.createElement("div");
    searchRow.className = "ss-search-row";
    var search = document.createElement("input");
    search.type = "text";
    search.className = "ss-search";
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-expanded", "true");
    search.setAttribute("aria-controls", this.id + "-list");
    search.setAttribute("autocomplete", "off");
    search.setAttribute("autocorrect", "off");
    search.setAttribute("autocapitalize", "off");
    search.setAttribute("spellcheck", "false");
    search.setAttribute("enterkeyhint", "done");
    search.placeholder = select.dataset.searchPlaceholder || "Search…";
    if (fieldLabel) search.setAttribute("aria-label", "Search " + fieldLabel.textContent.trim());
    var clear = document.createElement("button");
    clear.type = "button";
    clear.className = "ss-clear";
    clear.hidden = true;
    clear.setAttribute("aria-label", "Clear search");
    clear.textContent = "×";
    searchRow.appendChild(search);
    searchRow.appendChild(clear);

    var list = document.createElement("ul");
    list.className = "ss-list";
    list.id = this.id + "-list";
    list.setAttribute("role", "listbox");

    var empty = document.createElement("p");
    empty.className = "ss-empty";
    empty.hidden = true;

    panel.appendChild(searchRow);
    panel.appendChild(list);
    panel.appendChild(empty);
    wrap.appendChild(trigger);
    wrap.appendChild(panel);

    this.wrap = wrap;
    this.trigger = trigger;
    this.label = label;
    this.panel = panel;
    this.search = search;
    this.clear = clear;
    this.list = list;
    this.empty = empty;
  };

  /* Rebuilds the rows from the native select's options -- called every time
     the panel opens, so a name added to the dropdown while the page is
     open (assets/js/institutions.js) is simply there. */
  SearchableSelect.prototype.render = function () {
    var self = this;
    var list = this.list;
    list.textContent = "";
    this.items = [];

    Array.prototype.forEach.call(this.select.options, function (option, index) {
      // The empty placeholder ("Select institution") is the button's resting
      // label, not something to offer in the list.
      if (!option.value) return;

      var item = document.createElement("li");
      item.className = "ss-option";
      if (option.value === OTHER_VALUE) item.classList.add("ss-option-other");
      item.id = self.id + "-opt-" + index;
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", option.value === self.select.value ? "true" : "false");
      item.dataset.value = option.value;
      item.textContent = option.text;
      list.appendChild(item);

      self.items.push({
        el: item,
        value: option.value,
        text: option.text,
        norm: normalize(option.text),
        // "Other (not listed)" is the way out of a search that found
        // nothing, so it is never filtered away.
        pinned: option.value === OTHER_VALUE,
        visible: true,
      });
    });
  };

  SearchableSelect.prototype.filter = function () {
    var query = normalize(this.search.value);
    var tokens = query ? query.split(" ") : [];
    var shown = 0;
    var hiddenByCap = 0;
    var found = 0;

    this.items.forEach(function (item) {
      var hit = item.pinned || !tokens.length || matches(item.norm, tokens);
      if (hit && !item.pinned) found += 1;
      // A very long list is capped per keystroke: the rest stay one more
      // typed letter away, and nothing has to render 300 rows to show it.
      if (hit && !item.pinned && shown >= MAX_VISIBLE) {
        hiddenByCap += 1;
        hit = false;
      } else if (hit && !item.pinned) {
        shown += 1;
      }
      item.visible = hit;
      item.el.hidden = !hit;
      item.el.classList.remove("ss-active");
    });

    this.clear.hidden = !this.search.value;

    if (!found && tokens.length) {
      this.empty.hidden = false;
      this.empty.textContent = this.items.some(function (i) { return i.pinned; })
        ? 'No match for "' + this.search.value.trim() + '". Choose "Other (not listed)" to enter it.'
        : 'No match for "' + this.search.value.trim() + '".';
    } else if (hiddenByCap) {
      this.empty.hidden = false;
      this.empty.textContent = hiddenByCap + " more match — keep typing to narrow it down.";
    } else {
      this.empty.hidden = true;
    }

    this.activeIndex = -1;
    this.moveActive(1);
    this.list.scrollTop = 0;
  };

  SearchableSelect.prototype.visibleItems = function () {
    return this.items.filter(function (item) { return item.visible; });
  };

  SearchableSelect.prototype.moveActive = function (step) {
    var visible = this.visibleItems();
    if (!visible.length) {
      this.activeIndex = -1;
      this.search.removeAttribute("aria-activedescendant");
      return;
    }
    var current = -1;
    for (var i = 0; i < visible.length; i += 1) {
      if (visible[i].el.classList.contains("ss-active")) { current = i; break; }
    }
    var next = current + step;
    if (next < 0) next = visible.length - 1;
    if (next >= visible.length) next = 0;

    visible.forEach(function (item) { item.el.classList.remove("ss-active"); });
    var active = visible[next];
    active.el.classList.add("ss-active");
    this.activeIndex = this.items.indexOf(active);
    this.search.setAttribute("aria-activedescendant", active.el.id);
    if (active.el.scrollIntoView) active.el.scrollIntoView({ block: "nearest" });
  };

  SearchableSelect.prototype.choose = function (value) {
    var typed = this.search.value.trim();
    var other = this.select.dataset.otherInput
      ? document.getElementById(this.select.dataset.otherInput)
      : null;

    this.select.value = value;
    // Everything else on the page hangs off the native select's own event:
    // the "Other" box opening, its required flag, the dashboards' rows.
    this.select.dispatchEvent(new Event("change", { bubbles: true }));

    var toOther = value === OTHER_VALUE && other && other.offsetParent !== null;
    // Searched for something that isn't on the list and reached for
    // "Other"? Carry what was typed across rather than ask for it twice.
    if (value === OTHER_VALUE && other && typed && !other.value) other.value = typed;

    this.close(!toOther);
    if (toOther) other.focus();
  };

  SearchableSelect.prototype.syncFromSelect = function () {
    var option = this.select.selectedOptions && this.select.selectedOptions[0];
    var placeholder = this.select.options[0] && !this.select.options[0].value
      ? this.select.options[0].text
      : "Select…";
    var chosen = option && option.value ? option.text : "";
    this.label.textContent = chosen || placeholder;
    this.wrap.classList.toggle("ss-empty-value", !chosen);
    this.trigger.disabled = this.select.disabled;
  };

  SearchableSelect.prototype.isOpen = function () {
    return !this.panel.hidden;
  };

  SearchableSelect.prototype.open = function (seed) {
    if (this.isOpen() || this.select.disabled) return;
    if (open && open !== this) open.close(false);
    open = this;

    this.render();
    this.search.value = seed || "";
    this.panel.hidden = false;
    this.wrap.classList.add("ss-is-open");
    this.trigger.setAttribute("aria-expanded", "true");
    this.placePanel();
    this.filter();
    // On a phone this brings the field (and the panel under it) above the
    // keyboard that is about to open.
    if (this.wrap.scrollIntoView) this.wrap.scrollIntoView({ block: "nearest" });
    this.search.focus();
  };

  /* Opens upward when the panel would otherwise run off the bottom of the
     screen (or of the modal it is in) -- the Institution field sits low on
     more than one of these forms -- and gives it only the height it can
     actually have there. */
  SearchableSelect.prototype.placePanel = function () {
    this.wrap.classList.remove("ss-drop-up");
    this.panel.style.maxHeight = "";

    var box = this.trigger.getBoundingClientRect();
    var clip = clipBox(this.wrap);
    var ceiling = clip ? Math.max(0, clip.top) : 0;
    var floor = clip ? Math.min(window.innerHeight, clip.bottom) : window.innerHeight;
    var below = floor - box.bottom;
    var above = box.top - ceiling;

    var needed = this.panel.offsetHeight || 300;
    var up = below < needed && above > below;
    if (up) this.wrap.classList.add("ss-drop-up");

    // Only ever shrink the panel: the stylesheet stays in charge of how
    // tall it gets when there is room for it.
    var room = (up ? above : below) - 14;
    if (room > 150 && room < needed) this.panel.style.maxHeight = room + "px";
  };

  SearchableSelect.prototype.close = function (refocus) {
    if (!this.isOpen()) return;
    this.panel.hidden = true;
    this.wrap.classList.remove("ss-is-open", "ss-drop-up");
    this.trigger.setAttribute("aria-expanded", "false");
    this.search.value = "";
    this.search.removeAttribute("aria-activedescendant");
    if (open === this) open = null;
    if (refocus) this.trigger.focus();
  };

  SearchableSelect.prototype.bind = function () {
    var self = this;

    this.trigger.addEventListener("click", function (event) {
      event.preventDefault();
      if (self.isOpen()) self.close(true);
      else self.open("");
    });

    // Typing straight at the closed field opens the panel and keeps the
    // first letter, the way a native dropdown jumps to it.
    this.trigger.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        self.open("");
      } else if (event.key && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        self.open(event.key);
      }
    });

    this.search.addEventListener("input", function () { self.filter(); });

    this.search.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        self.moveActive(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        self.moveActive(-1);
      } else if (event.key === "Enter") {
        // Never let Enter inside the search box submit the form.
        event.preventDefault();
        var active = self.items[self.activeIndex];
        if (active && active.visible) self.choose(active.value);
      } else if (event.key === "Escape") {
        // Stop here: on the dashboards, Escape also closes the modal this
        // field sits in, and one keypress should only do one thing.
        event.preventDefault();
        event.stopPropagation();
        self.close(true);
      } else if (event.key === "Tab") {
        self.close(false);
      }
    });

    this.clear.addEventListener("click", function () {
      self.search.value = "";
      self.filter();
      self.search.focus();
    });

    this.list.addEventListener("click", function (event) {
      var item = event.target.closest(".ss-option");
      if (item && !item.hidden) self.choose(item.dataset.value);
    });
    this.list.addEventListener("mousemove", function (event) {
      var item = event.target.closest(".ss-option");
      if (!item || item.hidden) return;
      self.items.forEach(function (entry) { entry.el.classList.remove("ss-active"); });
      item.classList.add("ss-active");
      self.activeIndex = self.items.findIndex(function (entry) { return entry.el === item; });
      self.search.setAttribute("aria-activedescendant", item.id);
    });

    // Whatever sets the value -- this panel, another script, a reset -- the
    // button always shows what the select holds.
    this.select.addEventListener("change", function () { self.syncFromSelect(); });
  };

  function enhance(select) {
    if (!select || select.dataset.ssReady === "1") return null;
    if (!select.closest || !window.getComputedStyle) return null;
    select.dataset.ssReady = "1";
    return new SearchableSelect(select);
  }

  function enhanceAll(root) {
    var scope = root || document;
    Array.prototype.forEach.call(
      scope.querySelectorAll("select[data-searchable-select]"),
      enhance
    );
  }

  document.addEventListener("click", function (event) {
    if (!open) return;
    var within = event.target && event.target.closest ? event.target.closest(".ss") : null;
    if (within !== open.wrap) open.close(false);
  });
  document.addEventListener("keydown", function (event) {
    if (open && event.key === "Escape" && !open.panel.contains(event.target)) {
      event.stopPropagation();
      open.close(true);
    }
  });
  window.addEventListener("resize", function () { if (open) open.placePanel(); });
  // A panel left hanging where its field no longer is would be worse than
  // one that simply closed.
  window.addEventListener("scroll", function () { if (open) open.placePanel(); }, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { enhanceAll(); });
  } else {
    enhanceAll();
  }

  window.MSRECSearchableSelect = { enhance: enhance, enhanceAll: enhanceAll };
})();
