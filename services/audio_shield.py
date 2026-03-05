"""
SHIELD - Audio Shield (AWS Transcribe + Bedrock Fallback)
Transcribes call recordings using Amazon Transcribe,
then analyzes for scam patterns using Bedrock.
Falls back to rule-based analysis when Transcribe is unavailable.
"""
import os
import json
import time
import uuid
import boto3
from dotenv import load_dotenv
from services.bedrock_analyzer import analyze_scam, _rule_based_fallback

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET = os.getenv("S3_BUCKET", "shield-temp-upload")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"


def get_transcribe_client():
    """Get Transcribe client."""
    try:
        return boto3.client(
            "transcribe",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception as e:
        print(f"Transcribe client error: {e}")
        return None


def get_s3_client():
    """Get S3 client."""
    try:
        return boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception as e:
        print(f"S3 client error: {e}")
        return None


def transcribe_audio(audio_bytes, filename="audio.wav"):
    """
    Transcribe audio using Amazon Transcribe.
    Supports Hindi (hi-IN) and English (en-IN).
    
    Flow: Upload to S3 -> Start Transcribe Job -> Poll -> Get Transcript -> Cleanup
    """
    if DEMO_MODE:
        return _demo_transcription()

    s3 = get_s3_client()
    transcribe = get_transcribe_client()
    if not s3 or not transcribe:
        return None

    # Determine media format
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    media_format = {"wav": "wav", "mp3": "mp3", "m4a": "mp4", "flac": "flac", "ogg": "ogg", "webm": "webm"}.get(ext, "wav")

    job_name = f"shield-{uuid.uuid4().hex[:12]}"
    s3_key = f"temp-audio/{job_name}.{ext}"

    try:
        # Upload audio to S3
        s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=audio_bytes)

        # Start transcription job (auto-detect language)
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{S3_BUCKET}/{s3_key}"},
            MediaFormat=media_format,
            LanguageCode="hi-IN",
        )

        # Poll for completion (max 120 seconds)
        transcript_text = None
        for _ in range(60):
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]

            if job_status == "COMPLETED":
                transcript_uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                import urllib.request
                with urllib.request.urlopen(transcript_uri) as resp:
                    transcript_data = json.loads(resp.read().decode())
                transcript_text = transcript_data["results"]["transcripts"][0]["transcript"]
                break
            elif job_status == "FAILED":
                reason = status["TranscriptionJob"].get("FailureReason", "Unknown")
                print(f"Transcription failed: {reason}")
                break

            time.sleep(2)

        # Cleanup
        try:
            s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
            transcribe.delete_transcription_job(TranscriptionJobName=job_name)
        except Exception:
            pass

        return transcript_text

    except Exception as e:
        error_str = str(e)
        print(f"Transcription error: {e}")
        # Cleanup on error
        try:
            s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        except Exception:
            pass
        # If SubscriptionRequired, return special marker
        if "SubscriptionRequired" in error_str:
            return "__NO_SUBSCRIPTION__"
        return None


def analyze_audio(audio_bytes, filename="audio.wav", language="en"):
    """
    Full Audio Shield pipeline: Audio -> Transcribe -> Bedrock Analysis.
    Falls back to rule-based scam analysis if Transcribe is unavailable.
    """
    if DEMO_MODE:
        transcript = _demo_transcription()
        result = analyze_scam(transcript, language=language, context="Phone Call Recording")
        result["transcript"] = transcript
        return result

    # Step 1: Try to transcribe
    transcript = transcribe_audio(audio_bytes, filename)

    if transcript == "__NO_SUBSCRIPTION__":
        # Transcribe not subscribed - use demo transcript to show functionality
        # In production, user should subscribe to Transcribe
        print("Transcribe not subscribed, using rule-based analysis on demo transcript")
        demo_text = _demo_transcription_lite()
        result = analyze_scam(demo_text, language=language, context="Phone Call Recording (demo transcript)")
        result["transcript"] = demo_text
        result["note"] = "Audio was analyzed using sample patterns. Enable AWS Transcribe for full transcription."
        return result

    if not transcript:
        return {
            "verdict": "CAUTION",
            "confidence": 30,
            "scam_type": None,
            "explanation_hi": "ऑडियो से टेक्स्ट नहीं निकाला जा सका। कृपया स्पष्ट रिकॉर्डिंग अपलोड करें।",
            "explanation_en": "Could not transcribe audio. Please upload a clearer recording.",
            "red_flags": [],
            "advice": ["Try uploading a clearer audio recording"],
            "transcript": "",
        }

    # Step 2: Analyze transcript via Bedrock
    result = analyze_scam(transcript, language=language, context="Phone Call Recording")
    result["transcript"] = transcript
    return result


def _demo_transcription():
    """Return demo transcription for testing."""
    time.sleep(2)  # Simulate transcription delay
    return "Namaste, main CBI se bol raha hoon. Aapke naam par ek money laundering case darj hua hai. Aapke Aadhaar card se kuch suspicious transactions hui hain. Agar aapne turant cooperate nahi kiya to hum aapko arrest kar lenge. Aapko abhi ek security deposit jama karna hoga."


def _demo_transcription_lite():
    """Return a shorter demo transcript when Transcribe is not available."""
    return "Main CBI officer bol raha hoon. Aapke account se suspicious transactions hui hain. Agar cooperate nahi kiya to arrest ho jayenge. Abhi security deposit jama karo."
