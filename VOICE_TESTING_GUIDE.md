# Voice Assistant End-to-End Testing Guide

## Overview

This guide walks through complete testing of the voice assistant feature with sample audio and real-world scenarios.

**Testing Status**: ✅ Ready to test

## Prerequisites

### System Requirements

- Python 3.10+
- Node.js 18+ (for frontend testing)
- 2-4 GB RAM (for Whisper model on first run)
- 500 MB free disk space (for Whisper cache)

### Dependencies Installed

```bash
# Backend dependencies (already added)
pip install -r backend/requirements.txt

# Frontend dependencies (already installed)
npm install --prefix frontend
```

### First-Time Setup

**Note**: Whisper model downloads on first STT call:

- Model size: ~140 MB
- Download time: ~30 seconds (depends on internet)
- Location: `~/.cache/whisper/` (cached after first download)

---

## Testing Phases

### Phase 1: Backend Endpoint Tests

#### 1a. Unit Tests (No Audio Needed)

```bash
# Test speech models, language mapping, error handling
pytest backend/tests/test_speech.py -v

# Expected: All 16 tests pass
```

#### 1b. End-to-End Backend Tests (With Mocks)

```bash
# Test complete voice flows with mocked audio
pytest backend/tests/test_voice_e2e.py -v

# Expected: All 18 tests pass
# Tests include:
#   - TTS in English, Hindi, Telugu, Tamil
#   - Language normalization
#   - Voice + Chat integration
#   - Multi-turn voice conversations
#   - Error recovery scenarios
```

#### 1c. Manual Endpoint Testing (Real Audio)

```bash
# Start backend first
python -m uvicorn backend.main:app --reload --port 8000

# In another terminal, run endpoint tests
python test_voice_endpoints.py

# Expected output:
#   ✅ Language support tests (en/hi/te/ta)
#   ✅ Error scenario tests
#   ✅ Audio generation (generates .mp3 files)
#   ✅ Chat integration tests
```

**Test files generated:**

```
test_output_en.mp3      # English TTS output
test_output_hi.mp3      # Hindi TTS output
test_output_te.mp3      # Telugu TTS output
test_output_ta.mp3      # Tamil TTS output
chat_response.mp3       # Chat response audio
```

You can play these with any audio player:

```bash
# Windows
start test_output_en.mp3

# Mac
open test_output_en.mp3

# Linux
mpv test_output_en.mp3
```

---

### Phase 2: Frontend Voice UI Tests

#### 2a. Manual Browser Testing

**Start the dev environment:**

```bash
# Terminal 1: Backend
python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev

# Open http://localhost:3000 in browser
```

**Test Checklist:**

✅ **Mic Button Visibility**

- [ ] After login, scroll to chat section
- [ ] If browser supports Web Speech API, mic button (🎤) appears next to Search button
- [ ] On Chrome/Edge: Should appear immediately
- [ ] On Firefox: Should appear (with webkit support)
- [ ] On Safari: Should appear

✅ **Push-to-Talk Recording**

- [ ] Click 🎤 button
- [ ] Button turns red with "Stop" label
- [ ] Pulsing indicator shows recording active
- [ ] Speak clearly: "Tell me about housing schemes"
- [ ] Click "Stop"
- [ ] Transcript appears in search box as you finish speaking (live preview)
- [ ] Query automatically submits to chat

✅ **Voice with Different Languages**

- [ ] Change language to "हिंदी" (Hindi) using dropdown
- [ ] Mic button updates to use Hindi locale
- [ ] Speak Hindi: "सरकारी योजनाओं के बारे में बताएं"
- [ ] Chat processes in Hindi
- [ ] Test with Telugu (తెలుగు) and Tamil (தமிழ్)

✅ **Assistant Speech Toggle**

- [ ] Locate 🔊 Speak toggle next to language selector
- [ ] Toggle ON
- [ ] Submit a query
- [ ] Wait for response to complete
- [ ] Audio should play automatically
- [ ] Toggle OFF
- [ ] Submit another query
- [ ] Audio should NOT play

✅ **Manual Speaker Button**

- [ ] Assistant provides response (no audio)
- [ ] Click 🔊 Listen button on message
- [ ] Audio plays
- [ ] Button shows "Playing..." while active
- [ ] Audio playback completes

✅ **Error Handling**

- [ ] Deny microphone permission when prompted
- [ ] Error message should appear below chat
- [ ] Chat still works with text input
- [ ] Error can be dismissed

✅ **Voice Error Recovery**

- [ ] Enable audio toggle
- [ ] If TTS response fails, chat text is still visible
- [ ] Error message appears non-blocking
- [ ] User can continue with text input

---

### Phase 3: Integration Tests

#### 3a. Full Voice Chat Flow

**Scenario: User asks via voice, gets response in voice**

1. Start backend & frontend (see Phase 2a)
2. Login to application
3. Enable 🔊 Speak toggle
4. Click 🎤 button
5. Say: "What housing schemes are available?"
6. Wait for transcription
7. Chat processes query
8. Response appears in text
9. Audio plays automatically
10. Verify audio quality and language match

#### 3b. Multilingual Chat with Voice

**Scenario: User asks in Hindi, gets response in Hindi with voice**

1. Change language to "हिंदी"
2. Enable voice toggle
3. Click mic
4. Speak in Hindi: "किसानों के लिए क्या योजनाएं हैं?"
5. Wait for transcription in Hindi
6. Response in Hindi appears
7. Audio plays in Hindi

#### 3c. Follow-up Question with Voice

**Scenario: No results → user says yes → gets schemes → hears response**

