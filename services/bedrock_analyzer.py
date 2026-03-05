"""
SHIELD - Core Scam Analysis Engine (AWS Bedrock)
Uses Claude 3.5 Sonnet via Amazon Bedrock for India-specific scam detection.
"""
import os
import json
import re
import boto3
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# India-specific scam detection system prompt
SYSTEM_PROMPT = """You are SHIELD, an AI guardian protecting Indian seniors from cyber fraud.

CRITICAL INDIA-SPECIFIC SCAM PATTERNS TO DETECT:

1. DIGITAL_ARREST
   - Impersonation: CBI, ED, Police, Customs, Income Tax, Narcotics Bureau
   - Tactics: Video call threats, immediate arrest, money laundering accusations
   - Keywords: "arrest warrant", "drugs parcel", "money laundering", "case filed", "FIR registered"
   
2. FAKE_KYC
   - Impersonation: RBI, SBI, HDFC, Axis Bank, ICICI, PNB
   - Tactics: "Update Aadhaar/PAN or account frozen", urgency within hours
   - Keywords: "KYC update", "account will be blocked", "RBI directive", "verify Aadhaar"
   
3. UPI_SCAM
   - Tactics: "Wrong payment sent to your account", "reverse via link"
   - Keywords: "UPI reversal", "wrong transaction", "refund link", "Google Pay issue"
   
4. UTILITY_THREAT
   - Impersonation: Electricity board, Gas agency, BSNL, Jio
   - Tactics: Disconnection within hours, penalty for non-payment
   - Keywords: "connection will be cut", "pay immediately", "last notice"
   
5. LOTTERY_SCAM
   - Tactics: "You won prize", "claim now", "pay processing fee"
   - Keywords: "lottery", "lucky draw", "prize winner", "KBC", "Jio winner"

6. INVESTMENT_SCAM
   - Tactics: Guaranteed returns, crypto schemes, stock tips
   - Keywords: "guaranteed profit", "100% returns", "invest now", "limited time"

CULTURAL CONTEXT:
- Indian seniors deeply respect authority figures (police, banks, government)
- They fear account freezing, arrest, service disconnection
- Many cannot read English technical terms
- "Digital arrest" is a uniquely Indian phenomenon (Supreme Court flagged it as epidemic, Dec 2024)

RESPONSE FORMAT (JSON only, no markdown):
{
  "verdict": "SAFE" or "CAUTION" or "HIGH_RISK",
  "confidence": 0-100,
  "scam_type": "DIGITAL_ARREST" | "FAKE_KYC" | "UPI_SCAM" | "UTILITY_THREAT" | "LOTTERY_SCAM" | "INVESTMENT_SCAM" | null,
  "explanation_hi": "सरल हिंदी में समझाइए (8th-grade reading level)",
  "explanation_en": "Simple English explanation",
  "red_flags": ["specific red flag 1", "specific red flag 2"],
  "advice": ["actionable step 1 in simple language", "actionable step 2"]
}

GUIDELINES:
- SAFE (confidence 0-30): No scam indicators, legitimate communication
- CAUTION (confidence 31-70): Some suspicious elements, verify before acting
- HIGH_RISK (confidence 71-100): Clear scam pattern, immediate danger

Be conservative: Better to warn unnecessarily than miss a scam targeting a vulnerable senior.
"""


def get_bedrock_client():
    """Get Bedrock Runtime client."""
    try:
        return boto3.client(
            "bedrock-runtime",
            region_name=BEDROCK_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception as e:
        print(f"Bedrock client error: {e}")
        return None


def analyze_scam(text, language="en", context="General message"):
    """
    Core scam detection using Amazon Bedrock Claude.
    Retries on throttle. Falls back to rule-based analysis if Bedrock fails.
    """
    if DEMO_MODE:
        return _demo_analysis(text, language)

    client = get_bedrock_client()
    if not client:
        return _rule_based_fallback(text, language)

    user_message = f"""Analyze this message for scam patterns:

MESSAGE:
\"\"\"{text}\"\"\"

CONTEXT: {context}
USER LANGUAGE PREFERENCE: {"Hindi" if language == "hi" else "English"}

Return ONLY the JSON object, no other text."""

    import time as _time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "temperature": 0.1,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": user_message}
                    ]
                })
            )

            response_body = json.loads(response["body"].read())
            result_text = response_body["content"][0]["text"]

            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return _rule_based_fallback(text, language)

            required_keys = ["verdict", "confidence", "scam_type", "explanation_hi", "red_flags", "advice"]
            for key in required_keys:
                if key not in result:
                    result[key] = None if key in ["scam_type"] else ([] if key in ["red_flags", "advice"] else "")

            if "explanation_en" not in result:
                result["explanation_en"] = result.get("explanation_hi", "")

            return result

        except Exception as e:
            err_str = str(e)
            # Retry on throttling / rate limit errors
            if ("ThrottlingException" in err_str or "Too many requests" in err_str or
                "try again" in err_str.lower()) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"Bedrock throttled, retrying in {wait}s (attempt {attempt+1}/{max_retries})")
                _time.sleep(wait)
                continue
            print(f"Bedrock analysis error: {e}")
            return _rule_based_fallback(text, language)


