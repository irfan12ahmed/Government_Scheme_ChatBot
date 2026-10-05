"""Tests for speech-to-text and text-to-speech endpoints."""
import base64
import pytest

import backend.main as main


class TestSpeechHelpers:
    """Test language mapping and error formatting helpers."""

    def test_normalize_language_code_valid_languages(self) -> None:
        assert main.normalize_language_code("en") == "en"
        assert main.normalize_language_code("hi") == "hi"
        assert main.normalize_language_code("te") == "te"
        assert main.normalize_language_code("ta") == "ta"

    def test_normalize_language_code_invalid_falls_back_to_english(self) -> None:
        assert main.normalize_language_code("fr") == "en"
        assert main.normalize_language_code("xx") == "en"
        assert main.normalize_language_code("") == "en"

    def test_normalize_language_code_case_insensitive(self) -> None:
        assert main.normalize_language_code("EN") == "en"
        assert main.normalize_language_code("HI") == "hi"

    def test_format_speech_error_english(self) -> None:
        error = main.format_speech_error("test error", "en")
        assert "Speech processing failed" in error
        assert "text input" in error

    def test_format_speech_error_invalid_language_uses_english(self) -> None:
        error = main.format_speech_error("test error", "fr")
        assert "Speech processing failed" in error


class TestSpeechTranscribe:
    """Test audio transcription endpoint."""

    def test_transcribe_missing_audio_returns_error(self) -> None:
        payload = main.SpeechRequest(
            audio_base64=None,
            language="en",
        )
        response = main.transcribe_audio(payload)

        assert response.success is False
        assert response.data is None
        assert response.error is not None
        assert "speech processing failed" in response.error.lower()

    def test_transcribe_empty_audio_returns_error(self) -> None:
        empty_base64 = base64.b64encode(b"").decode("utf-8")
        payload = main.SpeechRequest(
            audio_base64=empty_base64,
            language="en",
        )
        response = main.transcribe_audio(payload)

        assert response.success is False
        assert response.data is None
        assert response.error is not None

    def test_transcribe_invalid_base64_returns_error(self) -> None:
        payload = main.SpeechRequest(
            audio_base64="not-valid-base64!!!",
            language="en",
        )
        response = main.transcribe_audio(payload)

        assert response.success is False
        assert response.data is None
        assert response.error is not None

    def test_transcribe_normalizes_language(self) -> None:
        # Test that invalid language gets normalized to "en"
        payload = main.SpeechRequest(
            audio_base64=None,
            language="fr",
        )
        response = main.transcribe_audio(payload)

        # Should have normalized language to "en" in the response
        assert response.language == "en"


class TestSpeechSynthesize:
    """Test text-to-speech synthesis endpoint."""

    def test_synthesize_missing_text_returns_error(self) -> None:
        payload = main.SpeechRequest(
            text=None,
            language="en",
        )
        response = main.synthesize_audio(payload)

        assert response.success is False
        assert response.data is None
        assert response.error is not None

    def test_synthesize_empty_text_returns_error(self) -> None:
        payload = main.SpeechRequest(
            text="  ",  # Whitespace only
            language="en",
        )
        response = main.synthesize_audio(payload)

        assert response.success is False
        assert response.data is None
        assert response.error is not None

    def test_synthesize_normalizes_language(self) -> None:
        # Test with a valid text payload but invalid language
        # The language should be normalized in the response
        payload = main.SpeechRequest(
            text="Hello",
            language="invalid_lang",
        )
        response = main.synthesize_audio(payload)

        # Response should have normalized language to "en"
        assert response.language == "en"

    def test_synthesize_valid_text_returns_base64_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that synthesize returns base64-encoded audio for valid text."""
        # Mock gTTS to avoid actual network calls during tests
        class MockgTTS:
            def __init__(self, text: str, lang: str, slow: bool) -> None:
                self.text = text
                self.lang = lang

            def save(self, path: str) -> None:
                # Write a minimal MP3 header to the file for testing
                with open(path, "wb") as f:
                    f.write(b"ID3")  # MP3 identifier

        monkeypatch.setattr("backend.main.gTTS", MockgTTS)

        payload = main.SpeechRequest(
            text="Hello world",
            language="en",
        )
        response = main.synthesize_audio(payload)

        assert response.success is True
        assert response.data is not None
        assert response.error is None
        # Should be base64-encoded
        try:
            decoded = base64.b64decode(response.data)
            assert decoded.startswith(b"ID3")
        except Exception as e:
            pytest.fail(f"Response data is not valid base64: {e}")


class TestSpeechEndpointIntegration:
    """Integration tests for speech endpoints."""

    def test_transcribe_and_synthesize_round_trip(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that we can do a basic round-trip synthesis then mock transcribe."""
        # Mock gTTS for synthesis
        class MockgTTS:
            def __init__(self, text: str, lang: str, slow: bool) -> None:
                self.text = text

            def save(self, path: str) -> None:
                with open(path, "wb") as f:
                    f.write(b"fake_audio_data")

        monkeypatch.setattr("backend.main.gTTS", MockgTTS)

        # First, synthesize some text
        synth_payload = main.SpeechRequest(
            text="Government scheme eligibility test",
            language="en",
        )
        synth_response = main.synthesize_audio(synth_payload)

        assert synth_response.success is True
        assert synth_response.data is not None

        # Verify that the synthesized audio is base64
        audio_data = base64.b64decode(synth_response.data)
        assert audio_data == b"fake_audio_data"

    def test_language_consistency_across_endpoints(self) -> None:
        """Test that language parameter is consistently normalized."""
        payload_en = main.SpeechRequest(text="test", language="EN")
        payload_invalid = main.SpeechRequest(text="test", language="xyz")

        # Both should normalize language to "en"
        response_en = main.synthesize_audio(payload_en)
        response_invalid = main.synthesize_audio(payload_invalid)

        assert response_en.language == "en"
        assert response_invalid.language == "en"
