"use client";

import { KeyboardEvent } from "react";
import * as React from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSearch: (value: string) => void;
  onMicTranscript?: (transcript: string) => void;
  onVoiceError?: (error: string) => void;
  loading: boolean;
  placeholder?: string;
  buttonText?: string;
  loadingText?: string;
  ariaLabel?: string;
  showMic?: boolean;
  micLanguage?: string;
}

export default function SearchBar({
  value,
  onChange,
  onSearch,
  onMicTranscript,
  onVoiceError,
  loading,
  placeholder = "e.g. housing scheme for poor families, farmer loan waiver, scholarship for students…",
  buttonText = "Search",
  loadingText = "Searching…",
  ariaLabel = "Search government schemes",
  showMic = false,
  micLanguage = "en",
}: Props) {
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(value);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      // Let form onSubmit handle Enter once to avoid duplicate requests.
      e.preventDefault();
    }
  };

  const handleMicTranscript = (transcript: string) => {
    if (transcript) {
      onChange(transcript);

      // If parent handles mic transcript, avoid calling onSearch here again.
      if (onMicTranscript) {
        onMicTranscript(transcript);
      } else {
        onSearch(transcript);
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-3">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="flex-1 border border-gray-300 rounded-xl px-5 py-3 text-gray-800 placeholder-gray-400
                   focus:outline-none focus:ring-2 focus:ring-orange-400 shadow-sm text-base"
        disabled={loading}
        aria-label={ariaLabel}
      />

      {/* Mic button if voice is enabled */}
      {showMic && (
        <MicButtonInline
          language={micLanguage}
          onTranscript={handleMicTranscript}
          onError={onVoiceError || (() => {})}
          disabled={loading}
        />
      )}

      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="bg-orange-500 hover:bg-orange-600 disabled:bg-orange-300 text-white font-semibold
                   px-7 py-3 rounded-xl shadow-sm transition-colors whitespace-nowrap cursor-pointer"
      >
        {loading ? (
          <span className="flex items-center gap-2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            {loadingText}
          </span>
        ) : (
          buttonText
        )}
      </button>
    </form>
  );
}

/**
 * Inline mic button for use within SearchBar
 */
function MicButtonInline({
  language,
  onTranscript,
  onError,
  disabled = false,
}: {
  language: string;
  onTranscript: (text: string) => void;
  onError: (error: string) => void;
  disabled: boolean;
}) {
  const [isListening, setIsListening] = React.useState(false);
  const recognitionRef = React.useRef<any>(null);

  React.useEffect(() => {
    // Initialize Web Speech API
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      return;
    }

    const recognition = new SpeechRecognition();
    const langMap: Record<string, string> = {
      en: "en-US",
      hi: "hi-IN",
      te: "te-IN",
      ta: "ta-IN",
    };

    recognition.language = langMap[language] || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    let finalTranscript = "";

    recognition.onstart = () => {
      finalTranscript = "";
    };

    recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript + " ";
        }
      }
    };

    recognition.onerror = (event: any) => {
      onError(`Speech error: ${event.error}`);
    };

    recognition.onend = () => {
      setIsListening(false);
      if (finalTranscript.trim()) {
        onTranscript(finalTranscript.trim());
      }
    };

    recognitionRef.current = recognition;
  }, [language, onTranscript, onError]);

  const startListening = () => {
    onError("");
    setIsListening(true);
    if (recognitionRef.current) {
      recognitionRef.current.start();
    }
  };

  const stopListening = () => {
    setIsListening(false);
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  };

  return (
    <button
      type="button"
      onClick={isListening ? stopListening : startListening}
      disabled={disabled}
      className={`px-4 py-3 rounded-xl font-semibold transition-colors flex items-center justify-center gap-2 min-w-fit ${
        isListening
          ? "bg-red-500 hover:bg-red-600 text-white"
          : "bg-gray-600 hover:bg-gray-700 disabled:bg-gray-300 text-white"
      }`}
      title={isListening ? "Stop recording" : "Click to speak"}
      aria-label={isListening ? "Stop recording" : "Speak query"}
    >
      {isListening ? (
        <>
          <span className="animate-pulse inline-block w-2 h-2 bg-white rounded-full"></span>
          <span className="text-sm">Stop</span>
        </>
      ) : (
        <>
          <span>🎤</span>
        </>
      )}
    </button>
  );
}
