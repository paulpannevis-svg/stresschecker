/* StressChecker® — Gedeelde JavaScript
   Minimaal gehouden — alleen wat echt nodig is op elke pagina */

// Voorkom dubbele form submissions
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', function() {
    const btn = this.querySelector('button[type="submit"]');
    if (btn) {
      btn.disabled = true;
      btn.style.opacity = '0.7';
      btn.textContent = btn.textContent.replace('▶', '⏳');
    }
  });
});
