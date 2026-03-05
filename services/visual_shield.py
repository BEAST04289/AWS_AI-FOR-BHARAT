"""
SHIELD - Visual Shield (AWS Bedrock Vision + Textract Fallback)
Analyzes screenshots for scam patterns using Bedrock Claude's multimodal vision.
Falls back to Textract OCR if available, otherwise uses Bedrock vision directly.
"""
import os
import json
import base64
import boto3
from dotenv import load_dotenv
from services.bedrock_analyzer import analyze_scam

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"


def get_textract_client():
    """Get Textract client."""
    try:
        return boto3.client(
            "textract",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception as e:
        print(f"Textract client error: {e}")
        return None


def get_bedrock_client():
    """Get Bedrock Runtime client for vision."""
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


def extract_text_textract(image_bytes):
    """Try to extract text using Textract (may not be subscribed)."""
    client = get_textract_client()
    if not client:
        return None
    try:
        response = client.detect_document_text(Document={"Bytes": image_bytes})
        lines = [b["Text"] for b in response.get("Blocks", []) if b["BlockType"] == "LINE"]
        return "\n".join(lines) if lines else None
    except Exception as e:
        print(f"Textract OCR error: {e}")
        return None


def analyze_image_bedrock_vision(image_bytes, language="en"):
    """
    Use Bedrock Claude Vision to directly analyze an image for scam content.
    Claude 3.5 Haiku supports multimodal (image + text) input.
    """
    client = get_bedrock_client()
    if not client:
        return None

    # Detect image type
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        media_type = "image/jpeg"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        media_type = "image/webp"
    else:
        media_type = "image/png"  # default assumption

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    lang_instruction = "Respond in Hindi" if language == "hi" else "Respond in English"

    try:
        response = client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"""You are SHIELD, an AI scam detector protecting Indian seniors.
Analyze this screenshot/image for scam or fraud patterns.

Look for:
- Fake KYC/Aadhaar/PAN update messages
- Digital arrest threats from fake police/CBI/ED
- UPI fraud or fake payment requests
- Lottery/prize scams
- Phishing URLs or fake login pages
- Emergency/accident scams asking for money
- Suspicious WhatsApp/SMS forwards

{lang_instruction}

Return ONLY a JSON object:
{{
    "verdict": "HIGH_RISK" or "CAUTION" or "SAFE",
    "confidence": 0-100,
    "scam_type": "FAKE_KYC" or "DIGITAL_ARREST" or "UPI_FRAUD" or "LOTTERY_SCAM" or "PHISHING_URL" or "EMERGENCY_SCAM" or null,
    "explanation_hi": "Hindi explanation",
    "explanation_en": "English explanation",
    "red_flags": ["flag1", "flag2"],
    "advice": ["advice1", "advice2"],
    "extracted_text": "any text visible in the image"
}}"""
                            }
                        ]
                    }
                ]
            })
        )

        response_body = json.loads(response["body"].read())
        result_text = response_body["content"][0]["text"]

        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                return None

        # Ensure all required keys exist
        for key in ["verdict", "confidence", "scam_type", "explanation_hi", "explanation_en", "red_flags", "advice"]:
            if key not in result:
                result[key] = None if key == "scam_type" else ([] if key in ["red_flags", "advice"] else "")

        result["ocr_text"] = result.get("extracted_text", "")
        return result

    except Exception as e:
        print(f"Bedrock Vision error: {e}")
        return None


def analyze_image(image_bytes, language="en"):
    """
    Full Visual Shield pipeline with graceful fallback:
    1. Try Bedrock Vision (multimodal) - works directly on images
    2. Try Textract OCR + Bedrock Text analysis as fallback
    3. Return helpful error if both fail
    """
    if DEMO_MODE:
        ocr_text = _demo_ocr()
        result = analyze_scam(ocr_text, language=language, context="WhatsApp/SMS Screenshot")
        result["ocr_text"] = ocr_text
        return result

    # Strategy 1: Bedrock Vision (directly analyze the image)
    vision_result = analyze_image_bedrock_vision(image_bytes, language)
    if vision_result:
        return vision_result

    # Strategy 2: Textract OCR then Bedrock text analysis
    ocr_text = extract_text_textract(image_bytes)
    if ocr_text:
        result = analyze_scam(ocr_text, language=language, context="WhatsApp/SMS Screenshot")
        result["ocr_text"] = ocr_text
        return result

    # Both failed
    return {
        "verdict": "CAUTION",
        "confidence": 30,
        "scam_type": None,
        "explanation_hi": "छवि का विश्लेषण नहीं हो सका। कृपया स्पष्ट छवि अपलोड करें।",
        "explanation_en": "Could not analyze image. Please upload a clearer image with visible text.",
        "red_flags": [],
        "advice": ["Try uploading a clearer screenshot with visible text"],
        "ocr_text": "",
    }


def _demo_ocr():
    """Return demo OCR text for testing without AWS."""
    return "आपका Aadhaar card RBI द्वारा block कर दिया जाएगा। तुरंत update करें: http://fake-kyc-update.com। अगर 24 घंटे में update नहीं किया तो आपका bank account freeze हो जाएगा। Call: 9876543210"
