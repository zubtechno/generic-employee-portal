if (window.lucide) {
  window.lucide.createIcons({ strokeWidth: 1.8 });
}

document.querySelectorAll('input[type="file"][accept^="image"]').forEach((input) => {
  input.addEventListener("change", () => {
    const label = input.closest(".file-field");
    if (!label || !input.files.length) return;
    const text = label.querySelector("span:nth-of-type(2)");
    if (text) text.textContent = input.files[0].name;
  });
});

// ── Dark Mode Toggle ──
(function () {
  const root = document.documentElement;
  const btn  = document.getElementById("theme-toggle-btn");
  if (!btn) return;

  // Apply stored preference (also handled inline before CSS to avoid flash)
  const saved = localStorage.getItem("theme");
  if (saved === "dark") root.setAttribute("data-theme", "dark");

  btn.addEventListener("click", function () {
    const isDark = root.getAttribute("data-theme") === "dark";
    if (isDark) {
      root.removeAttribute("data-theme");
      localStorage.setItem("theme", "light");
    } else {
      root.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
    }
  });
})();
