"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import MicButton from "@/components/MicButton";
import * as audioApi from "@/lib/audioApi";
import { useAuthSession } from "@/lib/useAuthSession";

type LanguageCode = "en" | "hi" | "te" | "ta";

interface VoiceChatResponse {
  query: string;
  answer: string;
  language: string;
}

interface VoiceHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

type VoiceStep = "language_selection" | "scheme_query";

const LANGUAGE_SELECTION_PROMPT =
  "Can you please choose your preferred language?";
const SCHEME_HELP_PROMPT = "How can I help you regarding government schemes?";

export default function VoicePage() {
  const { token, user, sessionLoading, clearSession } = useAuthSession();
  const [voiceLanguage, setVoiceLanguage] = useState<LanguageCode>("en");
  const [voiceStep, setVoiceStep] = useState<VoiceStep>("language_selection");
  const [voicePrompt, setVoicePrompt] = useState(LANGUAGE_SELECTION_PROMPT);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState("");
  const [voiceHistory, setVoiceHistory] = useState<VoiceHistoryMessage[]>([]);
  const [queryLoading, setQueryLoading] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [isSpeaking, setIsSpeaking] = useState(false);

  const languageNames: Record<LanguageCode, string> = {
    en: "English",
    hi: "हिंदी",
    te: "తెలుగు",
    ta: "தமிழ்",
  };

  const greetingName = useMemo(() => user?.name || "Citizen", [user]);

  useEffect(() => {
    const speechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    const canSpeak =
      typeof window !== "undefined" && "speechSynthesis" in window;
    setVoiceSupported(Boolean(speechRecognition || canSpeak));
  }, []);

  function detectLanguageFromTranscript(rawText: string): LanguageCode | null {
    const text = rawText.trim().toLowerCase();
    if (!text) return null;

    const languageHints: Record<LanguageCode, string[]> = {
      en: ["english", "eng", "inglish"],
      hi: ["hindi", "hind", "हिंदी", "हिन्दी"],
      te: ["telugu", "తెలుగు"],
      ta: ["tamil", "தமிழ்", "thamizh"],
    };

    for (const [code, hints] of Object.entries(languageHints) as [
      LanguageCode,
      string[],
    ][]) {
      if (hints.some((hint) => text.includes(hint))) {
        return code;
      }
    }

    return null;
  }

  async function askSchemeAssistant(query: string): Promise<VoiceChatResponse> {
    const response = await fetch("/api/voice-assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        language: voiceLanguage,
        history: voiceHistory,
      }),
    });

    if (!response.ok) {
      const raw = await response.text();
      throw new Error(raw || "Voice assistant request failed");
    }

    return (await response.json()) as VoiceChatResponse;
  }

  async function handleSchemeVoiceQuery(queryText: string) {
    const clean = queryText.trim();
    if (!clean) return;

    setQueryLoading(true);
    setVoiceError("");
    setTranscript(clean);
    try {
      const response = await askSchemeAssistant(clean);
      setAssistantAnswer(response.answer || "I could not find an answer.");
      setVoiceHistory((prev) => {
        const next = [
          ...prev,
          { role: "user" as const, content: clean },
          { role: "assistant" as const, content: response.answer || "" },
        ];
        return next.slice(-8);
      });
      setVoicePrompt(SCHEME_HELP_PROMPT);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Voice assistant request failed";
      setVoiceError(msg);
    } finally {
      setQueryLoading(false);
    }
  }

  async function handleMicTranscript(text: string) {
    const clean = text.trim();
    if (!clean) return;

    setVoiceError("");

    if (voiceStep === "language_selection") {
      const detectedLanguage = detectLanguageFromTranscript(clean);
      if (!detectedLanguage) {
        setVoicePrompt(
          `${LANGUAGE_SELECTION_PROMPT} (English, Hindi, Telugu, Tamil)`,
        );
        setVoiceError(
          "Could not detect language. Please say English, Hindi, Telugu, or Tamil.",
        );
        return;
      }

      setVoiceLanguage(detectedLanguage);
      setVoiceStep("scheme_query");
      setAssistantAnswer("");
      setVoiceHistory([]);
      setVoicePrompt(
        `${SCHEME_HELP_PROMPT} Selected language: ${languageNames[detectedLanguage]}.`,
      );
      return;
    }

    await handleSchemeVoiceQuery(clean);
  }

  async function handleSpeak(text: string) {
    const clean = text.trim();
    if (!clean) {
      setVoiceError("Enter text or record audio before playback.");
      return;
    }

    setVoiceError("");
    setIsSpeaking(true);
    try {
      const result = await audioApi.synthesizeAndPlayAudio(
        clean,
        voiceLanguage,
      );
      if (!result.success) {
        setVoiceError(result.error || "Voice playback failed");
        return;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Voice playback failed";
      setVoiceError(msg);
    } finally {
      setIsSpeaking(false);
    }
  }

  function logout() {
    clearSession();
  }

  if (sessionLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-green-50 flex items-center justify-center p-4">
        <section className="w-full max-w-lg bg-white rounded-2xl border border-orange-100 shadow-xl p-7 text-center">
          <p className="text-sm text-gray-500">Loading session...</p>
        </section>
      </main>
    );
  }

  if (!token || !user) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-green-50 flex items-center justify-center p-4">
        <section className="w-full max-w-lg bg-white rounded-2xl border border-orange-100 shadow-xl p-7 text-center">
          <h1 className="text-2xl font-extrabold text-gray-800">
            Voice Assistant
          </h1>
          <p className="text-sm text-gray-500 mt-2">
            Login from the main page to use voice features.
          </p>
          <Link
            href="/"
            className="mt-5 inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
          >
            Back To Main
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-green-50">
      <header className="border-b border-orange-100 bg-white/90 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-5 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold text-gray-800">
              Voice Assistant
            </h1>
            <p className="text-sm text-gray-500">
              Hello {greetingName} - dedicated voice input and playback
              workspace
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="text-sm px-4 py-2 rounded-lg border border-gray-300 hover:bg-gray-50"
            >
              Back To Chat
            </Link>
            <button
              onClick={logout}
              className="text-sm px-4 py-2 rounded-lg border border-gray-300 hover:bg-gray-50"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <section className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        <section className="bg-white rounded-2xl border border-orange-100 shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-800">Voice Input</h2>
          <p className="text-sm text-gray-500 mt-1">
            Press the mic and follow the guided voice flow for language and
            scheme queries.
          </p>

          <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
            {voicePrompt}
          </div>

          <div className="mt-4 flex items-center gap-3 flex-wrap">
            <label
              htmlFor="voice-lang"
              className="text-sm font-medium text-gray-700"
            >
              Language:
            </label>
            <select
              id="voice-lang"
              value={voiceLanguage}
              onChange={(e) => setVoiceLanguage(e.target.value as LanguageCode)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white hover:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              {(Object.keys(languageNames) as LanguageCode[]).map((lang) => (
                <option key={lang} value={lang}>
                  {languageNames[lang]}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4">
            <MicButton
              language={voiceLanguage}
              onTranscript={(text) => {
                void handleMicTranscript(text);
              }}
              onError={(error) => setVoiceError(error)}
              disabled={!voiceSupported || isSpeaking || queryLoading}
            />
          </div>

          <div className="mt-3 flex items-center gap-2 text-xs text-gray-600">
            <span className="rounded-full bg-gray-100 px-2 py-1">
              Step:{" "}
              {voiceStep === "language_selection"
                ? "Choose language"
                : "Ask scheme"}
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-1">
              Active language: {languageNames[voiceLanguage]}
            </span>
          </div>

          <div className="mt-4 space-y-3">
            <label className="block text-sm font-medium text-gray-700">
              Transcript
            </label>
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              rows={4}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              placeholder="Your recorded transcript appears here..."
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleSchemeVoiceQuery(transcript)}
                disabled={queryLoading || !transcript.trim()}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:bg-green-300"
              >
                {queryLoading ? "Searching..." : "Ask About This Scheme"}
              </button>
              <button
                type="button"
                onClick={() => void handleSpeak(transcript)}
                disabled={isSpeaking || !transcript.trim()}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-blue-300"
              >
                {isSpeaking ? "Playing..." : "Play Transcript"}
              </button>
            </div>
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-orange-100 shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-800">
            Scheme Assistant Response
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Voice queries are answered directly by Groq without database lookup.
          </p>

          {!assistantAnswer && (
            <p className="mt-4 text-sm text-gray-500">
              Ask a scheme question using mic or transcript to see assistant
              results.
            </p>
          )}

          {assistantAnswer && (
            <>
              <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-800 whitespace-pre-wrap">
                {assistantAnswer}
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleSpeak(assistantAnswer)}
                  disabled={isSpeaking}
                  className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-600 disabled:bg-orange-300"
                >
                  {isSpeaking ? "Playing..." : "Play Answer"}
                </button>
              </div>
            </>
          )}
        </section>

        {voiceError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {voiceError}
            <button
              onClick={() => setVoiceError("")}
              className="ml-2 underline hover:no-underline"
            >
              Dismiss
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
