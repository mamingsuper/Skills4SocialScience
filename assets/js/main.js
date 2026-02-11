/**
 * Awesome Econ AI Stuff - Main JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    initFilterGroups();
    initSmoothScroll();
    initNavScroll();
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
                        card.style.animation = 'fadeIn 0.3s ease';
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
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
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
            nav.style.backgroundColor = 'rgba(255, 255, 255, 0.9)';
        } else {
            nav.style.backgroundColor = 'rgba(255, 255, 255, 0.7)';
        }
    });
}

// Add fadeIn animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(style);
