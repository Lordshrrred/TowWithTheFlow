// script.js

// 1. Smooth scroll + active nav
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function(e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      target.scrollIntoView({ behavior: 'smooth' });
    }
  });
});

// 2. Active nav highlight on scroll
const sections = document.querySelectorAll('.section[id]');
const navLinks = document.querySelectorAll('.nav-link');

window.addEventListener('scroll', () => {
  let current = '';
  sections.forEach(section => {
    const sectionTop = section.offsetTop - 200;
    if (scrollY >= sectionTop) {
      current = section.getAttribute('id');
    }
  });

  navLinks.forEach(link => {
    link.classList.remove('active');
    if (link.getAttribute('href') === `#${current}`) {
      link.classList.add('active');
    }
  });
});

// 3. Scroll reveal
const revealElements = document.querySelectorAll('.section');
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.1 });

revealElements.forEach(el => revealObserver.observe(el));

// 4. Mode toggle (Earth / Cosmos)
const modeToggle = document.querySelector('.mode-toggle');
const body = document.body;

function setMode(mode) {
  body.classList.remove('earth', 'cosmos');
  body.classList.add(mode);
  localStorage.setItem('voa-mode', mode);
}

const savedMode = localStorage.getItem('voa-mode') || 'earth';
setMode(savedMode);

modeToggle.addEventListener('click', () => {
  const current = body.classList.contains('earth') ? 'cosmos' : 'earth';
  setMode(current);
});

// 5. Fake form submission
const form = document.getElementById('lead-form');
const successMsg = document.getElementById('form-success');

form.addEventListener('submit', e => {
  e.preventDefault();
  // Here you would normally send to Formspree / etc.
  form.style.opacity = '0.5';
  form.querySelector('button').textContent = 'Sending...';
  setTimeout(() => {
    form.classList.add('hidden');
    successMsg.classList.remove('hidden');
  }, 1200);
});

// 6. Copyright year
document.getElementById('year').textContent = new Date().getFullYear();

// 7. Very light mouse gradient shift (optional feel)
const heroBg = document.querySelector('.hero-bg');
let mouseX = 0, mouseY = 0;

window.addEventListener('mousemove', e => {
  mouseX = e.clientX / window.innerWidth;
  mouseY = e.clientY / window.innerHeight;
});

function updateGradient() {
  heroBg.style.background = `
    radial-gradient(circle at ${mouseX*100}% ${mouseY*100}%,
    rgba(122,232,201,0.08) 0%,
    transparent 40%)
  `;
  requestAnimationFrame(updateGradient);
}
updateGradient();