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
  // Under this width the panel stops hanging off the field and becomes a
  // sheet at the bottom of the screen, where there is room for the search
  // box and the list above the on-screen keyboard.
  var SHEET_WIDTH = 640;
  var GAP = 6;
  var EDGE = 8;

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
  var openPanel = null; // only one panel is ever open

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
    this.panelBackground = solidBackground(select.parentElement || select);
    this.panelColor = styles.color;
    this.panelBorder = styles.borderTopColor;
    panel.style.backgroundColor = this.panelBackground;
    panel.style.color = this.panelColor;
    panel.style.borderColor = this.panelBorder;

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
    var done = document.createElement("button");
    done.type = "button";
    done.className = "ss-done";
    done.textContent = "Done";

    var searchBox = document.createElement("span");
    searchBox.className = "ss-search-box";
    searchBox.appendChild(search);
    searchBox.appendChild(clear);
    searchRow.appendChild(searchBox);
    searchRow.appendChild(done);

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
    this.done = done;
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
    var found = 0;

    this.items.forEach(function (item) {
      var hit = item.pinned || !tokens.length || matches(item.norm, tokens);
      if (hit && !item.pinned) found += 1;
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

    // On screen unless it, or something it sits in, carries the hidden
    // attribute -- which is how every one of these boxes is toggled.
    var toOther = value === OTHER_VALUE && other && !other.hidden && !other.closest("[hidden]");
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

  /* The page behind a phone sheet must not scroll under it. */
  function lockScroll(on) {
    if (on) {
      lockScroll.previous = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = lockScroll.previous || "";
    }
  }

  function buildBackdrop(instance) {
    var backdrop = document.createElement("div");
    backdrop.className = "ss-backdrop";
    backdrop.hidden = true;
    backdrop.addEventListener("click", function () { instance.close(true); });
    return backdrop;
  }

  SearchableSelect.prototype.isSheet = function () {
    return window.innerWidth <= SHEET_WIDTH;
  };

  SearchableSelect.prototype.open = function (seed) {
    if (this.isOpen() || this.select.disabled) return;
    if (openPanel && openPanel !== this) openPanel.close(false);
    openPanel = this;

    this.render();
    this.search.value = seed || "";
    this.panel.hidden = false;

    // Out of the field and into a layer of its own, on the body. These
    // dropdowns sit inside sections, cards and modals that clip or scroll
    // their overflow -- the sign-up form's role sections are `overflow:
    // clip` -- and a list sliced off at the edge of its section is the one
    // thing this must never do.
    this.sheet = this.isSheet();
    this.panel.classList.toggle("ss-sheet", this.sheet);
    if (this.sheet) {
      this.backdrop = this.backdrop || buildBackdrop(this);
      document.body.appendChild(this.backdrop);
      this.backdrop.hidden = false;
      lockScroll(true);
    }
    document.body.appendChild(this.panel);

    this.placePanel();
    this.filter();
    if (!this.sheet && this.wrap.scrollIntoView) this.wrap.scrollIntoView({ block: "nearest" });
    this.trigger.setAttribute("aria-expanded", "true");
    this.wrap.classList.add("ss-is-open");
    this.search.focus();
  };

  /* Anchors the panel to the field it belongs to. On a phone it is pinned
     to the bottom of the screen instead, where the search box stays put and
     the list has room above the keyboard. */
  SearchableSelect.prototype.placePanel = function () {
    var style = this.panel.style;

    if (this.sheet) {
      // visualViewport knows how much of the screen the on-screen keyboard
      // has taken; without it, the bottom of the window is the best guess.
      var view = window.visualViewport;
      var covered = view ? Math.max(0, window.innerHeight - view.height - view.offsetTop) : 0;
      var usable = view ? view.height : window.innerHeight;
      style.left = "0px";
      style.right = "0px";
      style.width = "auto";
      style.top = "auto";
      style.bottom = Math.round(covered) + "px";
      style.maxHeight = Math.round(usable * 0.8) + "px";
      return;
    }

    var box = this.trigger.getBoundingClientRect();
    var below = window.innerHeight - box.bottom - GAP - EDGE;
    var above = box.top - GAP - EDGE;
    // 220px is about six rows: less than that below the field and it is
    // worth opening upward instead, if there is more room up there.
    var up = below < Math.min(220, above);

    style.left = Math.round(box.left) + "px";
    style.right = "auto";
    style.width = Math.round(box.width) + "px";
    style.maxHeight = Math.max(160, Math.min(up ? above : below, 340)) + "px";
    if (up) {
      style.top = "auto";
      style.bottom = Math.round(window.innerHeight - box.top + GAP) + "px";
    } else {
      style.bottom = "auto";
      style.top = Math.round(box.bottom + GAP) + "px";
    }
    this.wrap.classList.toggle("ss-drop-up", up);
  };

  SearchableSelect.prototype.close = function (refocus) {
    if (!this.isOpen()) return;
    this.panel.hidden = true;
    // Back where it belongs, so the field carries its own panel around.
    this.wrap.appendChild(this.panel);
    this.panel.classList.remove("ss-sheet");
    this.panel.removeAttribute("style");
    this.panel.style.backgroundColor = this.panelBackground;
    this.panel.style.color = this.panelColor;
    this.panel.style.borderColor = this.panelBorder;
    if (this.backdrop) {
      this.backdrop.hidden = true;
      if (this.backdrop.parentNode) this.backdrop.parentNode.removeChild(this.backdrop);
    }
    if (this.sheet) lockScroll(false);
    this.sheet = false;
    this.wrap.classList.remove("ss-is-open", "ss-drop-up");
    this.trigger.setAttribute("aria-expanded", "false");
    this.search.value = "";
    this.search.removeAttribute("aria-activedescendant");
    if (openPanel === this) openPanel = null;
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

    this.done.addEventListener("click", function () { self.close(true); });

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
    if (!openPanel) return;
    var target = event.target;
    if (!target || !target.closest) return;
    var inside = target.closest(".ss") === openPanel.wrap || openPanel.panel.contains(target);
    if (!inside) openPanel.close(false);
  });
  document.addEventListener("keydown", function (event) {
    if (openPanel && event.key === "Escape" && !openPanel.panel.contains(event.target)) {
      event.stopPropagation();
      openPanel.close(true);
    }
  });
  // The on-screen keyboard opening or closing moves the sheet, and neither
  // fires a window resize on every platform.
  if (window.visualViewport) {
    ["resize", "scroll"].forEach(function (type) {
      window.visualViewport.addEventListener(type, function () {
        if (openPanel && openPanel.sheet) openPanel.placePanel();
      });
    });
  }

  window.addEventListener("resize", function () {
    // A phone rotated into landscape may no longer want a sheet, or may
    // now want one: reopen the panel in the shape that fits.
    if (!openPanel) return;
    if (openPanel.sheet !== openPanel.isSheet()) {
      var instance = openPanel;
      var typed = instance.search.value;
      instance.close(false);
      instance.open(typed);
    } else {
      openPanel.placePanel();
    }
  });
  // A panel left hanging where its field no longer is would be worse than
  // one that simply closed; a sheet is pinned to the screen and stays put.
  window.addEventListener("scroll", function () {
    if (!openPanel || openPanel.sheet) return;
    var box = openPanel.trigger.getBoundingClientRect();
    if (box.bottom < 0 || box.top > window.innerHeight) openPanel.close(false);
    else openPanel.placePanel();
  }, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { enhanceAll(); });
  } else {
    enhanceAll();
  }

  window.MSRECSearchableSelect = { enhance: enhance, enhanceAll: enhanceAll };
})();
