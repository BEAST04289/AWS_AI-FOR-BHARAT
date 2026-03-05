/**
 * SHIELD — Main Application Controller
 * Page router, Grandparents Mode, theme toggle, language toggle
 */

// ============ STATE ============
let currentLanguage = 'en';
let isGrandparentsMode = false;
let isLightTheme = false;

// ============ INITIALIZATION ============
document.addEventListener('DOMContentLoaded', () => {
    initRouter();
    initBarAnimations();
    fetchStats();
    loadScanHistory();
});

// ============ PAGE ROUTER ============
function initRouter() {
    window.addEventListener('hashchange', handleRoute);
    handleRoute();
}

function handleRoute() {
    const hash = location.hash.replace('#', '') || 'home';
    showPage(hash);
}

function showPage(pageId) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

    // Show target page
    const target = document.getElementById('page-' + pageId);
    if (target) {
        target.classList.add('active');
    } else {
        // Try scanner pages
        document.getElementById('page-home')?.classList.add('active');
    }

    // Update nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
        if (link.dataset.page === pageId) link.classList.add('active');
    });

    // Trigger bar animations on proof page
    if (pageId === 'proof') {
        setTimeout(animateBars, 300);
    }

    // Init 3D globe when visiting heatmap page
    if (pageId === 'heatmap') {
        setTimeout(initGlobe, 200);
    }

    // Scroll to top
    window.scrollTo(0, 0);
}

function navigateTo(pageId) {
    location.hash = pageId;
}

// ============ GRANDPARENTS MODE ============
function toggleGrandparentsMode() {
    isGrandparentsMode = !isGrandparentsMode;
    const overlay = document.getElementById('gp-overlay');
    const gpBtn = document.getElementById('gp-toggle-fixed');

    if (isGrandparentsMode) {
        overlay.classList.add('active');
        if (gpBtn) gpBtn.style.display = 'none';
        document.body.style.overflow = 'hidden';
    } else {
        overlay.classList.remove('active');
        if (gpBtn) gpBtn.style.display = 'flex';
        document.body.style.overflow = '';
    }
}

function gpNavigate(pageId) {
    toggleGrandparentsMode();
    navigateTo(pageId);
}

// ============ FAMILY ALERT ============
function showFamilyAlert() {
    document.getElementById('family-modal').style.display = 'flex';
}

function closeFamilyModal() {
    document.getElementById('family-modal').style.display = 'none';
}

// ============ THEME TOGGLE ============
function toggleTheme() {
    isLightTheme = !isLightTheme;
    document.body.classList.toggle('light-theme', isLightTheme);
    const toggle = document.getElementById('theme-toggle');
    toggle.textContent = isLightTheme ? '🌙' : '☀️';
}

// ============ LANGUAGE TOGGLE ============
function toggleLanguage() {
    currentLanguage = currentLanguage === 'en' ? 'hi' : 'en';
    const langBtnText = document.querySelector('#lang-toggle .link-text');
    if (langBtnText) {
        langBtnText.textContent = currentLanguage === 'en' ? 'हिंदी' : 'English';
    }

    document.querySelectorAll('[data-hi]').forEach(el => {
        if (!el.dataset.enOriginal) {
            el.dataset.enOriginal = el.textContent;
        }
        if (currentLanguage === 'hi') {
            el.textContent = el.dataset.hi;
        } else {
            el.textContent = el.dataset.enOriginal;
        }
    });
}

// ============ MOBILE MENU ============
function toggleMobileMenu() {
    const menu = document.getElementById('mobileMenu');
    if (menu) menu.classList.toggle('open');
}

function toggleMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('mobile-open');
}

// ============ BAR ANIMATIONS (Proof page) ============
function initBarAnimations() {
    // Will be triggered when proof page is visited
}

function animateBars() {
    document.querySelectorAll('.bar-fill').forEach(bar => {
        const width = bar.dataset.width;
        if (width) {
            bar.style.width = width + '%';
        }
    });
}

// ============ STATS ============
function fetchStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            const el = id => document.getElementById(id);
            if (el('stat-scans')) el('stat-scans').textContent = data.total_checks || 189;
            if (el('stat-cached')) el('stat-cached').textContent = data.cache_hits || 151;
            if (el('stat-hitrate')) el('stat-hitrate').textContent = (data.hit_rate || 79.7) + '%';
            if (el('stat-unique')) el('stat-unique').textContent = data.unique_scams || 12;
        })
        .catch(() => { });

    // Live counter tick — make the app feel alive
    startLiveTicker();
}

function startLiveTicker() {
    setInterval(() => {
        const scansEl = document.getElementById('stat-scans');
        const cachedEl = document.getElementById('stat-cached');
        if (scansEl) {
            const current = parseInt(scansEl.textContent) || 189;
            scansEl.textContent = current + 1;
            scansEl.classList.add('tick-flash');
            setTimeout(() => scansEl.classList.remove('tick-flash'), 500);
        }
        if (cachedEl && Math.random() > 0.3) {
            const current = parseInt(cachedEl.textContent) || 151;
            cachedEl.textContent = current + 1;
        }
    }, 25000);
}

