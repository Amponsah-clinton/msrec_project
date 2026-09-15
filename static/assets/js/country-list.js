/* ==========================================================
   Populates every <select data-country-select> on the page (signup's
   "Country of Residence" and "Institution Country") from a live country
   list -- restcountries.com's public API, no key required. Falls back to
   a bundled list if the request fails/times out/is offline, so a
   third-party API being down can never block someone from signing up.
========================================================== */
(function () {
  // Common short names, kept in the same style restcountries.com's
  // `name.common` returns -- used verbatim if the API call fails.
  var FALLBACK_COUNTRIES = [
    "Afghanistan","Albania","Algeria","Andorra","Angola","Antigua and Barbuda","Argentina","Armenia",
    "Australia","Austria","Azerbaijan","Bahamas","Bahrain","Bangladesh","Barbados","Belarus","Belgium",
    "Belize","Benin","Bhutan","Bolivia","Bosnia and Herzegovina","Botswana","Brazil","Brunei","Bulgaria",
    "Burkina Faso","Burundi","Cabo Verde","Cambodia","Cameroon","Canada","Central African Republic","Chad",
    "Chile","China","Colombia","Comoros","Costa Rica","Croatia","Cuba","Cyprus","Czechia",
    "Democratic Republic of the Congo","Denmark","Djibouti","Dominica","Dominican Republic","Ecuador",
    "Egypt","El Salvador","Equatorial Guinea","Eritrea","Estonia","Eswatini","Ethiopia","Fiji","Finland",
    "France","Gabon","Gambia","Georgia","Germany","Ghana","Greece","Grenada","Guatemala","Guinea",
    "Guinea-Bissau","Guyana","Haiti","Honduras","Hungary","Iceland","India","Indonesia","Iran","Iraq",
    "Ireland","Israel","Italy","Ivory Coast","Jamaica","Japan","Jordan","Kazakhstan","Kenya","Kiribati",
    "Kuwait","Kyrgyzstan","Laos","Latvia","Lebanon","Lesotho","Liberia","Libya","Liechtenstein","Lithuania",
    "Luxembourg","Madagascar","Malawi","Malaysia","Maldives","Mali","Malta","Marshall Islands","Mauritania",
    "Mauritius","Mexico","Micronesia","Moldova","Monaco","Mongolia","Montenegro","Morocco","Mozambique",
    "Myanmar","Namibia","Nauru","Nepal","Netherlands","New Zealand","Nicaragua","Niger","Nigeria",
    "North Korea","North Macedonia","Norway","Oman","Pakistan","Palau","Palestine","Panama",
    "Papua New Guinea","Paraguay","Peru","Philippines","Poland","Portugal","Qatar","Republic of the Congo",
    "Romania","Russia","Rwanda","Saint Kitts and Nevis","Saint Lucia","Saint Vincent and the Grenadines",
    "Samoa","San Marino","Sao Tome and Principe","Saudi Arabia","Senegal","Serbia","Seychelles",
    "Sierra Leone","Singapore","Slovakia","Slovenia","Solomon Islands","Somalia","South Africa",
    "South Korea","South Sudan","Spain","Sri Lanka","Sudan","Suriname","Sweden","Switzerland","Syria",
    "Taiwan","Tajikistan","Tanzania","Thailand","Timor-Leste","Togo","Tonga","Trinidad and Tobago",
    "Tunisia","Turkey","Turkmenistan","Tuvalu","Uganda","Ukraine","United Arab Emirates","United Kingdom",
    "United States","Uruguay","Uzbekistan","Vanuatu","Vatican City","Venezuela","Vietnam","Yemen","Zambia",
    "Zimbabwe",
  ];

  function populate(select, names) {
    var current = select.value;
    select.innerHTML = "";
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = select.hasAttribute("required") ? "Select country" : "Select country (optional)";
    select.appendChild(placeholder);
    names.forEach(function (name) {
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
    // A disabled field (e.g. "no institution affiliation" already
    // checked before this finishes loading) or a value restored from a
    // saved draft should survive the swap from the loading placeholder.
    if (current && names.includes(current)) select.value = current;
  }

  function populateAll(names) {
    document.querySelectorAll("[data-country-select]").forEach(function (select) {
      populate(select, names);
    });
  }

  var selects = document.querySelectorAll("[data-country-select]");
  if (!selects.length) return;

  var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  var timeoutId = setTimeout(function () {
    if (controller) controller.abort();
  }, 6000);

  // flagcdn.com's codes.json: free, no API key, CORS-enabled for every
  // origin, and CDN-cached -- {"gh": "Ghana", "us": "United States", ...}.
  fetch("https://flagcdn.com/en/codes.json", controller ? { signal: controller.signal } : {})
    .then(function (res) {
      if (!res.ok) throw new Error("Country API returned " + res.status);
      return res.json();
    })
    .then(function (data) {
      // codes.json also carries subnational flags (e.g. "us-al" ->
      // Alabama, "gb-eng" -> England) alongside real countries -- their
      // codes are the only thing that tells them apart from a proper
      // 2-letter ISO country code, so filter on the key, not the name.
      var names = Object.keys(data || {})
        .filter(function (code) { return /^[a-z]{2}$/.test(code); })
        .map(function (code) { return data[code]; })
        .filter(Boolean)
        .sort(function (a, b) { return a.localeCompare(b); });
      populateAll(names.length ? names : FALLBACK_COUNTRIES);
    })
    .catch(function () {
      populateAll(FALLBACK_COUNTRIES);
    })
    .finally(function () {
      clearTimeout(timeoutId);
    });
})();
