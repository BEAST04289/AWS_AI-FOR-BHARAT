"""
SHIELD - Flask Web Server (Security Hardened)
Routes for the SHIELD web application and API endpoints.
Powered by AWS: Bedrock, Textract, Transcribe, Polly, DynamoDB.

Security: API keys, rate limiting, CORS, RBAC, input validation,
          security headers, file type validation, XSS/injection protection.
"""
import os
import io
import re
import base64
import time
import hmac
import hashlib
import secrets
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from services.bedrock_analyzer import analyze_scam, analyze_url
from services.visual_shield import analyze_image
from services.audio_shield import analyze_audio
from services.tts_service import generate_speech, get_verdict_speech_text
from services.fingerprint import check_cache, store_fingerprint, get_stats, create_fingerprint

app = Flask(__name__)

# ==================== SECURITY CONFIGURATION ====================

# CORS: Only allow requests from our own domain (and localhost for dev)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",")
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# API Key for programmatic access (optional, set in .env)
API_KEY = os.getenv("SHIELD_API_KEY", "")
ADMIN_API_KEY = os.getenv("SHIELD_ADMIN_KEY", "")

# Rate Limiting Config
MAX_REQUESTS_PER_IP = int(os.getenv("MAX_REQUESTS_PER_IP_PER_DAY", 50))
MAX_BURST_PER_MINUTE = int(os.getenv("MAX_BURST_PER_MINUTE", 10))
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", 5)) * 1024 * 1024
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", 5000))
MAX_URL_LENGTH = 2048

# Request tracking (in-memory for prototype; use Redis in production)
request_counts = {}
burst_counts = {}

# Ensure temp directory exists
os.makedirs("temp_audio", exist_ok=True)

# Allowed file types
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a",
                       "audio/webm", "audio/ogg", "audio/flac", "audio/x-wav"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}

# Image magic bytes for validation
IMAGE_MAGIC_BYTES = {
    b'\x89PNG': 'png',
    b'\xff\xd8\xff': 'jpeg',
    b'RIFF': 'webp',  # RIFF....WEBP
    b'GIF8': 'gif',
}


# ==================== SECURITY MIDDLEWARE ====================

@app.after_request
def add_security_headers(response):
    """Add security headers to every response to prevent common attacks."""
    # Prevent XSS
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "media-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy (disable unnecessary browser features)
    response.headers["Permissions-Policy"] = (
        "camera=(), geolocation=(), payment=(), usb=()"
    )

    # Strict Transport Security (for HTTPS in production)
    if os.getenv("FLASK_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


@app.before_request
def global_request_validation():
    """Validate all incoming requests before processing."""
    # Block requests with suspicious headers
    user_agent = request.headers.get("User-Agent", "")
    if not user_agent or len(user_agent) > 500:
        return jsonify({"error": "Invalid request"}), 400

    # Enforce maximum content length (10MB absolute max)
    if request.content_length and request.content_length > 10 * 1024 * 1024:
        return jsonify({"error": "Request too large"}), 413


# ==================== RATE LIMITING ====================

def rate_limit(f):
    """Enhanced rate limiter: per-IP daily limit + burst protection."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        # Take only the first IP if proxied
        if "," in ip:
            ip = ip.split(",")[0].strip()

        today = time.strftime("%Y-%m-%d")
        now_minute = time.strftime("%Y-%m-%d-%H-%M")
        daily_key = f"{ip}:{today}"
        burst_key = f"{ip}:{now_minute}"

        # Clean stale entries (prevent memory leak)
        stale_daily = [k for k in request_counts if not k.endswith(today)]
        for k in stale_daily:
            del request_counts[k]
        stale_burst = [k for k in burst_counts if not k.endswith(now_minute)]
        for k in stale_burst:
            del burst_counts[k]

        # Burst limit (per minute)
        burst_counts.setdefault(burst_key, 0)
        if burst_counts[burst_key] >= MAX_BURST_PER_MINUTE:
            return jsonify({
                "error": "Too many requests. Please slow down.",
                "retry_after_seconds": 60,
            }), 429

        # Daily limit
        request_counts.setdefault(daily_key, 0)
        if request_counts[daily_key] >= MAX_REQUESTS_PER_IP:
            return jsonify({
                "error": "Daily limit reached. Please try again tomorrow.",
                "limit": MAX_REQUESTS_PER_IP,
            }), 429

        request_counts[daily_key] += 1
        burst_counts[burst_key] += 1
        return f(*args, **kwargs)

    return decorated_function


# ==================== API KEY AUTHENTICATION ====================

def require_api_key(f):
    """Require API key for programmatic access (optional — browser UI is exempt)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If no API key is configured, allow all requests (open mode)
        if not API_KEY:
            return f(*args, **kwargs)

        # Check for API key in header
        provided_key = request.headers.get("X-API-Key", "")
        # Also accept Bearer token format
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:]

        # Browser requests from same origin don't need API key (CORS handles it)
        referer = request.headers.get("Referer", "")
        is_browser_request = any(origin in referer for origin in ALLOWED_ORIGINS)
        if is_browser_request:
            return f(*args, **kwargs)

        # Validate API key with constant-time comparison (prevent timing attacks)
        if provided_key and hmac.compare_digest(provided_key, API_KEY):
            return f(*args, **kwargs)

        return jsonify({"error": "Invalid or missing API key"}), 401

    return decorated_function


