/**
 * AI4SS - Main JavaScript
 * Features: Filter tabs, scroll-reveal, counter animation, active nav, particles
 */

document.addEventListener('DOMContentLoaded', () => {
    initFilterGroups();
    initSmoothScroll();
    initNavScroll();
    initScrollReveal();
    initCounterAnimation();
    initActiveNav();
    initMobileNav();
    initParticles();
});

/**
 * Generic filter tabs for collection grids.
 */
function initFilterGroups() {
    const filterGroups = document.querySelectorAll('[data-filter-group]');
    if (!filterGroups.length) return;

    filterGroups.forEach((group) => {
        const filterTabs = group.querySelectorAll('.filter-tab');
        const targetSelector = group.dataset.target;
        const attribute = group.dataset.attribute || 'category';
        const cards = targetSelector ? document.querySelectorAll(targetSelector) : [];

        if (!filterTabs.length || !cards.length) return;

        filterTabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                filterTabs.forEach((item) => item.classList.remove('active'));
                tab.classList.add('active');

                const filterValue = tab.dataset.filter || 'all';

                cards.forEach((card) => {
                    const cardValue = (card.dataset[attribute] || '').toLowerCase();
                    const shouldShow = filterValue === 'all' || cardValue === filterValue;

                    if (shouldShow) {
                        card.style.display = 'block';
                        card.style.animation = 'fadeInUp 0.4s ease forwards';
                    } else {
                        card.style.display = 'none';
                    }
                });
            });
        });
    });
}

/**
 * Smooth scroll for anchor links
 */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', (e) => {
            e.preventDefault();
            const target = document.querySelector(anchor.getAttribute('href'));
            if (target) {
                const navHeight = document.querySelector('.nav')?.offsetHeight || 0;
                const targetPosition = target.getBoundingClientRect().top + window.scrollY - navHeight - 20;
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
}

/**
 * Navigation background on scroll
 */
function initNavScroll() {
    const nav = document.querySelector('.nav');
    if (!nav) return;

    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            nav.classList.add('scrolled');
        } else {
            nav.classList.remove('scrolled');
        }
    });
}

/**
 * Scroll-reveal: fade in elements as they enter viewport
 */
function initScrollReveal() {
    const revealElements = document.querySelectorAll('.reveal');
    if (!revealElements.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });

    revealElements.forEach(el => observer.observe(el));
}

/**
 * Counter animation for stat values
 */
function initCounterAnimation() {
    const counters = document.querySelectorAll('.stat-value[data-count]');
    if (!counters.length) return;

    const animateCounter = (el) => {
        const target = parseInt(el.dataset.count, 10);
        const duration = 1500;
        const increment = target / (duration / 16);
        let current = 0;

        const step = () => {
            current += increment;
            if (current >= target) {
                el.textContent = target;
                return;
            }
            el.textContent = Math.floor(current);
            requestAnimationFrame(step);
        };

        step();
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });

    counters.forEach(el => {
        el.textContent = '0';
        observer.observe(el);
    });
}

/**
 * Active navigation link tracking
 */
function initActiveNav() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-links a[href^="#"]');
    if (!sections.length || !navLinks.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                navLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${id}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }, {
        threshold: 0.2,
        rootMargin: '-80px 0px -60% 0px'
    });

    sections.forEach(section => observer.observe(section));
}

/**
 * Mobile navigation toggle
 */
function initMobileNav() {
    const toggle = document.querySelector('.nav-toggle');
    const links = document.querySelector('.nav-links');
    if (!toggle || !links) return;

    toggle.addEventListener('click', () => {
        links.classList.toggle('open');
        toggle.classList.toggle('active');
    });

    // Close menu when clicking a link
    links.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            links.classList.remove('open');
            toggle.classList.remove('active');
        });
    });
}

/**
 * Subtle particle effect for hero section
 */
function initParticles() {
    const canvas = document.getElementById('particle-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationFrame;

    function resize() {
        const hero = canvas.parentElement;
        canvas.width = hero.offsetWidth;
        canvas.height = hero.offsetHeight;
    }

    function createParticles() {
        particles = [];
        const count = Math.floor((canvas.width * canvas.height) / 15000);
        for (let i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                radius: Math.random() * 1.5 + 0.5,
                vx: (Math.random() - 0.5) * 0.3,
                vy: (Math.random() - 0.5) * 0.3,
                alpha: Math.random() * 0.5 + 0.1
            });
        }
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        particles.forEach(p => {
            // Move
            p.x += p.vx;
            p.y += p.vy;

            // Wrap around
            if (p.x < 0) p.x = canvas.width;
            if (p.x > canvas.width) p.x = 0;
            if (p.y < 0) p.y = canvas.height;
            if (p.y > canvas.height) p.y = 0;

            // Draw
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(127, 90, 240, ${p.alpha})`;
            ctx.fill();
        });

        // Connect nearby particles
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < 100) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(127, 90, 240, ${0.1 * (1 - dist / 100)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }

        animationFrame = requestAnimationFrame(draw);
    }

    resize();
    createParticles();
    draw();

    window.addEventListener('resize', () => {
        resize();
        createParticles();
    });
}
