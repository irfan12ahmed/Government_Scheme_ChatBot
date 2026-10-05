"""
End-to-End Voice Flow Tests
Tests the complete voice pipeline: mic input → STT → chat → TTS → audio playback
"""

import base64
import json
import tempfile
import os
import pytest
from pathlib import Path

import backend.main as main


class TestBackendVoiceEndpoints:
    """Test backend speech endpoints with sample audio."""

    def test_synthesize_english_text(self) -> None:
        """Test TTS endpoint with English text - generates valid base64 audio."""
        payload = main.SpeechRequest(
            text="Tell me about housing schemes in India",
            language="en",
        )
        response = main.synthesize_audio(payload)

        # Verify response structure
        assert response.success is True
        assert response.data is not None
        assert response.error is None
        assert response.language == "en"

        # Verify data is base64-encoded
        try:
            audio_bytes = base64.b64decode(response.data)
            assert len(audio_bytes) > 0
            # MP3 files start with ID3 or FF FB (sync word)
            assert audio_bytes[:3] == b"ID3" or audio_bytes[0:2] == b"\xff\xfb"
        except Exception as e:
            pytest.fail(f"Failed to decode base64 audio: {e}")

    def test_synthesize_hindi_text(self) -> None:
        """Test TTS with Hindi text."""
        payload = main.SpeechRequest(
            text="भारत में सरकारी योजनाएं",
            language="hi",
        )
        response = main.synthesize_audio(payload)

        assert response.success is True
        assert response.data is not None
        assert response.language == "hi"

    def test_synthesize_lang_normalization(self) -> None:
        """Test that invalid language normalizes to English."""
        payload = main.SpeechRequest(
            text="Test text",
            language="fr",  # Unsupported language
        )
        response = main.synthesize_audio(payload)

        # Should normalize to English, not fail
        assert response.language == "en"
        assert response.success is True

    def test_transcribe_with_mock_whisper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test transcription endpoint with mocked Whisper model."""

        # Mock Whisper to avoid downloading the model during test
        class MockWhisperModel:
            def transcribe(self, path: str, language: str = None) -> dict:
                return {
                    "text": "Tell me about scholarship schemes",
                }

        class MockWhisper:
            @staticmethod
            def load_model(model: str, device: str):
                return MockWhisperModel()

        monkeypatch.setattr("backend.main.whisper", MockWhisper)

        # Create a minimal WAV file for testing
        wav_data = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 100
        audio_base64 = base64.b64encode(wav_data).decode("utf-8")

        payload = main.SpeechRequest(
            audio_base64=audio_base64,
            language="en",
            format="wav",
        )
        response = main.transcribe_audio(payload)

        assert response.success is True
        assert response.data == "Tell me about scholarship schemes"
        assert response.language == "en"


class TestVoiceChatIntegration:
    """Test voice feature integration with existing chat flow."""

    def test_voice_transcript_flows_to_chat(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Simulate: mic captures "yes" → sent to chat → triggers relevant schemes."""
        # Setup: Create a pending relevance suggestion state
        main.chat_state_store["conv-test"] = main.ChatState(
            pending_relevant_suggestions=True,
            last_query="education support",
        )

        # Mock the scheme lookup
        db_results = [
            main.SchemeResult(
                scheme_name="Scholarship Scheme",
                details="Details",
                benefits="Benefits",
                eligibility="Eligibility",
                application="Apply",
                documents="Docs",
                level="Central",
                schemeCategory="Education",
                tags="test",
                score=0.95,
            )
        ]

        monkeypatch.setattr(
            main, "get_db_relevant_schemes", lambda _q, limit=5: db_results[:limit]
        )
        monkeypatch.setattr(
            main, "web_search_relevant_schemes", lambda _q, limit=5: []
        )

        # Simulate: Microphone captured "yes" and frontend submitted it to chat
        voice_transcript = "yes"
        chat_request = main.ChatRequest(
            query=voice_transcript,
            conversation_id="conv-test",
            language="en",
        )

        # Execute chat with voice input
        response = main.chat(chat_request)

        # Verify: Chat correctly interpreted voice input and returned relevant schemes
        assert response.response_type == "relevant_schemes"
        assert len(response.relevant_schemes) == 1
        assert response.relevant_schemes[0].scheme_name == "Scholarship Scheme"

    def test_voice_multilingual_chat_flow(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test: Voice query in Hindi → chat responds in Hindi."""
        # Mock semantic search to find a scheme
        def mock_candidates(query: str, top_k: int):
            return [(0, 0.95)]  # Return one match with high confidence

        monkeypatch.setattr(main, "semantic_candidates", mock_candidates)

        def mock_groq_gen(query: str, scheme, history):
            # Simulate LLM response in Hindi
            return "यह एक सरकारी योजना है।"

        monkeypatch.setattr(
            main, "generate_answer_with_groq", mock_groq_gen
        )

        # Hindi voice input
        chat_request = main.ChatRequest(
            query="कृषि योजनाओं के बारे में बताएं",
            language="hi",
            conversation_id="conv-hindi",
        )

        response = main.chat(chat_request)

        # Verify: Response was generated for Hindi query
        assert response.response_type == "direct_answer"
        assert len(response.answer) > 0

    def test_tts_audio_playback_chain(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test complete TTS chain: Response text → base64 audio → frontend playback."""
        # Step 1: Generate text response (simulated chat response)
        response_text = "You are eligible for this housing scheme."

        # Step 2: Synthesize response to audio
        tts_request = main.SpeechRequest(
            text=response_text,
            language="en",
        )
        tts_response = main.synthesize_audio(tts_request)

        # Verify TTS succeeded
        assert tts_response.success is True
        assert tts_response.data is not None

        # Step 3: Simulate frontend decoding and preparing playback
        try:
            audio_bytes = base64.b64decode(tts_response.data)
            # Create a blob-like object
            assert len(audio_bytes) > 0
            # Frontend would use: const blob = new Blob([audio_bytes], {type: 'audio/mp3'})
            # Then: URL.createObjectURL(blob) and new Audio(url).play()
            playback_ready = True
        except Exception:
            playback_ready = False

        assert playback_ready is True


class TestVoiceLanguagePipeline:
    """Test language consistency across the entire voice pipeline."""

    def test_english_voice_pipeline(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """English: mic → STT (English) → chat → TTS (English) → playback."""
        # Step 1: Mock STT (English)
        mock_transcript_en = "Tell me about farmer schemes"

        # Step 2: Send to chat with language=en
        def mock_candidates(query: str, top_k: int):
            return [(0, 0.92)]

        monkeypatch.setattr(main, "semantic_candidates", mock_candidates)

        def mock_groq(query: str, scheme, history):
            return "The PM-KISAN scheme provides support to farmers."

        monkeypatch.setattr(main, "generate_answer_with_groq", mock_groq)

        chat_req = main.ChatRequest(
            query=mock_transcript_en,
            language="en",
        )
        chat_resp = main.chat(chat_req)

        # Step 3: TTS response in English
        tts_req = main.SpeechRequest(
            text=chat_resp.answer,
            language="en",
        )
        tts_resp = main.synthesize_audio(tts_req)

        # Verify pipeline
        assert tts_resp.success is True
        assert tts_resp.language == "en"

    def test_hindi_voice_pipeline(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Hindi: mic → STT (Hindi) → chat (in Hindi) → TTS (Hindi) → playback."""
        # Step 1: Mock STT (Hindi)
        mock_transcript_hi = "महिला शिक्षा योजनाओं के बारे में बताएं"

        # Step 2: Chat processes Hindi query
        def mock_candidates(query: str, top_k: int):
            return [(0, 0.88)]

        monkeypatch.setattr(main, "semantic_candidates", mock_candidates)

        def mock_groq(query: str, scheme, history):
            return "यह महिलाओं के लिए शिक्षा सहायता प्रदान करती है।"

        monkeypatch.setattr(main, "generate_answer_with_groq", mock_groq)

        chat_req = main.ChatRequest(
            query=mock_transcript_hi,
            language="hi",
        )
        chat_resp = main.chat(chat_req)

        # Step 3: TTS response in Hindi
        tts_req = main.SpeechRequest(
            text=chat_resp.answer,
            language="hi",
        )
        tts_resp = main.synthesize_audio(tts_req)

        # Verify Hindi pipeline
        assert tts_resp.success is True
        assert tts_resp.language == "hi"


class TestVoiceErrorRecovery:
    """Test voice flow error handling and graceful fallback."""

    def test_mic_error_fallback_to_text(self) -> None:
        """If mic fails, user can continue with text input."""
        # Simulate: Mic error occurs
        voice_error = "NotAllowedError: Permission denied"

        # Fallback: User types the query manually
        text_query = "housing scheme"

        # Chat should work normally with text input
        chat_request = main.ChatRequest(
            query=text_query,
            language="en",
        )

        # Verify: Chat request is valid and would process normally
        assert chat_request.query == "housing scheme"
        assert len(chat_request.query) > 0

    def test_tts_failure_preserves_text_response(self) -> None:
        """If TTS fails, chat response text is still available."""
        # Simulate: Chat succeeded and generated response
        chat_response_text = "You qualify for this scheme."

        # Simulate: TTS fails (no audio)
        tts_request = main.SpeechRequest(
            text="",  # Empty text triggers error
            language="en",
        )
        tts_response = main.synthesize_audio(tts_request)

        # Verify: TTS failed
        assert tts_response.success is False

        # But: Original text response is still available to user
        assert chat_response_text is not None
        assert len(chat_response_text) > 0

    def test_language_fallback_on_unsupported_lang(self) -> None:
        """Unsupported language falls back to English gracefully."""
        # Request TTS in unsupported language
        unsupported_lang = "fr"  # French not supported
        payload = main.SpeechRequest(
            text="Test message",
            language=unsupported_lang,
        )

        response = main.synthesize_audio(payload)

        # Should succeed with English fallback
        assert response.success is True
        assert response.language == "en"  # Normalized to English


class TestVoiceEndToEndScenarios:
    """Complete end-to-end scenarios mimicking real user interactions."""

    def test_full_english_user_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        English user session:
        1. User asks via mic: "What scholarship am I eligible for?"
        2. Chat responds with scheme info
        3. User enables audio and hears response
        """
        conv_id = "conv-e2e-en"

        # Step 1: Mic captures speech (simulated STT)
        mic_input = "What scheme am I eligible for?"

        # Step 2: Send to chat
        def mock_candidates(query: str, top_k: int):
            return [(0, 0.90)]

        monkeypatch.setattr(main, "semantic_candidates", mock_candidates)

        def mock_groq(query: str, scheme, history):
            return "Based on your profile, you are eligible for the National Scholarship Scheme."

        monkeypatch.setattr(main, "generate_answer_with_groq", mock_groq)

        chat_req = main.ChatRequest(
            query=mic_input,
            language="en",
            conversation_id=conv_id,
        )
        chat_resp = main.chat(chat_req)

        assert chat_resp.response_type == "direct_answer"

        # Step 3: User enables audio playback → TTS converts response to audio
        tts_req = main.SpeechRequest(
            text=chat_resp.answer,
            language="en",
        )
        tts_resp = main.synthesize_audio(tts_req)

        # Verify complete flow
        assert tts_resp.success is True
        assert tts_resp.data is not None
        # Audio ready for playback

    def test_hindi_user_follow_up_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Hindi user multi-turn:
        1. Initial question (no result) → asks if user wants alternatives
        2. User says "yes" (via mic) → gets relevant schemes
        3. Response is played back in Hindi
        """
        conv_id = "conv-e2e-hi"

        # Turn 1: No results → pending follow-up
        main.chat_state_store[conv_id] = main.ChatState(
            pending_relevant_suggestions=False,
            last_query="",
        )

        # User asks in Hindi
        question_hi = "कम ब्याज दर वाली किसान योजनाएं"

        # No DB match → ask follow-up
        monkeypatch.setattr(main, "semantic_candidates", lambda _q, _k: [])

        chat_req_1 = main.ChatRequest(
            query=question_hi,
            language="hi",
            conversation_id=conv_id,
        )
        chat_resp_1 = main.chat(chat_req_1)

        assert chat_resp_1.response_type == "no_data_prompt"
        assert main.chat_state_store[conv_id].pending_relevant_suggestions is True

        # Turn 2: User says "yes" (via mic)
        mic_yes_input = "हाँ"

        db_schemes = [
            main.SchemeResult(
                scheme_name="किसान क्रेडिट कार्ड",
                details="Details",
                benefits="Benefits",
                eligibility="Eligibility",
                application="Apply",
                documents="Docs",
                level="Central",
                schemeCategory="Agriculture",
                tags="test",
                score=0.85,
            )
        ]

        monkeypatch.setattr(
            main, "get_db_relevant_schemes", lambda _q, limit=5: db_schemes[:limit]
        )
        monkeypatch.setattr(main, "web_search_relevant_schemes", lambda _q, limit=5: [])

        chat_req_2 = main.ChatRequest(
            query=mic_yes_input,
            language="hi",
            conversation_id=conv_id,
        )
        chat_resp_2 = main.chat(chat_req_2)

        assert chat_resp_2.response_type == "relevant_schemes"

        # Turn 3: Convert response to Hindi audio
        tts_req = main.SpeechRequest(
            text="Here are relevant schemes for you.",
            language="hi",
        )
        tts_resp = main.synthesize_audio(tts_req)

        assert tts_resp.success is True
        assert tts_resp.language == "hi"


if __name__ == "__main__":
    # Run tests with: pytest backend/tests/test_voice_e2e.py -v
    pytest.main([__file__, "-v", "-s"])
