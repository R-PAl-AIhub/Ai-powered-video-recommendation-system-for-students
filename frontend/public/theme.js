// Runs before first paint: apply the theme the student chose, if any.
// With no saved choice the stylesheet follows the system preference.
(function () {
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch (_) {
    /* storage unavailable (private mode): fall back to the system preference */
  }
})();
