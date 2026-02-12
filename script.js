// Mode toggle (Earth vs Cosmos)
const modeToggle = document.querySelector('.mode-toggle');
const body = document.body;

function setMode(mode) {
  body.classList.remove('earth-mode', 'cosmos-mode');
  body.classList.add(mode + '-mode');
  localStorage.setItem('voa-mode', mode);
}

const savedMode = localStorage.getItem('voa-mode') || 'earth';
setMode(savedMode);

modeToggle.addEventListener('click', () => {
  const current = body.classList.contains('earth-mode') ? 'cosmos' : 'earth';
  setMode(current);
});

// Rest of your previous script (smooth scroll, reveal, form fake submit, etc.) stays the same