/**
 * SHIELD — Scanner Controller (Enhanced)
 * Handles all scanner interactions: Image, Audio, Text, URL
 * Preset demos, fingerprint demo, browser TTS fallback
 * WOW FEATURES: Explainable AI breakdown, WhatsApp sim, share report, sound effects
 */

// ============ STATE ============
let selectedImageFile = null;
let selectedAudioFile = null;
let lastAnalysisText = null;
let lastAnalysisTime = null;
let fingerprintDemoCount = 0;
let lastResultData = null;  // Store for sharing

// ============ PRESET DEMOS ============
const PRESETS = {
    digital_arrest: "नमस्ते, मैं CBI से बोल रहा हूँ। आपके नाम पर एक money laundering case दर्ज हुआ है। आपके Aadhaar card से कुछ suspicious transactions हुई हैं। अगर आपने तुरंत cooperate नहीं किया तो हम आपको arrest कर लेंगे। आपको अभी एक security deposit जमा करना होगा।",
    fake_kyc: "Dear Customer, Your SBI account KYC is expiring today. Update your Aadhaar and PAN now or your account will be permanently blocked by RBI. Click here to verify immediately: http://sbi-kyc-update.xyz/verify. Last chance - only 2 hours remaining.",
    upi_scam: "Hi, I accidentally sent Rs 5000 to your PhonePe account by mistake. Can you please reverse the payment? If you don't return it within 30 minutes, I will file a police complaint. My UPI ID: scammer@paytm",
    lottery: "🎉 CONGRATULATIONS! You have won Rs 25,00,000 in Jio KBC Lucky Draw 2025. Send Rs 2500 as processing fee to claim. Contact: 9876543210. Offer valid today only! Claim now: https://kbc-prize.tk/winner",
    utility: "⚠️ FINAL NOTICE: Your electricity connection (Account: 987654) will be disconnected TODAY at 3:00 PM due to non-payment of Rs 1,247. Pay immediately to avoid disconnection. Click: https://pay-bill.buzz/quick",
    investment: "💰 GUARANTEED 100% returns in 30 days! Invest just Rs 10,000 today in our crypto trading bot and get Rs 1,00,000 back. Limited slots available. Join our exclusive WhatsApp group: https://bit.ly/get-rich",
    safe: "Hello! Your Amazon order #12345 has been shipped. Expected delivery: March 2. Track your package at amazon.in/orders. Thank you for shopping with us!"
};

function loadPreset(key) {
    const textarea = document.getElementById('text-input');
    if (textarea && PRESETS[key]) {
        textarea.value = PRESETS[key];
        textarea.focus();
    }
}

// ============ SOUND EFFECTS ============
function playAlertSound(verdict) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = ctx.createOscillator();
        const gainNode = ctx.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(ctx.destination);

        if (verdict === 'HIGH_RISK') {
            // Urgent: three short beeps
            oscillator.frequency.setValueAtTime(880, ctx.currentTime);
            gainNode.gain.setValueAtTime(0.15, ctx.currentTime);
            oscillator.start(ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
            gainNode.gain.setValueAtTime(0.15, ctx.currentTime + 0.15);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
            gainNode.gain.setValueAtTime(0.15, ctx.currentTime + 0.3);
            gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
            oscillator.stop(ctx.currentTime + 0.5);
        } else if (verdict === 'CAUTION') {
            // Two gentle tones
            oscillator.frequency.setValueAtTime(660, ctx.currentTime);
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime + 0.2);
            gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            oscillator.stop(ctx.currentTime + 0.4);
        } else {
            // Safe: pleasant ding
            oscillator.frequency.setValueAtTime(523, ctx.currentTime);
            oscillator.frequency.setValueAtTime(659, ctx.currentTime + 0.1);
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            oscillator.stop(ctx.currentTime + 0.4);
        }
    } catch (e) { /* Audio not available */ }
}

