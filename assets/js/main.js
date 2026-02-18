/**
 * AI4SS - Main JavaScript
 * Features: Multi-dimensional filters, scroll-reveal, counter animation,
 *           active nav, particles (blue theme), search, typewriter, scroll-to-top
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
    initStaggerAnimation();
    initSearch();
    initTypewriter();
    initScrollToTop();
});

/**
 * Enhanced multi-dimensional filter system with faceted search support.
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
                const grid = cards[0]?.closest('.skills-grid');

                if (grid) grid.classList.add('filtering');

                let delay = 0;
                cards.forEach((card) => {
                    const cardValue = (card.dataset[attribute] || '').toLowerCase();
                    const shouldShow = filterValue === 'all' || cardValue === filterValue;

                    if (shouldShow) {
                        card.style.display = 'flex';
                        card.classList.remove('hidden');
                        // Stagger visible cards
                        setTimeout(() => {
                            card.classList.add('revealing');
                            setTimeout(() => {
                                card.classList.remove('revealing');
                                card.classList.add('revealed');
                            }, 50);
                        }, delay);
                        delay += 30;
                    } else {
                        card.classList.add('hidden');
                        card.classList.remove('revealed');
                        setTimeout(() => {
                            card.style.display = 'none';
                        }, 200);
                    }
                });

                setTimeout(() => {
                    if (grid) grid.classList.remove('filtering');
                }, 250);
            });
        });
    });
}

/**
 * Stagger animation for cards when filters change
 */
function initStaggerAnimation() {
    const styles = document.createElement('style');
    styles.textContent = `
        .hidden {
            opacity: 0;
            transform: scale(0.95);
            transition: opacity 0.15s ease, transform 0.15s ease;
        }
        .revealing {
            opacity: 0;
            transform: translateY(20px) scale(0.98);
            transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1),
                        transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .revealed {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    `;
    document.head.appendChild(styles);
}

/**
 * Smooth scroll for anchor links
 */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', (e) => {
            const href = anchor.getAttribute('href');
            if (href === '#') return;
            e.preventDefault();
            const target = document.querySelector(href);
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

    const handler = () => {
        nav.classList.toggle('scrolled', window.scrollY > 50);
    };

    window.addEventListener('scroll', handler, { passive: true });
    handler(); // Run once on load
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
        threshold: 0.08,
        rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(el => observer.observe(el));
}

/**
 * Counter animation for stat values - with easing
 */
function initCounterAnimation() {
    const counters = document.querySelectorAll('.stat-value[data-count]');
    if (!counters.length) return;

    const easeOut = t => 1 - Math.pow(1 - t, 3); // Cubic ease-out

    const animateCounter = (el) => {
        const target = parseInt(el.dataset.count, 10);
        if (isNaN(target) || target === 0) {
            el.textContent = '0';
            return;
        }
        const duration = 1600;
        const startTime = performance.now();

        const step = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easedProgress = easeOut(progress);
            el.textContent = Math.floor(easedProgress * target);

            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                el.textContent = target;
            }
        };

        requestAnimationFrame(step);
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
        toggle.setAttribute('aria-expanded', links.classList.contains('open'));
    });

    // Close menu when clicking a link
    links.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            links.classList.remove('open');
            toggle.classList.remove('active');
            toggle.setAttribute('aria-expanded', 'false');
        });
    });

    // Close menu on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.nav') && links.classList.contains('open')) {
            links.classList.remove('open');
            toggle.classList.remove('active');
        }
    });
}

/**
 * Subtle particle effect for hero section - BLUE theme (matching site palette)
 */
function initParticles() {
    const canvas = document.getElementById('particle-canvas');
    if (!canvas) return;

    // Respect reduced-motion preference
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        canvas.style.display = 'none';
        return;
    }

    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationFrame;

    // --- THEME COLOR: Blue #2563EB (37, 99, 235) ---
    const PARTICLE_R = 37;
    const PARTICLE_G = 99;
    const PARTICLE_B = 235;

    function resize() {
        const hero = canvas.parentElement;
        canvas.width = hero.offsetWidth;
        canvas.height = hero.offsetHeight;
    }

    function createParticles() {
        particles = [];
        const count = Math.min(Math.floor((canvas.width * canvas.height) / 14000), 80);
        for (let i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: Math.random() * canvas.height,
                radius: Math.random() * 1.8 + 0.4,
                vx: (Math.random() - 0.5) * 0.25,
                vy: (Math.random() - 0.5) * 0.25,
                alpha: Math.random() * 0.45 + 0.08
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

            // Draw particle
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${PARTICLE_R}, ${PARTICLE_G}, ${PARTICLE_B}, ${p.alpha})`;
            ctx.fill();
        });

        // Connect nearby particles with gradient lines
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < 110) {
                    const lineAlpha = 0.12 * (1 - dist / 110);
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(${PARTICLE_R}, ${PARTICLE_G}, ${PARTICLE_B}, ${lineAlpha})`;
                    ctx.lineWidth = 0.6;
                    ctx.stroke();
                }
            }
        }

        animationFrame = requestAnimationFrame(draw);
    }

    resize();
    createParticles();
    draw();

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            resize();
            createParticles();
        }, 200);
    });
}

