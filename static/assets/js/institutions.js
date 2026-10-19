/* Institution dropdowns -- the "Other (not listed)" escape hatch.
   ------------------------------------------------------------------
   Every Institution <select> on the site offers "Other (not listed)"
   first, ahead of the admin-managed list, plus a companion free-text box.
   This file is the browser half of pages/institutions.py: when someone
   finishes typing a name into that box it is put in Title Case, added to
   the dropdown itself and selected there, so the name they go on to submit
   is the one the list will hold. The server repeats both steps on the way
   in -- this is for the person looking at the form, never the guarantee.

   Used by: the public sign-up form (assets/js/signup.js), workshop
   registration (templates/workshop/register.html) and the Committee
   Members forms on the admin and secretariat dashboards
   (dashboard/js/board-committee-admin.js,
   templates/dashboards/secretariat/committee/members.html). */
(function () {
  "use strict";

  var OTHER_VALUE = "__other__";
  // An all-capitals word of no more than this many letters is an acronym the
  // member means literally (KNUST, UCC, KATH, GIMPA) and is left untouched;
  // a longer one is just caps-lock ("TEACHING") and is title-cased with the
  // rest.
  var ACRONYM_MAX_LETTERS = 6;

  var LETTER_RUN = /\p{L}+/gu;
  var LETTERS = /\p{L}/gu;
  var HAS_LOWER = /\p{Ll}/u;
  var HAS_UPPER = /\p{Lu}/u;

  function isAcronym(word) {
    var letters = word.match(LETTERS);
    return (
      HAS_UPPER.test(word) &&
      !HAS_LOWER.test(word) &&
      letters !== null &&
      letters.length <= ACRONYM_MAX_LETTERS
    );
  }

  /* Capitalizes the first letter of each letter-run in one word, so
     hyphenated and Irish-style names read correctly ("kwame-nkrumah" ->
     "Kwame-Nkrumah", "o'brien" -> "O'Brien") while a possessive stays
     lowercase ("mary's" -> "Mary's", never "Mary'S"). */
  function capitalizeWord(word) {
    return word.replace(LETTER_RUN, function (run, offset) {
      // Only an O'-style prefix -- a single letter, then the apostrophe, at
      // the very start of the word -- capitalizes what follows the quote.
      if (offset > 0 && word.charAt(offset - 1) === "'" && offset !== 2) {
        return run.toLowerCase();
      }
      return run.charAt(0).toUpperCase() + run.slice(1).toLowerCase();
    });
  }

  /* Capitalizes each word of an institution name. Mirrors
     pages.institutions.title_case: a name with any lowercase in it keeps
     its acronyms and its mixed-case words ("University of Ghana, KNUST" ->
     "University Of Ghana, KNUST", "McDonald clinic" -> "McDonald Clinic"),
     while a word shouted in full is not an acronym ("korle bu TEACHING
     hospital" -> "Korle Bu Teaching Hospital"). A name typed entirely in
     capitals is treated as caps-lock and title-cased, unless it is a lone
     acronym. */
  function titleCase(value) {
    var name = String(value == null ? "" : value).trim().replace(/\s+/g, " ");
    if (!name) return "";

    var words = name.split(" ");
    if (!HAS_LOWER.test(name)) {
      if (words.length === 1 && isAcronym(name)) return name;
      return words.map(capitalizeWord).join(" ");
    }
    return words
      .map(function (word) {
        var keep = isAcronym(word) || (HAS_UPPER.test(word) && HAS_LOWER.test(word));
        return keep ? word : capitalizeWord(word);
      })
      .join(" ");
  }

  /* The institutions a dropdown actually lists: not the empty placeholder,
     not the "Other" row. */
  function listedOptions(select) {
    return Array.prototype.filter.call(select.options, function (option) {
      return option.value && option.value !== OTHER_VALUE;
    });
  }

  function findOption(select, name) {
    var lower = name.toLowerCase();
    var match = listedOptions(select).filter(function (option) {
      return option.value.toLowerCase() === lower;
    });
    return match.length ? match[0] : null;
  }

  /* Adds one name to one dropdown, keeping the list alphabetical where it
     already is. An admin can order the list by hand, and a name dropped
     into the middle of a hand-ordered list would look misplaced -- such a
     list gets the new name appended instead. */
  function insertOption(select, name) {
    var option = new Option(name, name);
    var listed = listedOptions(select);
    var sorted = listed.every(function (current, index) {
      return index === 0 || listed[index - 1].text.localeCompare(current.text) <= 0;
    });

    var before = null;
    if (sorted) {
      for (var i = 0; i < listed.length; i += 1) {
        if (listed[i].text.localeCompare(name) > 0) {
          before = listed[i];
          break;
        }
      }
    }
    select.add(option, before);
    return option;
  }

  /* Puts one typed-in value in Title Case and makes sure every dropdown
     passed in lists it. Returns the name to submit -- which is the list's
     own spelling when the institution is already on it, so one institution
     can't end up on the list twice under two casings. */
  function promote(value, selects) {
    var name = titleCase(value);
    if (!name) return "";

    var targets = Array.prototype.slice.call(selects || []);
    targets.forEach(function (select) {
      var existing = findOption(select, name);
      if (existing) name = existing.value;
    });
    targets.forEach(function (select) {
      if (!findOption(select, name)) insertOption(select, name);
    });
    return name;
  }

  /* Call when someone finishes typing in the "Other" box (on blur, or as
     the form is submitted): the typed name joins the dropdown(s) and is
     selected there, then the select's own "change" handler hides the
     now-spent box. An empty box is left alone, so the field's own
     required-ness is what complains about it. */
  function commit(select, input, selects) {
    if (!select || !input || select.value !== OTHER_VALUE) return "";

    var name = promote(input.value, selects && selects.length ? selects : [select]);
    if (!name) return "";

    input.value = name;
    select.value = name;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    return name;
  }

  /* Wires one select/input pair: Title-Case and promote on blur, and again
     as the form is submitted, for anyone who hits Enter straight from the
     box. The optional third argument is every dropdown on the page that
     shares the same list, so a name typed in one section shows up in all
     of them. */
  function wire(select, input, selects) {
    if (!select || !input) return;
    input.addEventListener("blur", function () {
      commit(select, input, selects);
    });
    var form = select.form;
    if (!form) return;
    form.addEventListener(
      "submit",
      function () {
        commit(select, input, selects);
      },
      true
    );
  }

  window.MSRECInstitutions = {
    OTHER_VALUE: OTHER_VALUE,
    titleCase: titleCase,
    promote: promote,
    commit: commit,
    wire: wire,
  };
})();