// ============ FILE HANDLING ============
function handleDrop(e, type) {
    e.preventDefault();
    e.stopPropagation();
    const zone = document.getElementById(type + '-drop-zone');
    if (zone) zone.classList.remove('drag-over');

    const file = e.dataTransfer.files[0];
    if (file) processFile(file, type);
}

function handleDragOver(e) {
    e.preventDefault();
    e.target.closest('.upload-area')?.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.target.closest('.upload-area')?.classList.remove('drag-over');
}

function handleFileSelect(input, type) {
    const file = input.files[0];
    if (file) processFile(file, type);
}

function processFile(file, type) {
    if (type === 'image') {
        selectedImageFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            document.getElementById('preview-img').src = e.target.result;
            document.getElementById('image-preview').style.display = 'block';
            document.getElementById('image-drop-zone').style.display = 'none';
            document.getElementById('analyze-image-btn').disabled = false;
        };
        reader.readAsDataURL(file);
    } else if (type === 'audio') {
        selectedAudioFile = file;
        document.getElementById('audio-filename').textContent = file.name;
        document.getElementById('audio-preview').style.display = 'block';
        document.getElementById('audio-drop-zone').style.display = 'none';
        document.getElementById('analyze-audio-btn').disabled = false;
    }
}

function removeFile(type) {
    if (type === 'image') {
        selectedImageFile = null;
        document.getElementById('image-preview').style.display = 'none';
        document.getElementById('image-drop-zone').style.display = '';
        document.getElementById('analyze-image-btn').disabled = true;
        document.getElementById('image-input').value = '';
    } else if (type === 'audio') {
        selectedAudioFile = null;
        document.getElementById('audio-preview').style.display = 'none';
        document.getElementById('audio-drop-zone').style.display = '';
        document.getElementById('analyze-audio-btn').disabled = true;
        document.getElementById('audio-input').value = '';
    }
}

// Click to browse
document.addEventListener('click', (e) => {
    const zone = e.target.closest('.upload-area');
    if (zone) {
        const input = zone.querySelector('input[type="file"]');
        if (input) input.click();
    }
});

// ============ ANALYZE FUNCTIONS ============
async function analyzeImage() {
    if (!selectedImageFile) return;
    const scanType = 'image';
    showLoading(scanType, 'Extracting text via AWS Textract OCR...');

    const formData = new FormData();
    formData.append('file', selectedImageFile);
    formData.append('language', typeof currentLanguage !== 'undefined' ? currentLanguage : 'en');

    try {
        const startTime = Date.now();
        const response = await fetch('/api/analyze/image', { method: 'POST', body: formData });
        const data = await response.json();
        data.latency_ms = data.latency_ms || (Date.now() - startTime);

        hideLoading(scanType);
        renderResults(data, scanType);
        playAlertSound(data.verdict);

        if (typeof saveScanToHistory === 'function') {
            saveScanToHistory(data.ocr_text || 'Image scan', data.verdict, data.scam_type);
        }
        speakResult(data);
    } catch (error) {
        hideLoading(scanType);
        showError(scanType, 'Analysis failed. Please try again.');
    }
}

async function analyzeAudio() {
    if (!selectedAudioFile) return;
    const scanType = 'audio';
    showLoading(scanType, 'Transcribing audio via AWS Transcribe...');

    const formData = new FormData();
    formData.append('file', selectedAudioFile);
    formData.append('language', typeof currentLanguage !== 'undefined' ? currentLanguage : 'en');

    try {
        const startTime = Date.now();
        const response = await fetch('/api/analyze/audio', { method: 'POST', body: formData });
        const data = await response.json();
        data.latency_ms = data.latency_ms || (Date.now() - startTime);

        hideLoading(scanType);
        renderResults(data, scanType);
        playAlertSound(data.verdict);

        if (typeof saveScanToHistory === 'function') {
            saveScanToHistory(data.transcript || 'Audio scan', data.verdict, data.scam_type);
        }
        speakResult(data);
    } catch (error) {
        hideLoading(scanType);
        showError(scanType, 'Analysis failed. Please try again.');
    }
}