/**
 * =============================================
 * SEARCH FUNCTIONALITY
 * Client-side search across Skills, Papers, Resources
 * =============================================
 */
function initSearch() {
    const searchOverlay = document.getElementById('search-overlay');
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');
    const searchBtn = document.getElementById('nav-search-btn');
    const searchClose = document.querySelector('.search-close');

    if (!searchOverlay || !searchInput) return;

    // Build search index from page cards
    const searchIndex = buildSearchIndex();

    // Open search
    const openSearch = () => {
        searchOverlay.classList.add('active');
        searchOverlay.removeAttribute('hidden');
        requestAnimationFrame(() => searchInput.focus());
        document.body.style.overflow = 'hidden';
        showSearchHint(searchResults);
    };

    // Close search
    const closeSearch = () => {
        searchOverlay.classList.remove('active');
        searchInput.value = '';
        searchResults.innerHTML = '';
        document.body.style.overflow = '';
        showSearchHint(searchResults);
    };

    if (searchBtn) {
        searchBtn.addEventListener('click', openSearch);
    }

    if (searchClose) {
        searchClose.addEventListener('click', closeSearch);
    }

    // Close on overlay background click
    searchOverlay.addEventListener('click', (e) => {
        if (e.target === searchOverlay) closeSearch();
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && searchOverlay.classList.contains('active')) {
            closeSearch();
        }
        // Open search with Cmd/Ctrl+K
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            searchOverlay.classList.contains('active') ? closeSearch() : openSearch();
        }
    });

    // Live search
    let searchDebounce;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(() => {
            const query = searchInput.value.trim();
            if (query.length < 2) {
                showSearchHint(searchResults);
                return;
            }
            const results = performSearch(query, searchIndex);
            renderSearchResults(results, query, searchResults);
        }, 120);
    });

    // Show initial hint
    showSearchHint(searchResults);
}

function showSearchHint(container) {
    container.innerHTML = `
        <p class="search-hint">
            Type to search skills, papers, and tools &nbsp;·&nbsp; Press <kbd style="background:var(--bg-tertiary);border:1px solid var(--border-default);border-radius:4px;padding:1px 5px;font-size:0.8rem;">Esc</kbd> to close
        </p>`;
}

function buildSearchIndex() {
    const index = [];

    // Index skill cards
    document.querySelectorAll('.skill-card:not(.paper-card):not(.resource-card)').forEach(card => {
        const title = card.querySelector('.skill-title')?.textContent?.trim() || '';
        const desc = card.querySelector('.skill-description')?.textContent?.trim() || '';
        const link = card.querySelector('.skill-link')?.getAttribute('href') || '#';
        const tags = Array.from(card.querySelectorAll('.tag')).map(t => t.textContent.trim()).join(' ');
        if (title) {
            index.push({ type: 'skill', title, desc, link, tags });
        }
    });

    // Index paper cards
    document.querySelectorAll('.paper-card').forEach(card => {
        const title = card.querySelector('.skill-title')?.textContent?.trim() || '';
        const desc = card.querySelector('.skill-description')?.textContent?.trim() || '';
        const link = card.querySelector('.skill-link')?.getAttribute('href') || '#';
        const tags = Array.from(card.querySelectorAll('.tag')).map(t => t.textContent.trim()).join(' ');
        if (title) {
            index.push({ type: 'paper', title, desc, link, tags });
        }
    });

    // Index resource cards
    document.querySelectorAll('.resource-card').forEach(card => {
        const title = card.querySelector('.skill-title')?.textContent?.trim() || '';
        const desc = card.querySelector('.skill-description')?.textContent?.trim() || '';
        const link = card.querySelector('.skill-link')?.getAttribute('href') || '#';
        const tags = Array.from(card.querySelectorAll('.tag')).map(t => t.textContent.trim()).join(' ');
        if (title) {
            index.push({ type: 'resource', title, desc, link, tags });
        }
    });

    return index;
}