def analyze_url(url, language="en"):
    """Analyze a URL for phishing/scam patterns using Bedrock + pattern matching."""
    # Always use the robust pattern-based analysis (works offline too)
    # Then try Bedrock for richer analysis if available
    pattern_result = _demo_url_analysis(url, language)

    if DEMO_MODE:
        return pattern_result

    # Try Bedrock for deeper analysis
    client = get_bedrock_client()
    if not client:
        return pattern_result

    try:
        response = client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "temperature": 0.1,
                "system": "You analyze URLs for phishing and scam patterns. Focus on Indian scam URLs. Return JSON with: verdict (SAFE/CAUTION/HIGH_RISK), confidence (0-100), scam_type, explanation_hi, explanation_en, red_flags (list), advice (list).",
                "messages": [{"role": "user", "content": f"Analyze this URL for phishing/scam: {url}"}]
            })
        )
        body = json.loads(response["body"].read())
        result_text = body["content"][0]["text"]
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            result = json.loads(json_match.group()) if json_match else None
        if result and "verdict" in result:
            result["url_analyzed"] = url
            return result
    except Exception as e:
        print(f"Bedrock URL analysis error: {e}")

    return pattern_result


def _demo_url_analysis(url, language="en"):
    """Demo URL analysis with pattern matching."""
    import time
    import random
    time.sleep(1.0)
    
    url_lower = (url or "").lower()
    
    # Known phishing patterns
    phishing_indicators = [
        "bit.ly", "tinyurl", "short.url", "goo.gl",
        "login", "verify", "update", "secure", "account",
        "bank", "sbi", "hdfc", "icici", "rbi",
        "kyc", "aadhaar", "aadhar", "pan-update",
        "prize", "winner", "lottery", "reward",
        "free", "offer", "claim",
    ]
    
    suspicious_tlds = [".xyz", ".tk", ".ml", ".ga", ".cf", ".top", ".click", ".link", ".buzz"]
    
    # Check for IP-based URLs
    ip_pattern = re.match(r'https?://\d+\.\d+\.\d+\.\d+', url_lower)
    
    # Check for misleading domains
    misleading = any(bank in url_lower and ".com" not in url_lower.split(bank)[1][:5]
                     for bank in ["sbi", "hdfc", "icici", "rbi", "paytm"])
    
    # Brand impersonation detection (catches micro-soft, amaz0n, g00gle, etc.)
    known_brands = ["microsoft", "google", "apple", "amazon", "facebook", "instagram",
                    "whatsapp", "telegram", "paypal", "netflix", "flipkart", "phonepe",
                    "gpay", "paytm", "razorpay", "uber", "zomato", "swiggy"]
    import re as _re
    # Strip protocol and path for domain check
    domain_part = _re.sub(r'https?://', '', url_lower).split('/')[0].split('?')[0]
    # Remove hyphens and common number substitutions for comparison
    normalized = domain_part.replace('-', '').replace('0', 'o').replace('1', 'l').replace('3', 'e').replace('5', 's')
    
    score = 0
    red_flags = []
    
    for brand in known_brands:
        # Check if brand name appears in domain but with modifications (hyphens, typos)
        if brand in normalized and brand not in domain_part:
            score += 50
            red_flags.append(f"Domain impersonates '{brand}' (brand spoofing)")
            break
        # Also check if the exact brand is in domain but with wrong TLD
        if brand in domain_part and not domain_part.endswith(('.com', '.in', '.org', '.co.in')):
            score += 30
            red_flags.append(f"Suspicious domain uses '{brand}' name with unusual TLD")
            break

    if ip_pattern:
        score += 40
        red_flags.append("URL uses IP address instead of domain name")
    
    if any(tld in url_lower for tld in suspicious_tlds):
        score += 30
        red_flags.append("Suspicious top-level domain detected")
    
    for indicator in phishing_indicators:
        if indicator in url_lower:
            score += 15
            red_flags.append(f"Suspicious keyword: '{indicator}'")
            if len(red_flags) > 4:
                break
    
    if misleading:
        score += 35
        red_flags.append("Domain mimics a known Indian bank/service")
    
    if not url_lower.startswith("https://"):
        score += 10
        red_flags.append("Not using HTTPS (insecure connection)")
    
    score = min(score, 98)
    
    if score >= 60:
        return {
            "verdict": "HIGH_RISK",
            "confidence": random.randint(max(75, score - 10), min(98, score + 5)),
            "scam_type": "PHISHING_URL",
            "explanation_hi": "यह लिंक खतरनाक है। इसे खोलने पर आपकी जानकारी चोरी हो सकती है। इस पर क्लिक न करें।",
            "explanation_en": "This URL shows signs of a phishing attack. Do NOT click this link — it could steal your personal information.",
            "red_flags": red_flags[:4],
            "advice": [
                "Do NOT click this link",
                "Do NOT enter any personal information",
                "Report to Cyber Crime Helpline: 1930",
                "Block the sender"
            ],
            "url_analyzed": url,
        }
    elif score >= 30:
        return {
            "verdict": "CAUTION",
            "confidence": random.randint(40, 65),
            "scam_type": None,
            "explanation_hi": "इस लिंक में कुछ संदिग्ध संकेत हैं। खोलने से पहले सत्यापित करें।",
            "explanation_en": "This URL has some suspicious indicators. Verify the sender before clicking.",
            "red_flags": red_flags[:3],
            "advice": [
                "Verify the sender's identity first",
                "Check if the URL matches the official website",
                "When in doubt, don't click"
            ],
            "url_analyzed": url,
        }
    else:
        return {
            "verdict": "SAFE",
            "confidence": random.randint(10, 25),
            "scam_type": None,
            "explanation_hi": "यह लिंक सुरक्षित दिख रहा है, लेकिन हमेशा सावधान रहें।",
            "explanation_en": "This URL appears safe, but always exercise caution with unfamiliar links.",
            "red_flags": [],
            "advice": ["Always verify before entering personal information"],
            "url_analyzed": url,
        }