async function analyzeText() {
    const textarea = document.getElementById('text-input');
    const text = textarea?.value?.trim();
    if (!text) return;

    const scanType = 'text';
    showLoading(scanType, 'Checking fingerprint cache...');

    try {
        const startTime = Date.now();
        const response = await fetch('/api/analyze/text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                language: typeof currentLanguage !== 'undefined' ? currentLanguage : 'en'
            })
        });
        const data = await response.json();
        const elapsed = Date.now() - startTime;
        data.latency_ms = data.latency_ms || elapsed;
        data._originalText = text;

        hideLoading(scanType);
        renderResults(data, scanType);
        playAlertSound(data.verdict);

        // Fingerprint demo logic
        updateFingerprintDemo(text, data);

        if (typeof saveScanToHistory === 'function') {
            saveScanToHistory(text, data.verdict, data.scam_type);
        }
        speakResult(data);
    } catch (error) {
        hideLoading(scanType);
        showError(scanType, 'Analysis failed. Please try again.');
    }
}

async function analyzeUrl() {
    const input = document.getElementById('url-input');
    const url = input?.value?.trim();
    if (!url) return;

    const scanType = 'url';
    showLoading(scanType, 'Checking URL patterns...');

    try {
        const response = await fetch('/api/analyze/url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, language: typeof currentLanguage !== 'undefined' ? currentLanguage : 'en' })
        });
        const data = await response.json();

        hideLoading(scanType);
        renderResults(data, scanType);
        playAlertSound(data.verdict);

        if (typeof saveScanToHistory === 'function') {
            saveScanToHistory(url, data.verdict, data.scam_type);
        }
        speakResult(data);
    } catch (error) {
        hideLoading(scanType);
        showError(scanType, 'Analysis failed. Please try again.');
    }
}

// ============ FINGERPRINT DEMO ============
function updateFingerprintDemo(text, data) {
    const fpDemo = document.getElementById('fingerprint-demo');
    if (!fpDemo) return;

    if (text === lastAnalysisText) {
        fpDemo.style.display = 'block';
        document.getElementById('fp-first-time').textContent = (lastAnalysisTime / 1000).toFixed(1) + 's';
        const cachedTime = data.cached ? (data.latency_ms || 200) : data.latency_ms;
        document.getElementById('fp-second-time').textContent = cachedTime + 'ms';
        fingerprintDemoCount++;
    } else {
        lastAnalysisText = text;
        lastAnalysisTime = data.latency_ms || 1500;
        fpDemo.style.display = 'block';
        document.getElementById('fp-first-time').textContent = (lastAnalysisTime / 1000).toFixed(1) + 's';
        document.getElementById('fp-second-time').textContent = '—';
    }
}

// ============ UI HELPERS ============
function showLoading(scanType, tip) {
    const loader = document.getElementById('scanner-loading-' + scanType);
    const results = document.getElementById('scanner-results-' + scanType);
    if (loader) { loader.style.display = 'block'; }
    if (results) { results.style.display = 'none'; }
    const tipEl = document.getElementById('loader-tip-' + scanType);
    if (tipEl) tipEl.textContent = tip || '';
}

function hideLoading(scanType) {
    const loader = document.getElementById('scanner-loading-' + scanType);
    if (loader) loader.style.display = 'none';
}

function showError(scanType, message) {
    const results = document.getElementById('scanner-results-' + scanType);
    if (results) {
        results.style.display = 'block';
        results.innerHTML = `<div class="result-verdict verdict-caution" style="margin-top:1rem;">
            <div class="verdict-icon">⚠️</div>
            <div class="verdict-label">${message}</div>
        </div>`;
    }
}