def require_admin(f):
    """RBAC: Require admin API key for sensitive endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ADMIN_API_KEY:
            return f(*args, **kwargs)

        provided_key = request.headers.get("X-Admin-Key", "")
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:]

        if provided_key and hmac.compare_digest(provided_key, ADMIN_API_KEY):
            return f(*args, **kwargs)

        return jsonify({"error": "Admin access required"}), 403

    return decorated_function


# ==================== INPUT VALIDATION ====================

def sanitize_text(text):
    """Sanitize text input to prevent XSS and injection attacks."""
    if not isinstance(text, str):
        return None
    # Strip null bytes (injection attempt)
    text = text.replace("\x00", "")
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Limit length
    text = text[:MAX_TEXT_LENGTH]
    return text.strip()


def validate_url(url):
    """Validate and sanitize URL input."""
    if not isinstance(url, str):
        return None, "URL must be a string"
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        return None, f"URL too long. Max {MAX_URL_LENGTH} characters."
    # Must start with http:// or https://
    if not re.match(r'^https?://', url, re.IGNORECASE):
        url = "http://" + url
    # Block local/internal network URLs (SSRF protection)
    blocked_patterns = [
        r'localhost', r'127\.0\.0\.1', r'0\.0\.0\.0',
        r'10\.\d+\.\d+\.\d+', r'172\.(1[6-9]|2\d|3[01])\.\d+\.\d+',
        r'192\.168\.\d+\.\d+', r'169\.254\.\d+\.\d+',
        r'\[::1\]', r'metadata\.google', r'169\.254\.169\.254',
    ]
    for pattern in blocked_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return None, "Internal/private URLs not allowed"
    return url, None


def validate_language(lang):
    """Validate language parameter."""
    allowed = {"en", "hi"}
    if lang not in allowed:
        return "en"
    return lang


def validate_image_file(file_bytes, filename):
    """Validate uploaded image: check magic bytes and extension."""
    if not file_bytes:
        return False, "Empty file"
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, f"File too large. Max {MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
    if len(file_bytes) < 8:
        return False, "File too small to be a valid image"

    # Check extension
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext and ext not in ALLOWED_IMAGE_EXTENSIONS:
            return False, f"File type '{ext}' not allowed. Use PNG, JPG, or WebP."

    # Check magic bytes (content-based validation)
    valid_magic = False
    for magic, fmt in IMAGE_MAGIC_BYTES.items():
        if file_bytes[:len(magic)] == magic:
            valid_magic = True
            break
    if not valid_magic:
        return False, "Invalid image format. Upload a PNG, JPG, or WebP image."

    return True, None


def validate_audio_file(file_bytes, filename):
    """Validate uploaded audio file."""
    if not file_bytes:
        return False, "Empty file"
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, f"File too large. Max {MAX_FILE_SIZE_BYTES // (1024*1024)}MB."
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext and ext not in ALLOWED_AUDIO_EXTENSIONS:
            return False, f"Audio type '{ext}' not allowed. Use WAV, MP3, M4A, FLAC, or OGG."
    return True, None


# ==================== PAGE ROUTES ====================

@app.route("/")
def index():
    """Serve the main SHIELD page."""
    return render_template("index.html")


# ==================== API ROUTES (Protected) ====================

@app.route("/api/analyze/image", methods=["POST"])
@rate_limit
@require_api_key
def api_analyze_image():
    """
    Analyze an uploaded image for scams.
    Flow: Image → Bedrock Vision / Textract OCR → Bedrock Analysis → Polly Voice
    """
    start_time = time.time()

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    language = validate_language(request.form.get("language", "en"))

    try:
        image_bytes = file.read()

        # Validate image
        valid, error = validate_image_file(image_bytes, file.filename)
        if not valid:
            return jsonify({"error": error}), 400

        result = analyze_image(image_bytes, language=language)

        result["latency_ms"] = int((time.time() - start_time) * 1000)
        result["shield_type"] = "visual"

        # Store fingerprint if scam detected
        ocr_text = result.get("ocr_text", "")
        if ocr_text:
            store_fingerprint(ocr_text, result)

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Image analysis error: {e}")
        return jsonify({"error": "Analysis failed. Please try again."}), 500


@app.route("/api/analyze/audio", methods=["POST"])
@rate_limit
@require_api_key
def api_analyze_audio():
    """
    Analyze an uploaded audio recording for scams.
    Flow: Audio → S3 → Transcribe → Bedrock Analysis → Polly Voice
    """
    start_time = time.time()

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    language = validate_language(request.form.get("language", "en"))

    try:
        audio_bytes = file.read()

        # Validate audio
        valid, error = validate_audio_file(audio_bytes, file.filename)
        if not valid:
            return jsonify({"error": error}), 400

        result = analyze_audio(audio_bytes, filename=file.filename, language=language)

        result["latency_ms"] = int((time.time() - start_time) * 1000)
        result["shield_type"] = "audio"

        transcript = result.get("transcript", "")
        if transcript:
            store_fingerprint(transcript, result)

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Audio analysis error: {e}")
        return jsonify({"error": "Analysis failed. Please try again."}), 500


@app.route("/api/analyze/text", methods=["POST"])
@rate_limit
@require_api_key
def api_analyze_text():
    """
    Analyze text input for scams.
    Flow: Text → Fingerprint Check → Bedrock Analysis → Store Fingerprint
    """
    start_time = time.time()

    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"error": "No text provided"}), 400

    # Sanitize input
    text = sanitize_text(data.get("text", ""))
    if not text or len(text) < 3:
        return jsonify({"error": "Text too short. Minimum 3 characters."}), 400
    language = validate_language(data.get("language", "en"))

    try:
        # Check fingerprint cache first (THE INNOVATION)
        cached_result = check_cache(text)
        if cached_result:
            cached_result["latency_ms"] = int((time.time() - start_time) * 1000)
            cached_result["shield_type"] = "text"
            cached_result["cached"] = True
            return jsonify(cached_result)

        # Cache miss → Bedrock analysis
        result = analyze_scam(text, language=language, context="Text Message / SMS")
        result["latency_ms"] = int((time.time() - start_time) * 1000)
        result["shield_type"] = "text"
        result["cached"] = False
        result["fingerprint"] = (create_fingerprint(text) or "")[:16] + "..."

        # Store fingerprint for future users
        store_fingerprint(text, result)

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Text analysis error: {e}")
        return jsonify({"error": "Analysis failed. Please try again."}), 500


@app.route("/api/tts", methods=["POST"])
@rate_limit
@require_api_key
def api_tts():
    """
    Generate Hindi voice response using AWS Polly.
    Returns base64-encoded MP3 audio.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    verdict = data.get("verdict", "CAUTION")
    if verdict not in {"HIGH_RISK", "CAUTION", "SAFE"}:
        verdict = "CAUTION"

    explanation_hi = sanitize_text(data.get("explanation_hi", "")) or ""
    explanation_en = sanitize_text(data.get("explanation_en", "")) or ""
    language = validate_language(data.get("language", "hi"))

    try:
        speech_text = get_verdict_speech_text(verdict, explanation_hi, explanation_en, language)
        audio_bytes = generate_speech(speech_text, language=language)

        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return jsonify({"audio": audio_b64, "text": speech_text})
        else:
            return jsonify({"audio": None, "text": speech_text})

    except Exception as e:
        app.logger.error(f"TTS error: {e}")
        return jsonify({"error": "Voice generation failed."}), 500