1. Click mic
2. Ask for: "Advanced quantum computing subsidies" (not in database)
3. Chat responds with "no data found" prompt
4. Click mic again
5. Say: "yes"
6. Chat returns relevant schemes
7. If audio enabled, schemes list is read aloud

---

### Phase 4: Edge Cases & Error Scenarios

#### 4a. Test Error Recovery

```bash
# Stop backend mid-recording
python test_voice_endpoints.py

# Expected:
#   Should show error in UI
#   Can retry or continue with text
```

#### 4b. Test Language Fallback

- Request unsupported language (e.g., French)
- Should normalize to English without error
- Response still plays correctly

#### 4c. Test Very Long Responses

- Ask a question that generates long response
- TTS should still work (may take longer)
- Audio playback should handle full response

#### 4d. Test Rapid Requests

- Mic input
- Chat response
- Another mic input while audio still playing
- Should handle gracefully

---

## Test Results Summary Template

Use this to document your test run:

```markdown
## Voice Assistant Testing Results

**Date**: [Date]
**Tester**: [Name]
**Environment**: Windows 10 / Chrome 120

### Backend Tests

- [ ] Unit tests (test_speech.py): ✅ 16/16 passed
- [ ] E2E tests (test_voice_e2e.py): ✅ 18/18 passed
- [ ] Endpoint tests (test_voice_endpoints.py): ✅ All passed
  - ✅ English TTS
  - ✅ Hindi TTS
  - ✅ Telugu TTS
  - ✅ Tamil TTS
  - ✅ Language normalization
  - ✅ Error scenarios

### Frontend Tests

- [ ] Mic button visibility: ✅
- [ ] Push-to-talk recording: ✅
- [ ] Live transcript preview: ✅
- [ ] English voice: ✅
- [ ] Hindi voice: ✅
- [ ] Telugu voice: ✅
- [ ] Tamil voice: ✅
- [ ] Audio toggle: ✅
- [ ] Manual speaker button: ✅
- [ ] Error handling: ✅

### Integration Tests

- [ ] Full voice chat flow: ✅
- [ ] Multilingual voice: ✅
- [ ] Follow-up questions with voice: ✅

### Issues Found

(List any bugs or unexpected behavior)

### Performance Notes

- STT latency: ~2-5s
- TTS latency: ~1-3s
- Audio playback quality: Good/Excellent
```

---

## Troubleshooting

### Mic Button Doesn't Appear

**Cause**: Browser doesn't support Web Speech API
**Solution**:

- Use Chrome, Edge, Firefox, or Safari (all supported)
- Check browser console for errors: F12 → Console
- Ensure JavaScript is enabled

### "No speech detected" Error

**Cause**: Audio too quiet or microphone not working
**Solution**:

- Check microphone isn't muted
- Speak louder and clearer
- Test microphone in browser settings
- Check browser microphone permissions

### Audio Doesn't Play

**Cause**: Speaker muted or no audio output
**Solution**:

- Check system volume
- Check browser volume
- Test with another website's audio first
- Check browser audio permissions

### TTS Takes Too Long

**Cause**: Whisper model downloading on first run, or slow internet
**Solution**:

- First TTS call loads ~140 MB model (~30s)
- Subsequent calls are much faster (cached)
- Check internet connection

### Chat Doesn't Respond to Voice Input

**Cause**: STT failed silently, API error, or mic permission denied
**Solution**:

- Check browser console for errors
- Ensure backend is running (try `/health` endpoint)
- Check voice error message displayed in UI
- Use text input as fallback

---

## Performance Benchmarks

Expected timings on typical hardware:

| Operation      | Time   | Notes                      |
| -------------- | ------ | -------------------------- |
| First STT call | ~30s   | Model download             |
| Subsequent STT | 2-5s   | Whisper base model         |
| TTS (English)  | 1-3s   | gTTS                       |
| TTS (Hindi)    | 2-4s   | gTTS with non-Latin script |
| Audio playback | <100ms | Browser HTML5 Audio        |
| Chat response  | 2-8s   | Groq API + streaming       |

---

## Browser Compatibility Matrix

| Browser | Version | Web Speech API | Status          |
| ------- | ------- | -------------- | --------------- |
| Chrome  | 90+     | ✅             | Fully supported |
| Edge    | 90+     | ✅             | Fully supported |
| Firefox | 90+     | ✅             | Fully supported |
| Safari  | 15+     | ✅             | Fully supported |
| Opera   | 76+     | ✅             | Fully supported |
| IE 11   | All     | ❌             | Not supported   |

---

## Next Steps After Testing

1. **Document any issues found** in GitHub Issues
2. **Performance optimization** if needed (model size, caching)
3. **Deployment checklist** for production
4. **User documentation** for voice features
5. **Monitoring setup** for voice endpoint performance

---

## Quick Commands Reference

```bash
# Run all backend tests
pytest backend/tests/ -v

# Run only voice tests
pytest backend/tests/test_voice_e2e.py -v

# Run endpoint tests with real audio generation
python test_voice_endpoints.py

# Start backend
python -m uvicorn backend.main:app --reload --port 8000

# Start frontend
cd frontend && npm run dev

# Clear Whisper cache
rm -rf ~/.cache/whisper/
```

---

## Support & Questions

If tests fail or behavior is unexpected:

1. Check the troubleshooting section above
2. Review error messages in browser console (F12)
3. Check backend logs for API errors
4. Verify backend is running: `curl http://localhost:8000/health`
5. Review implementation docs: [VOICE_IMPLEMENTATION.md](VOICE_IMPLEMENTATION.md)