def _demo_analysis(text, language="en"):
    """Demo mode: Intelligent analysis without calling AWS — uses semantic pattern matching."""
    import time
    import random
    time.sleep(1.5)

    text_lower = (text or "").lower()

    # === PHASE 1: Keyword-based high-risk detection ===
    high_risk_patterns = {
        "DIGITAL_ARREST": {
            "keywords": ["cbi", "ed officer", "police", "arrest", "money laundering", "fir", "narcotics", "customs", "digital arrest", "warrant", "enforcement directorate"],
            "hi": "यह एक 'डिजिटल अरेस्ट' घोटाला है। कोई भी सरकारी एजेंसी फोन पर गिरफ्तारी की धमकी नहीं देती। तुरंत फोन काट दें।",
            "en": "This is a 'Digital Arrest' scam. No government agency threatens arrest over phone. Hang up immediately.",
            "flags": ["Authority impersonation detected", "Arrest/legal threat used as pressure tactic", "Demands immediate action or payment"],
            "breakdown": {"Authority Impersonation": 32, "Legal/Arrest Threats": 28, "Financial Demand": 18, "Urgency Language": 14},
        },
        "FAKE_KYC": {
            "keywords": ["kyc", "aadhaar", "aadhar", "pan card", "rbi", "account block", "bank update", "verify identity", "pan update", "link aadhaar"],
            "hi": "यह नकली KYC अपडेट है। RBI या कोई बैंक कभी लिंक भेजकर KYC अपडेट नहीं माँगता। इस लिंक पर क्लिक न करें।",
            "en": "This is a fake KYC update. RBI or banks never ask for KYC via links. Do not click this link.",
            "flags": ["Impersonates bank or RBI", "Requests sensitive identity documents", "Creates artificial urgency"],
            "breakdown": {"Bank/RBI Impersonation": 30, "Identity Document Request": 26, "Suspicious Link": 20, "Artificial Urgency": 16},
        },
        "UPI_SCAM": {
            "keywords": ["upi", "wrong payment", "reversal", "refund", "google pay", "phonepe", "paytm", "bhim"],
            "hi": "यह UPI धोखाधड़ी है। गलत पैसे भेजने का बहाना बनाकर आपसे पैसे लूटने की कोशिश है।",
            "en": "This is a UPI fraud. They're trying to trick you with a wrong payment excuse.",
            "flags": ["Claims wrong payment was sent", "Requests money transfer or reversal", "Uses urgency to prevent verification"],
            "breakdown": {"Payment Reversal Trick": 34, "Financial Pressure": 24, "Social Engineering": 20, "Urgency Language": 14},
        },
        "UTILITY_THREAT": {
            "keywords": ["electricity", "bill payment", "disconnection", "gas connection", "bsnl", "last notice", "power cut", "meter"],
            "hi": "यह नकली बिल चेतावनी है। बिजली/गैस कंपनी कभी इस तरह फोन पर पैसे नहीं माँगती।",
            "en": "This is a fake utility bill threat. Utility companies never demand payment this way.",
            "flags": ["Threatens service disconnection", "Demands immediate payment", "Uses unofficial payment channel"],
            "breakdown": {"Service Disconnection Threat": 30, "Financial Demand": 26, "Fear Tactics": 22, "Unofficial Channel": 14},
        },
        "LOTTERY_SCAM": {
            "keywords": ["lottery", "winner", "prize", "congratulations", "kbc", "lucky draw", "claim", "jackpot", "won"],
            "hi": "यह लॉटरी घोटाला है। आपने कोई लॉटरी नहीं जीती। कोई पैसे न भेजें।",
            "en": "This is a lottery scam. You haven't won any prize. Don't send money.",
            "flags": ["Claims unexpected prize/lottery win", "Requests processing fee", "Creates excitement to bypass judgment"],
            "breakdown": {"Unsolicited Prize Claim": 32, "Processing Fee Request": 28, "Emotional Manipulation": 18, "Too Good To Be True": 14},
        },
        "INVESTMENT_SCAM": {
            "keywords": ["guaranteed", "profit", "returns", "invest", "crypto", "trading", "100%", "daily income", "passive income", "stock tip"],
            "hi": "यह निवेश घोटाला है। कोई भी 'गारंटीड रिटर्न' वाला निवेश धोखा है।",
            "en": "This is an investment scam. Any 'guaranteed returns' scheme is fraudulent.",
            "flags": ["Promises unrealistic returns", "Creates FOMO (fear of missing out)", "No registered investment entity"],
            "breakdown": {"Unrealistic Returns Promise": 34, "FOMO Manipulation": 22, "Unregistered Entity": 20, "Financial Lure": 16},
        },
    }

    for scam_type, pattern in high_risk_patterns.items():
        if any(kw in text_lower for kw in pattern["keywords"]):
            confidence = random.randint(82, 96)
            return {
                "verdict": "HIGH_RISK",
                "confidence": confidence,
                "scam_type": scam_type,
                "explanation_hi": pattern["hi"],
                "explanation_en": pattern["en"],
                "red_flags": pattern["flags"],
                "confidence_breakdown": pattern["breakdown"],
                "advice": [
                    "Do NOT click any links or share OTP",
                    "Call Cyber Crime Helpline: 1930",
                    "Inform your family immediately",
                ],
            }

    # === PHASE 2: Semantic intent detection (catches what keywords miss) ===
    semantic_patterns = [
        {
            "patterns": [
                r"send.*(?:money|payment|amount|transfer)",
                r"share.*(?:otp|pin|password|cvv|account)",
                r"(?:bank|account).*(?:detail|number|info)",
                r"click.*(?:link|here|below|button)",
                r"(?:give|tell|provide|enter).*(?:otp|pin|password)",
            ],
            "verdict": "HIGH_RISK",
            "confidence_range": (72, 88),
            "scam_type": None,
            "hi": "इस संदेश में आपकी व्यक्तिगत जानकारी या पैसे माँगने का प्रयास है। यह धोखाधड़ी हो सकती है।",
            "en": "This message attempts to extract personal information or money from you. This could be fraud.",
            "flags": ["Requests sensitive personal information", "Attempts to extract financial data", "Uses social engineering tactics"],
        },
        {
            "patterns": [
                r"(?:act|respond|reply).*(?:immediately|urgently|now|fast|quick)",
                r"(?:last|final).*(?:chance|warning|notice|opportunity)",
                r"(?:expire|expiring|expired).*(?:today|hour|minute|soon)",
                r"(?:within|before).*(?:\d+\s*hour|\d+\s*minute|midnight|today)",
                r"(?:hurry|rush|asap|don.t delay|time.s running)",
            ],
            "verdict": "CAUTION",
            "confidence_range": (50, 72),
            "scam_type": None,
            "hi": "इस संदेश में जल्दबाज़ी का दबाव बनाया जा रहा है। सावधान रहें और सत्यापित करें।",
            "en": "This message creates artificial urgency to pressure you into acting quickly. Verify before proceeding.",
            "flags": ["Urgency language detected", "Pressure tactics to bypass critical thinking"],
        },
        {
            "patterns": [
                r"(?:free|win|won|selected|chosen|lucky)",
                r"(?:offer|deal|discount).*(?:limited|exclusive|special)",
                r"(?:cash\s*back|reward|bonus|gift)",
            ],
            "verdict": "CAUTION",
            "confidence_range": (40, 62),
            "scam_type": None,
            "hi": "इस संदेश में लुभावने ऑफ़र का इस्तेमाल हो रहा है। सत्यापित करें।",
            "en": "This message uses enticing offers that may be too good to be true. Verify the source.",
            "flags": ["Suspicious promotional content", "Unverified source"],
        },
    ]

    for sp in semantic_patterns:
        for pattern in sp["patterns"]:
            if re.search(pattern, text_lower):
                return {
                    "verdict": sp["verdict"],
                    "confidence": random.randint(*sp["confidence_range"]),
                    "scam_type": sp["scam_type"],
                    "explanation_hi": sp["hi"],
                    "explanation_en": sp["en"],
                    "red_flags": sp["flags"],
                    "advice": [
                        "Do NOT share personal information",
                        "Verify the sender's identity",
                        "When in doubt, call Cyber Crime Helpline: 1930"
                    ],
                }

    # === PHASE 3: Medium risk — generic suspicious markers ===
    medium_keywords = ["click here", "verify now", "update required", "urgent", "immediately", "limited time", "act now", "don't ignore"]
    if any(kw in text_lower for kw in medium_keywords):
        return {
            "verdict": "CAUTION",
            "confidence": random.randint(45, 68),
            "scam_type": None,
            "explanation_hi": "इस संदेश में कुछ संदिग्ध संकेत हैं। आगे बढ़ने से पहले सत्यापित करें।",
            "explanation_en": "This message has some suspicious indicators. Verify before proceeding.",
            "red_flags": ["Urgency language detected", "Unverified source"],
            "advice": ["Verify the sender's identity", "Do not share personal information"],
        }

    # === PHASE 4: Safe — no threats detected ===
    return {
        "verdict": "SAFE",
        "confidence": random.randint(10, 25),
        "scam_type": None,
        "explanation_hi": "कोई स्पष्ट खतरा नहीं दिख रहा, लेकिन हमेशा सावधान रहें।",
        "explanation_en": "No clear threat detected, but always stay cautious with messages from unknown sources.",
        "red_flags": [],
        "advice": ["Always verify before sharing personal info"],
    }