function renderResults(data, scanType) {
    const container = document.getElementById('scanner-results-' + scanType);
    if (!container) return;

    lastResultData = data;
    const verdict = data.verdict || 'CAUTION';
    const confidence = data.confidence || 50;
    const lang = typeof currentLanguage !== 'undefined' ? currentLanguage : 'en';

    const verdictMap = {
        'SAFE': { cls: 'verdict-safe', icon: '●', label: 'SAFE', color: '#22c55e' },
        'CAUTION': { cls: 'verdict-caution', icon: '△', label: 'CAUTION', color: '#f59e0b' },
        'HIGH_RISK': { cls: 'verdict-danger', icon: '▲', label: 'HIGH RISK', color: '#ef4444' },
    };

    const v = verdictMap[verdict] || verdictMap['CAUTION'];
    const explanation = lang === 'hi' ? (data.explanation_hi || data.explanation_en || '') : (data.explanation_en || data.explanation_hi || '');

    let html = `
        <div class="result-verdict ${v.cls}">
            <div class="verdict-icon">${v.icon}</div>
            <div class="verdict-label">${v.label}</div>
            ${data.scam_type ? `<div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.3rem">${data.scam_type.replace(/_/g, ' ')}</div>` : ''}
            <div class="confidence-bar"><div class="confidence-fill" style="width:${confidence}%;background:${v.color}"></div></div>
            <div class="confidence-text">${confidence}% confidence</div>
            <div class="latency-badge ${data.cached ? 'cached' : ''}">
                ${data.cached ? 'CACHED' : 'Bedrock'} · ${data.latency_ms || '—'}ms
            </div>
        </div>
    `;

    // === EXPLAINABLE AI CONFIDENCE BREAKDOWN ===
    if (data.confidence_breakdown) {
        const breakdown = data.confidence_breakdown;
        const total = Object.values(breakdown).reduce((s, v) => s + v, 0);
        html += `<div class="confidence-breakdown"><h4>AI Confidence Breakdown — ${confidence}%</h4>`;
        Object.entries(breakdown).forEach(([label, value]) => {
            const pct = Math.round((value / total) * confidence);
            const fillClass = value >= 28 ? 'fill-high' : value >= 18 ? 'fill-medium' : 'fill-low';
            html += `<div class="breakdown-bar">
                <span class="breakdown-label">${label}</span>
                <div class="breakdown-track">
                    <div class="breakdown-fill ${fillClass}" data-width="${value}">${value}%</div>
                </div>
            </div>`;
        });
        html += `<div class="breakdown-total">Combined signal strength: <strong>${total}%</strong></div></div>`;
    }

    // Explanation
    html += `<div class="result-explain"><h4>Analysis</h4><p style="color:var(--text-secondary);font-size:0.9rem;line-height:1.6">${explanation}</p></div>`;

    // Red flags
    if (data.red_flags && data.red_flags.length > 0) {
        html += `<div class="result-section"><h4>Red Flags</h4>`;
        data.red_flags.forEach(flag => {
            html += `<div class="explain-item"><span style="color:var(--danger)">•</span><span>${flag}</span></div>`;
        });
        html += `</div>`;
    }

    // Advice
    if (data.advice && data.advice.length > 0) {
        html += `<div class="result-section"><h4>Recommended Actions</h4>`;
        data.advice.forEach(tip => {
            html += `<div class="explain-item"><span>→</span><span>${tip}</span></div>`;
        });
        html += `</div>`;
    }

    // OCR text (for image)
    if (data.ocr_text) {
        html += `<div class="result-section"><h4>Extracted Text (OCR)</h4><p style="font-size:0.8rem;color:var(--text-muted);font-family:monospace;white-space:pre-wrap">${data.ocr_text}</p></div>`;
    }

    // Transcript (for audio)
    if (data.transcript) {
        html += `<div class="result-section"><h4>Transcript</h4><p style="font-size:0.8rem;color:var(--text-muted);font-family:monospace;white-space:pre-wrap">${data.transcript}</p></div>`;
    }

    // URL analyzed
    if (data.url_analyzed) {
        html += `<div class="result-section"><h4>URL Analyzed</h4><p style="font-size:0.8rem;color:var(--text-muted);font-family:monospace;word-break:break-all">${data.url_analyzed}</p></div>`;
    }

    // Fingerprint
    if (data.fingerprint) {
        html += `<div class="result-fingerprint"><span class="fp-label">Fingerprint:</span><span class="fp-hash">${data.fingerprint}</span></div>`;
    }

    // === ACTION BUTTONS: Voice + Share + WhatsApp Sim ===
    const dataForBtn = JSON.stringify(data).replace(/'/g, "\\'").replace(/"/g, '&quot;');
    html += `<div class="share-actions">
        <button class="btn btn-primary" onclick='speakResult(lastResultData)' style="padding:0.6rem 1.2rem;font-size:0.85rem">
            ${lang === 'hi' ? 'आवाज़ में सुनें' : 'Listen'}
        </button>
        <button class="btn-share" onclick="shareReport()">Copy Report</button>
        <button class="btn-share" onclick="shareWhatsApp()">Share via WhatsApp</button>
    </div>`;

    // === WHATSAPP FORWARD SIMULATION ===
    if (data._originalText || scanType === 'text') {
        const msgText = (data._originalText || '').substring(0, 120);
        const waClass = verdict === 'HIGH_RISK' ? 'wa-verdict-danger' : verdict === 'CAUTION' ? 'wa-verdict-caution' : 'wa-verdict-safe';
        const waLabel = verdict === 'HIGH_RISK' ? '🚨 SCAM DETECTED' : verdict === 'CAUTION' ? '⚠️ SUSPICIOUS' : '✅ LOOKS SAFE';
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

        html += `
        <div class="wa-sim-trigger">
            <button class="btn-wa-sim" onclick="document.getElementById('wa-sim-${scanType}').style.display='block'; this.style.display='none'">
                📱 See this as WhatsApp "Forward to SHIELD"
            </button>
        </div>
        <div class="wa-sim" id="wa-sim-${scanType}" style="display:none">
            <div class="wa-header">
                <div class="wa-avatar">🛡️</div>
                <span class="wa-name">SHIELD Bot</span>
                <span class="wa-badge">Verified</span>
            </div>
            <div class="wa-chat">
                <div class="wa-msg wa-msg-in">
                    <div class="wa-fwd-label">↪️ Forwarded</div>
                    <div>${msgText}${msgText.length >= 120 ? '...' : ''}</div>
                    <div class="wa-msg-time">${timeStr}</div>
                </div>
                <div class="wa-msg wa-msg-shield">
                    <div class="wa-shield-label">🛡️ SHIELD Analysis</div>
                    <div><span class="wa-verdict-badge ${waClass}">${waLabel}</span></div>
                    <div style="margin-top:0.4rem;font-size:0.8rem">${explanation.substring(0, 100)}${explanation.length > 100 ? '...' : ''}</div>
                    <div style="margin-top:0.3rem;font-size:0.7rem;color:#8696a0">Confidence: ${confidence}% · Powered by AWS Bedrock</div>
                    <div class="wa-msg-time">${timeStr}</div>
                </div>
            </div>
        </div>`;
    }

    container.innerHTML = html;
    container.style.display = 'block';

    // Animate breakdown bars after render
    setTimeout(() => {
        container.querySelectorAll('.breakdown-fill').forEach(bar => {
            const w = bar.dataset.width;
            if (w) bar.style.width = w + '%';
        });
    }, 100);
}

// ============ SHARE REPORT ============
function shareReport() {
    if (!lastResultData) return;
    const data = lastResultData;
    const verdict = data.verdict || 'UNKNOWN';
    const explanation = data.explanation_en || data.explanation_hi || '';

    let report = `🛡️ SHIELD Scam Analysis Report\n`;
    report += `${'='.repeat(35)}\n\n`;
    report += `⚡ Verdict: ${verdict}\n`;
    report += `📊 Confidence: ${data.confidence || 0}%\n`;
    if (data.scam_type) report += `🏷️ Type: ${data.scam_type.replace(/_/g, ' ')}\n`;
    report += `\n📋 Analysis:\n${explanation}\n`;

    if (data.red_flags && data.red_flags.length > 0) {
        report += `\n🚩 Red Flags:\n`;
        data.red_flags.forEach(f => report += `  • ${f}\n`);
    }
    if (data.advice && data.advice.length > 0) {
        report += `\n💡 What To Do:\n`;
        data.advice.forEach(a => report += `  → ${a}\n`);
    }

    report += `\n---\nAnalyzed by SHIELD — AI Guardian for India's Seniors\n🔗 shield.ai | ☎️ Cyber Crime: 1930`;

    navigator.clipboard.writeText(report).then(() => {
        showCopyToast('✅ Report copied to clipboard!');
    }).catch(() => {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = report;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showCopyToast('✅ Report copied to clipboard!');
    });
}