@app.route("/api/analyze/url", methods=["POST"])
@rate_limit
@require_api_key
def api_analyze_url():
    """Analyze a URL for phishing/scam patterns."""
    start_time = time.time()

    data = request.get_json(silent=True)
    if not data or not data.get("url"):
        return jsonify({"error": "No URL provided"}), 400

    # Validate and sanitize URL (includes SSRF protection)
    url, error = validate_url(data["url"])
    if error:
        return jsonify({"error": error}), 400

    language = validate_language(data.get("language", "en"))

    try:
        result = analyze_url(url, language=language)
        result["latency_ms"] = int((time.time() - start_time) * 1000)
        result["shield_type"] = "url"
        return jsonify(result)

    except Exception as e:
        app.logger.error(f"URL analysis error: {e}")
        return jsonify({"error": "Analysis failed. Please try again."}), 500


@app.route("/api/stats", methods=["GET"])
@require_admin
def api_stats():
    """Get fingerprint cache statistics. Admin only."""
    try:
        stats = get_stats()
        return jsonify(stats)
    except Exception as e:
        app.logger.error(f"Stats error: {e}")
        return jsonify({"error": "Stats unavailable"}), 500


# ==================== HEALTH CHECK ====================

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for deployment monitoring."""
    return jsonify({
        "status": "healthy",
        "service": "SHIELD",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


# ==================== SERVICE WORKER ====================

@app.route("/sw.js")
def service_worker():
    """Serve the service worker from root scope."""
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


# ==================== STATIC FILES ====================

@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files."""
    return send_from_directory("static", filename)


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(413)
def request_too_large(e):
    return jsonify({"error": "Request too large"}), 413


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ==================== RUN ====================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") != "production"
    api_key_status = "ENABLED" if API_KEY else "OPEN (no key set)"
    admin_key_status = "ENABLED" if ADMIN_API_KEY else "OPEN (no key set)"

    print(f"[SHIELD] Starting on port {port}")
    print(f"   Demo Mode: {os.getenv('DEMO_MODE', 'true')}")
    print(f"   Rate Limit: {MAX_REQUESTS_PER_IP} requests/IP/day, {MAX_BURST_PER_MINUTE}/min burst")
    print(f"   Max File Size: {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")
    print(f"   API Key Auth: {api_key_status}")
    print(f"   Admin Key: {admin_key_status}")
    print(f"   CORS Origins: {ALLOWED_ORIGINS}")
    app.run(host="0.0.0.0", port=port, debug=debug)