function performSearch(query, index) {
    const q = query.toLowerCase();
    const terms = q.split(/\s+/).filter(Boolean);

    return index
        .map(item => {
            const searchText = `${item.title} ${item.desc} ${item.tags}`.toLowerCase();
            let score = 0;

            terms.forEach(term => {
                if (item.title.toLowerCase().includes(term)) score += 10;
                if (item.desc.toLowerCase().includes(term)) score += 4;
                if (item.tags.toLowerCase().includes(term)) score += 2;
            });

            return { ...item, score };
        })
        .filter(item => item.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 12);
}

function highlightText(text, query) {
    if (!query) return text;
    const terms = query.split(/\s+/).filter(Boolean);
    let result = text;
    terms.forEach(term => {
        const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        result = result.replace(regex, '<mark style="background:rgba(37,99,235,0.15);color:var(--accent-secondary);border-radius:2px;padding:0 2px;">$1</mark>');
    });
    return result;
}

function renderSearchResults(results, query, container) {
    if (!results.length) {
        container.innerHTML = `
            <div class="search-empty">
                <div style="font-size:2rem;margin-bottom:0.5rem;">🔍</div>
                No results for "<strong>${query}</strong>"
                <div style="margin-top:0.75rem;font-size:0.8rem;">Try different keywords or browse the sections below</div>
            </div>`;
        return;
    }

    const typeLabels = { skill: 'Skill', paper: 'Paper', resource: 'Tool' };
    const html = results.map(item => `
        <a href="${item.link}" class="search-result-item" style="display:block;text-decoration:none;">
            <div class="search-result-type type-${item.type}">${typeLabels[item.type] || item.type}</div>
            <div class="search-result-title">${highlightText(item.title, query)}</div>
            <div class="search-result-desc">${highlightText(item.desc.slice(0, 120) + (item.desc.length > 120 ? '…' : ''), query)}</div>
        </a>
    `).join('');

    container.innerHTML = `
        <div style="font-size:0.8rem;color:var(--text-tertiary);margin-bottom:10px;text-align:right;">
            ${results.length} result${results.length !== 1 ? 's' : ''}
        </div>
        ${html}`;
}

/**
 * =============================================
 * TYPEWRITER ANIMATION for Hero Code Preview
 * =============================================
 */
function initTypewriter() {
    const codeEl = document.querySelector('.code-content code');
    if (!codeEl) return;

    // Don't animate if reduced motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const lines = [
        { text: '$ claude', color: '#7f5af0', delay: 800 },
        { text: '', delay: 400 },
        { text: '# Finding relevant literature...', color: '#72748d', delay: 200 },
        { text: '', delay: 300 },
        { text: '> /literature-review Find seminal papers', color: '', delay: 100 },
        { text: '  on AI in Sociology from 2023-2025', color: '', delay: 100 },
        { text: '', delay: 400 },
        { text: '✓ Found 15 papers from public sources', color: '#2cb67d', delay: 60 },
        { text: '✓ Generating summary matrix...', color: '#2cb67d', delay: 60 },
        { text: '✓ Exporting to Zotero...', color: '#2cb67d', delay: 60 },
    ];

    // Clear original content
    codeEl.innerHTML = '';

    let lineIndex = 0;
    let charIndex = 0;
    let currentSpan = null;
    let totalDelay = 1000; // Start after page loads

    const typeChar = () => {
        if (lineIndex >= lines.length) {
            // Add blinking cursor at end
            const cursor = document.createElement('span');
            cursor.className = 'typewriter-cursor';
            codeEl.appendChild(cursor);
            return;
        }

        const line = lines[lineIndex];

        if (charIndex === 0) {
            // Start new line
            currentSpan = document.createElement('span');
            if (line.color) currentSpan.style.color = line.color;
            codeEl.appendChild(currentSpan);
        }

        if (charIndex < line.text.length) {
            currentSpan.textContent += line.text[charIndex];
            charIndex++;
            setTimeout(typeChar, 28);
        } else {
            // End of line
            codeEl.appendChild(document.createTextNode('\n'));
            lineIndex++;
            charIndex = 0;
            setTimeout(typeChar, line.delay || 80);
        }
    };

    setTimeout(typeChar, totalDelay);
}

/**
 * =============================================
 * SCROLL-TO-TOP BUTTON
 * =============================================
 */
function initScrollToTop() {
    // Create button
    const btn = document.createElement('button');
    btn.id = 'scroll-top-btn';
    btn.setAttribute('aria-label', 'Scroll to top');
    btn.innerHTML = '↑';
    document.body.appendChild(btn);

    // Show/hide based on scroll position
    const toggleVisibility = () => {
        btn.classList.toggle('visible', window.scrollY > 500);
    };

    window.addEventListener('scroll', toggleVisibility, { passive: true });

    btn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}
