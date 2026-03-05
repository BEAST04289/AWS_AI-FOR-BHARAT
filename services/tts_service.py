"""
SHIELD - Text-to-Speech Service (AWS Polly)
Generates Hindi voice responses using Amazon Polly with Kajal Neural voice.
Falls back to browser speechSynthesis signal in demo mode.
"""
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# Voice configuration — Aditi (standard) is available in all regions
VOICES = {
    "hi": {"VoiceId": "Aditi", "LanguageCode": "hi-IN", "Engine": "standard"},
    "en": {"VoiceId": "Aditi", "LanguageCode": "hi-IN", "Engine": "standard"},
}


def get_polly_client():
    """Get Polly client."""
    try:
        return boto3.client(
            "polly",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception as e:
        print(f"Polly client error: {e}")
        return None


def generate_speech(text, language="hi"):
    """
    Generate speech from text using Amazon Polly.
    In demo mode, returns None — client uses browser speechSynthesis as fallback.
    """
    if DEMO_MODE:
        return None  # Client-side will use browser speechSynthesis

    client = get_polly_client()
    if not client:
        return None

    voice_config = VOICES.get(language, VOICES["hi"])

    try:
        ssml_text = f"""<speak>
    <prosody rate="slow">{text}</prosody>
    <break time="500ms"/>
    अगर आपको कोई संदेह है, तो अपने परिवार से बात कीजिए।
</speak>"""

        response = client.synthesize_speech(
            Text=ssml_text,
            TextType="ssml",
            OutputFormat="mp3",
            VoiceId=voice_config["VoiceId"],
            Engine=voice_config["Engine"],
            LanguageCode=voice_config["LanguageCode"],
        )

        if "AudioStream" in response:
            return response["AudioStream"].read()
        return None

    except Exception as e:
        print(f"Polly TTS error: {e}")
        try:
            response = client.synthesize_speech(
                Text=text,
                TextType="text",
                OutputFormat="mp3",
                VoiceId=voice_config["VoiceId"],
                Engine=voice_config["Engine"],
                LanguageCode=voice_config["LanguageCode"],
            )
            if "AudioStream" in response:
                return response["AudioStream"].read()
        except Exception as e2:
            print(f"Polly TTS fallback error: {e2}")
        return None


def get_verdict_speech_text(verdict, explanation_hi, explanation_en, language="hi"):
    """Generate culturally appropriate speech text based on verdict."""
    if language == "hi":
        templates = {
            "HIGH_RISK": f"सावधान! यह एक घोटाला है। {explanation_hi}। कृपया किसी लिंक पर क्लिक न करें और अपने परिवार को बताएं।",
            "CAUTION": f"ध्यान दीजिए। {explanation_hi}। आगे बढ़ने से पहले सत्यापित करें।",
            "SAFE": f"अच्छी खबर! {explanation_hi}।",
        }
    else:
        templates = {
            "HIGH_RISK": f"Warning! This is a scam. {explanation_en}. Do not click any links and inform your family.",
            "CAUTION": f"Be careful. {explanation_en}. Verify before proceeding.",
            "SAFE": f"Good news! {explanation_en}.",
        }

    return templates.get(verdict, templates["CAUTION"])