function shareWhatsApp() {
    if (!lastResultData) return;
    const data = lastResultData;
    const verdict = data.verdict || 'UNKNOWN';
    const explanation = data.explanation_en || data.explanation_hi || '';

    let msg = `🛡️ *SHIELD Alert*\n`;
    msg += `Verdict: *${verdict}* (${data.confidence}%)\n`;
    if (data.scam_type) msg += `Type: ${data.scam_type.replace(/_/g, ' ')}\n`;
    msg += `\n${explanation}\n`;
    msg += `\n⚠️ Report suspected scams: 1930`;

    const url = `https://wa.me/?text=${encodeURIComponent(msg)}`;
    window.open(url, '_blank');
}

function showCopyToast(message) {
    let toast = document.getElementById('copy-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'copy-toast';
        toast.className = 'copy-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2000);
}

// ============ BROWSER TTS FALLBACK ============
function speakResult(data) {
    const lang = typeof currentLanguage !== 'undefined' ? currentLanguage : 'en';
    const explanation = lang === 'hi' ? (data.explanation_hi || data.explanation_en) : (data.explanation_en || data.explanation_hi);

    let speechText = '';
    if (data.verdict === 'HIGH_RISK') {
        speechText = lang === 'hi'
            ? `सावधान! यह एक घोटाला है। ${explanation}। कृपया किसी लिंक पर क्लिक न करें।`
            : `Warning! This is a scam. ${explanation}. Do not click any links.`;
    } else if (data.verdict === 'CAUTION') {
        speechText = lang === 'hi'
            ? `ध्यान दीजिए। ${explanation}। सत्यापित करें।`
            : `Be careful. ${explanation}. Please verify before proceeding.`;
    } else {
        speechText = lang === 'hi'
            ? `अच्छी खबर! ${explanation}।`
            : `Good news! ${explanation}.`;
    }

    // Try Polly first, fallback to browser speechSynthesis
    fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: speechText, language: lang })
    })
        .then(r => {
            if (r.ok && r.headers.get('content-type')?.includes('audio')) {
                return r.blob();
            }
            throw new Error('No Polly audio');
        })
        .then(blob => {
            if (blob.size > 0) {
                const audio = new Audio(URL.createObjectURL(blob));
                audio.play().catch(() => browserTTS(speechText, lang));
            } else {
                browserTTS(speechText, lang);
            }
        })
        .catch(() => {
            browserTTS(speechText, lang);
        });
}

function browserTTS(text, lang) {
    if (!('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.85;
    utterance.pitch = 1;

    const voices = window.speechSynthesis.getVoices();
    if (lang === 'hi') {
        const hindiVoice = voices.find(v => v.lang.startsWith('hi'));
        if (hindiVoice) utterance.voice = hindiVoice;
        utterance.lang = 'hi-IN';
    } else {
        const indianVoice = voices.find(v => v.lang === 'en-IN');
        const enVoice = indianVoice || voices.find(v => v.lang.startsWith('en'));
        if (enVoice) utterance.voice = enVoice;
        utterance.lang = 'en-IN';
    }

    window.speechSynthesis.speak(utterance);
}

// Load voices
if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => { };
    window.speechSynthesis.getVoices();
}
