#!/usr/bin/env python3
"""
Manual Voice Endpoint Testing Script
Directly tests the /api/audio/transcribe and /api/audio/synthesize endpoints
"""

import base64
import json
import requests
import sys
from pathlib import Path


BASE_URL = "http://localhost:8000"


def test_synthesize_endpoint(text: str, language: str = "en") -> dict:
    """Test TTS endpoint and return the response."""
    print(f"\n{'='*60}")
    print(f"Testing: POST /api/audio/synthesize")
    print(f"Language: {language}")
    print(f"Text: {text[:50]}...")
    print(f"{'='*60}")

    payload = {
        "text": text,
        "language": language,
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/audio/synthesize",
            json=payload,
            timeout=30,
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success: {result['success']}")
            print(f"Language: {result['language']}")
            if result.get("data"):
                audio_bytes = base64.b64decode(result["data"])
                print(f"Audio size: {len(audio_bytes)} bytes")
                # Save audio file for manual playback
                audio_file = f"test_output_{language}.mp3"
                with open(audio_file, "wb") as f:
                    f.write(audio_bytes)
                print(f"✅ Saved audio to: {audio_file}")
            else:
                print(f"❌ Error: {result.get('error')}")
            return result
        else:
            print(f"❌ Error: {response.text}")
            return {}
    except Exception as e:
        print(f"❌ Exception: {e}")
        return {}


def test_transcribe_endpoint(audio_file_path: str, language: str = "en") -> dict:
    """Test STT endpoint with an audio file."""
    print(f"\n{'='*60}")
    print(f"Testing: POST /api/audio/transcribe")
    print(f"Audio file: {audio_file_path}")
    print(f"Language: {language}")
    print(f"{'='*60}")

    if not Path(audio_file_path).exists():
        print(f"❌ Error: File not found: {audio_file_path}")
        return {}

    try:
        # Read and encode audio
        with open(audio_file_path, "rb") as f:
            audio_bytes = f.read()

        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Determine format from filename
        file_ext = Path(audio_file_path).suffix.lower().strip(".")
        if file_ext not in ["wav", "mp3", "ogg"]:
            file_ext = "wav"

        payload = {
            "audio_base64": audio_base64,
            "language": language,
            "format": file_ext,
        }

        response = requests.post(
            f"{BASE_URL}/api/audio/transcribe",
            json=payload,
            timeout=60,  # Transcription can take longer
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success: {result['success']}")
            print(f"Language: {result['language']}")
            if result["success"]:
                print(f"Transcribed text: {result.get('data', '')}")
            else:
                print(f"❌ Error: {result.get('error')}")
            return result
        else:
            print(f"❌ Error: {response.text}")
            return {}
    except Exception as e:
        print(f"❌ Exception: {e}")
        return {}


def test_voice_language_support() -> None:
    """Test TTS in all supported languages."""
    print("\n" + "="*80)
    print("TESTING VOICE LANGUAGE SUPPORT")
    print("="*80)

    test_texts = {
        "en": "Housing scheme for low income families",
        "hi": "गरीब परिवारों के लिए आवास योजना",
        "te": "తక్క ఆదాయ కంటే ఎక్కువ కుటుంబాల కోసం గృహ నిర్మాణ పథకం",
        "ta": "குறைந்த வருமான குடும்பங்களுக்கான வீட்டுத் திட்டம்",
    }

    results = {}
    for lang, text in test_texts.items():
        result = test_synthesize_endpoint(text, lang)
        results[lang] = {
            "success": result.get("success", False),
            "has_audio": result.get("data") is not None,
        }

    print("\n" + "="*80)
    print("LANGUAGE SUPPORT SUMMARY")
    print("="*80)
    for lang, status in results.items():
        emoji = "✅" if status["success"] and status["has_audio"] else "❌"
        print(f"{emoji} {lang.upper()}: success={status['success']}, audio={status['has_audio']}")


def test_voice_error_scenarios() -> None:
    """Test error handling in voice endpoints."""
    print("\n" + "="*80)
    print("TESTING ERROR SCENARIOS")
    print("="*80)

    # Test 1: Empty text
    print("\n--- Test 1: Empty text (should fail gracefully) ---")
    result = test_synthesize_endpoint("", "en")
    assert result.get("success") is False, "Should fail on empty text"
    print("✅ Correctly rejected empty text")

    # Test 2: Invalid language (should normalize to English)
    print("\n--- Test 2: Invalid language (should normalize to English) ---")
    result = test_synthesize_endpoint("Test", "fr")
    assert result.get("language") == "en", "Should normalize to English"
    print("✅ Correctly normalized to English")

    # Test 3: Very long text (should succeed)
    print("\n--- Test 3: Long text (should handle) ---")
    long_text = "This is a long text. " * 50  # Repeat to make it long
    result = test_synthesize_endpoint(long_text, "en")
    if result.get("success"):
        print("✅ Successfully handled long text")
    else:
        print(f"ℹ️  Long text test result: {result.get('error')}")


def test_voice_chat_integration() -> None:
    """Test voice integration with chat endpoint."""
    print("\n" + "="*80)
    print("TESTING VOICE + CHAT INTEGRATION")
    print("="*80)

    # Step 1: Synthesize a chat-like response
    print("\n--- Step 1: Generate audio response ---")
    response_text = "You are eligible for the PM-KISAN scheme which provides direct income support to farmers."
    result = test_synthesize_endpoint(response_text, "en")

    if not result.get("success"):
        print("❌ Failed to generate audio for chat response")
        return

    audio_file = "chat_response.mp3"
    with open(audio_file, "wb") as f:
        f.write(base64.b64decode(result["data"]))

    print(f"✅ Generated audio response: {audio_file}")

    # Step 2: Verify audio can be decoded
    print("\n--- Step 2: Verify audio playback ---")
    try:
        with open(audio_file, "rb") as f:
            audio_data = f.read()
        print(f"✅ Audio file ready for playback ({len(audio_data)} bytes)")
    except Exception as e:
        print(f"❌ Failed to verify audio: {e}")


def create_sample_wav(filename: str = "sample.wav") -> None:
    """Create a minimal WAV file for testing."""
    print(f"\n--- Creating sample WAV file ---")
    # Minimal WAV header (44 bytes) + silence
    wav_data = (
        b"RIFF"  # Chunk ID
        + b"\x24\x00\x00\x00"  # Chunk size (36 bytes)
        + b"WAVE"  # Format
        + b"fmt "  # Subchunk1 ID
        + b"\x10\x00\x00\x00"  # Subchunk1 size (16)
        + b"\x01\x00"  # Audio format (PCM)
        + b"\x01\x00"  # Num channels (mono)
        + b"\x40\x1f\x00\x00"  # Sample rate (8000 Hz)
        + b"\x80\x3e\x00\x00"  # Byte rate
        + b"\x02\x00"  # Block align
        + b"\x10\x00"  # Bits per sample (16)
        + b"data"  # Subchunk2 ID
        + b"\x00\x00\x00\x00"  # Subchunk2 size
    )

    with open(filename, "wb") as f:
        f.write(wav_data)

    print(f"✅ Created: {filename}")


def main() -> None:
    """Run all tests."""
    print("\n" + "="*80)
    print("VOICE ASSISTANT END-TO-END TESTING")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")

    # Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running and healthy")
        else:
            print("⚠️  Backend is running but returned unexpected status")
    except requests.ConnectionError:
        print("❌ Cannot connect to backend at {BASE_URL}")
        print("   Make sure backend is running: python -m uvicorn backend.main:app --reload")
        sys.exit(1)

    # Run test suites
    try:
        # Create sample audio for testing
        create_sample_wav()

        # Test language support
        test_voice_language_support()

        # Test error scenarios
        test_voice_error_scenarios()

        # Test chat integration
        test_voice_chat_integration()

        print("\n" + "="*80)
        print("✅ TESTING COMPLETE")
        print("="*80)
        print("\nGenerated test files:")
        print("  - test_output_en.mp3 (English TTS)")
        print("  - test_output_hi.mp3 (Hindi TTS)")
        print("  - test_output_te.mp3 (Telugu TTS)")
        print("  - test_output_ta.mp3 (Tamil TTS)")
        print("  - chat_response.mp3 (Chat response audio)")
        print("\nYou can play these files to verify audio quality.")

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