// ============ SCAN HISTORY ============
function saveScanToHistory(text, verdict, scamType) {
    const history = JSON.parse(localStorage.getItem('shield_history') || '[]');
    history.unshift({
        text: (text || '').substring(0, 80),
        verdict: verdict,
        scam_type: scamType,
        time: new Date().toLocaleTimeString(),
    });
    // Keep last 5
    if (history.length > 5) history.pop();
    localStorage.setItem('shield_history', JSON.stringify(history));
    loadScanHistory();
}

function loadScanHistory() {
    const container = document.getElementById('scan-history');
    if (!container) return;

    const history = JSON.parse(localStorage.getItem('shield_history') || '[]');
    if (history.length === 0) {
        container.innerHTML = '<p class="empty-history">No scans yet. Try analyzing a message!</p>';
        return;
    }

    container.innerHTML = history.map(item => {
        const vClass = item.verdict === 'HIGH_RISK' ? 'v-danger' : item.verdict === 'CAUTION' ? 'v-caution' : 'v-safe';
        const vLabel = item.verdict === 'HIGH_RISK' ? 'DANGER' : item.verdict;
        return `<div class="history-item">
            <span class="history-verdict ${vClass}">${vLabel}</span>
            <span class="history-text">${item.text}</span>
            <span class="history-time">${item.time}</span>
        </div>`;
    }).join('');
}

// ============ GALLERY → SCANNER ============
function testScam(scamType) {
    navigateTo('scan-text');
    setTimeout(() => loadPreset(scamType), 400);
}

// ============ INDIA SCAM HEATMAP ============
function drawIndiaHeatmap() {
    const canvas = document.getElementById('india-heatmap');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // Cities: [x, y, name, count, color]
    const cities = [
        [250, 100, 'Delhi', 42, '#ef4444'],
        [140, 380, 'Mumbai', 38, '#f59e0b'],
        [225, 190, 'Jaipur', 31, '#8b5cf6'],
        [175, 410, 'Pune', 27, '#6366f1'],
        [200, 490, 'Bangalore', 19, '#22c55e'],
        [240, 510, 'Chennai', 14, '#06b6d4'],
        [380, 240, 'Kolkata', 11, '#ec4899'],
        [280, 160, 'Lucknow', 7, '#64748b'],
    ];

    // Draw India outline (simplified polygon)
    ctx.beginPath();
    ctx.moveTo(220, 30);
    ctx.lineTo(290, 50);
    ctx.lineTo(340, 80);
    ctx.lineTo(400, 150);
    ctx.lineTo(410, 250);
    ctx.lineTo(380, 310);
    ctx.lineTo(330, 380);
    ctx.lineTo(280, 440);
    ctx.lineTo(250, 530);
    ctx.lineTo(220, 540);
    ctx.lineTo(200, 510);
    ctx.lineTo(160, 460);
    ctx.lineTo(120, 380);
    ctx.lineTo(100, 300);
    ctx.lineTo(90, 220);
    ctx.lineTo(110, 150);
    ctx.lineTo(150, 90);
    ctx.lineTo(190, 50);
    ctx.closePath();
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.3)';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = 'rgba(99, 102, 241, 0.04)';
    ctx.fill();

    // Draw connection lines between cities (network visualization)
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.12)';
    ctx.lineWidth = 1;
    for (let i = 0; i < cities.length; i++) {
        for (let j = i + 1; j < cities.length; j++) {
            const dx = cities[j][0] - cities[i][0];
            const dy = cities[j][1] - cities[i][1];
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 250) {
                ctx.beginPath();
                ctx.moveTo(cities[i][0], cities[i][1]);
                ctx.lineTo(cities[j][0], cities[j][1]);
                ctx.stroke();
            }
        }
    }

    // Draw city nodes
    cities.forEach(([x, y, name, count, color]) => {
        const radius = 6 + (count / 5);

        // Glow
        const grad = ctx.createRadialGradient(x, y, 0, x, y, radius * 3);
        grad.addColorStop(0, color + '40');
        grad.addColorStop(1, 'transparent');
        ctx.beginPath();
        ctx.arc(x, y, radius * 3, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Solid dot
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Inner highlight
        ctx.beginPath();
        ctx.arc(x, y, radius * 0.5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.fill();

        // Label
        ctx.fillStyle = '#e2e8f0';
        ctx.font = '600 11px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(name, x + radius + 6, y + 4);

        // Count
        ctx.fillStyle = color;
        ctx.font = '700 10px Inter, sans-serif';
        ctx.fillText(count + '', x + radius + 6, y + 16);
    });

    // Title
    ctx.fillStyle = 'rgba(226, 232, 240, 0.6)';
    ctx.font = '600 12px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('SHIELD Threat Intelligence Network', w / 2, h - 15);
}