def _rule_based_fallback(text, language="en"):
    """Enhanced rule-based analysis with Hindi/Hinglish/English keyword detection."""
    text_lower = (text or "").lower()

    # HIGH RISK — English keywords
    high_risk_en = [
        "cbi", "ed officer", "police", "arrest", "money laundering",
        "rbi", "account block", "kyc update", "aadhaar update",
        "electricity cut", "gas disconnect", "otp", "urgent payment",
        "fir", "narcotics", "customs", "digital arrest",
        "send money", "send me money", "card block", "card has been blocked",
        "account frozen", "account freeze", "verify your", "your account",
        "click the link", "update immediately", "pay now", "scam",
        "bank account", "suspended", "illegal activity", "drugs parcel",
    ]

    # HIGH RISK — Hindi / Hinglish keywords
    high_risk_hi = [
        "गिरफ्तार", "arrest", "पुलिस", "सीबीआई", "ईडी",
        "पैसे भेजो", "पैसा भेजो", "paisa bhejo", "paise bhejo",
        "कार्ड ब्लॉक", "card block", "अकाउंट ब्लॉक",
        "kyc", "केवाईसी", "आधार", "aadhaar", "aadhar",
        "तुरंत", "turant", "जल्दी", "jaldi",
        "खाता बंद", "khata band", "account band",
        "बैंक", "bank", "otp",
        "हादसा", "hadsa", "accident",
        "अस्पताल", "hospital", "aspatal",
        "बेटा", "beta", "बेटी", "beti",
        "शिकार", "shikar",
        "रुपये", "rupaye", "पेमेंट", "payment",
        "लिंक पर क्लिक", "link click",
        "फ्रीज", "freeze", "ब्लॉक", "block",
        "सस्पेंड", "suspend",
        "बिजली काट", "bijli kat", "bijlee",
        "गैस कनेक्शन", "gas connection",
        "लॉटरी", "lottery", "इनाम", "inaam",
        "जीत", "jeet", "prize",
    ]

    # MEDIUM — promotional/suspicious
    medium_keywords = [
        "congratulations", "lottery", "prize", "winner",
        "click here", "verify now", "update required",
        "offer", "free", "guaranteed", "returns",
        "invest", "trading", "crypto",
        "whatsapp group", "join now",
        "बधाई", "मुबारक", "मुफ्त", "फ्री",
    ]

    # Detect scam type based on keyword matches
    matched_flags = []
    scam_type = None

    # Check high-risk keywords
    high_match = False
    for kw in high_risk_en + high_risk_hi:
        if kw in text_lower:
            high_match = True
            matched_flags.append(f"Suspicious keyword: '{kw}'")
            # Detect specific scam types
            if kw in ["cbi", "सीबीआई", "ईडी", "police", "पुलिस", "arrest", "गिरफ्तार", "fir", "narcotics", "digital arrest"]:
                scam_type = "DIGITAL_ARREST"
            elif kw in ["kyc", "केवाईसी", "आधार", "aadhaar", "aadhar", "rbi", "account block", "अकाउंट ब्लॉक", "card block", "कार्ड ब्लॉक"]:
                scam_type = scam_type or "FAKE_KYC"
            elif kw in ["हादसा", "hadsa", "accident", "अस्पताल", "hospital", "बेटा", "beta"]:
                scam_type = scam_type or "EMERGENCY_SCAM"
            elif kw in ["बिजली काट", "bijli kat", "electricity cut", "गैस कनेक्शन"]:
                scam_type = scam_type or "UTILITY_THREAT"
            elif kw in ["लॉटरी", "lottery", "इनाम", "inaam", "जीत", "jeet", "prize"]:
                scam_type = scam_type or "LOTTERY_SCAM"
            if len(matched_flags) >= 4:
                break

    if high_match:
        return {
            "verdict": "HIGH_RISK",
            "confidence": min(85, 65 + len(matched_flags) * 5),
            "scam_type": scam_type or "UNKNOWN",
            "explanation_hi": "इस संदेश में खतरनाक शब्द हैं। यह एक धोखाधड़ी हो सकती है। अपने परिवार से बात करें।",
            "explanation_en": "This message contains multiple scam indicators. This is likely a fraud attempt. Talk to your family before responding.",
            "red_flags": matched_flags[:4],
            "advice": ["Do NOT click any links", "Do NOT send money or OTP", "Call family member immediately", "Call Cyber Crime Helpline 1930"],
        }

    # Check medium keywords
    med_match = False
    for kw in medium_keywords:
        if kw in text_lower:
            med_match = True
            matched_flags.append(f"Suspicious term: '{kw}'")

    if med_match:
        return {
            "verdict": "CAUTION",
            "confidence": 60,
            "scam_type": None,
            "explanation_hi": "यह संदेश संदेहास्पद हो सकता है। सावधानी से काम लें।",
            "explanation_en": "This message has suspicious promotional content. Proceed with caution.",
            "red_flags": matched_flags[:3],
            "advice": ["Verify sender identity", "Do not share personal information", "If unsure, ask a family member"],
        }

    # Check for suspicious URLs in text
    url_pattern = re.search(r'https?://[^\s]+|www\.[^\s]+|bit\.ly|tinyurl', text_lower)
    if url_pattern:
        return {
            "verdict": "CAUTION",
            "confidence": 55,
            "scam_type": None,
            "explanation_hi": "इस संदेश में एक लिंक है। अनजान लिंक पर क्लिक न करें।",
            "explanation_en": "This message contains a link. Do not click links from unknown senders.",
            "red_flags": ["Contains URL — verify before clicking"],
            "advice": ["Do NOT click the link", "Verify the sender first"],
        }

    return {
        "verdict": "SAFE",
        "confidence": 15,
        "scam_type": None,
        "explanation_hi": "कोई स्पष्ट खतरा नहीं दिख रहा।",
        "explanation_en": "No clear scam indicators detected.",
        "red_flags": [],
        "advice": ["Always verify unknown senders before sharing personal info"],
    }
