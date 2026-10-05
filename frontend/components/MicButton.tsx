"use client";

import { useEffect, useRef, useState } from "react";
import * as audioApi from "@/lib/audioApi";

interface MicButtonProps {
  language: string;
  onTranscript: (transcript: string) => void;
  onError: (error: string) => void;
  disabled?: boolean;
}

export default function MicButton({
  language,
  onTranscript,
  onError,
  disabled = false,
}: MicButtonProps) {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    // Initialize Web Speech API
    recognitionRef.current = audioApi.initializeSpeechRecognition(
      language,
      setTranscript,
      onError,
      () => setIsListening(false),
    );
  }, [language, onError]);

  const startListening = async () => {
    setTranscript("");
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
    // When stopped, pass the final transcript up to parent
    if (transcript.trim()) {
      onTranscript(transcript.trim());
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={isListening ? stopListening : startListening}
        disabled={disabled}
        className={`px-4 py-2 rounded-lg font-semibold transition-colors flex items-center gap-2 ${
          isListening
            ? "bg-red-500 hover:bg-red-600 text-white"
            : "bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 text-white"
        }`}
        title={isListening ? "Stop recording" : "Click to speak"}
      >
        {isListening ? (
          <>
            <span className="animate-pulse inline-block w-3 h-3 bg-white rounded-full"></span>
            Stop
          </>
        ) : (
          <>
            <span>🎤</span>
            Mic
          </>
        )}
      </button>

      {/* Live transcript preview */}
      {isListening && transcript && (
        <div className="text-sm bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-blue-900">
          <span className="font-semibold">Listening: </span>
          {transcript}
        </div>
      )}

      {/* Error display */}
      {/* Errors already shown in parent search bar, but can duplicate here if needed */}
    </div>
  );
}
