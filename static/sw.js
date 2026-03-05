const CACHE_NAME = 'shield-v6';
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/styles.css?v=6',
    '/static/js/main.js',
    '/static/js/scanner.js',
    '/static/js/globe.js',
    '/static/manifest.json',
];

// Install — pre-cache core assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SHIELD SW] Caching core assets');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
    self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            );
        })
    );
    self.clients.claim();
});

// Fetch — network-first for API, cache-first for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API calls: network-first with timeout fallback
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Cache successful API responses
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, clone);
                    });
                    return response;
                })
                .catch(() => {
                    return caches.match(event.request).then(cached => {
                        return cached || new Response(
                            JSON.stringify({
                                error: 'offline',
                                message: 'You are offline. Please check your connection.',
                                verdict: 'CAUTION',
                                confidence: 0,
                                explanation_en: 'Unable to analyze — you are currently offline.',
                                explanation_hi: 'विश्लेषण नहीं हो पा रहा — आप ऑफ़लाइन हैं।',
                                red_flags: [],
                                advice: ['Please reconnect to the internet and try again.']
                            }),
                            { headers: { 'Content-Type': 'application/json' } }
                        );
                    });
                })
        );
        return;
    }

    // Static assets: cache-first
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;
            return fetch(event.request).then(response => {
                // Cache new static assets
                if (response.status === 200) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            });
        }).catch(() => {
            // Offline fallback for navigation
            if (event.request.mode === 'navigate') {
                return caches.match('/');
            }
        })
    );
});
