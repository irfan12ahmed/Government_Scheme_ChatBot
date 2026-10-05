"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import SearchBar from "@/components/SearchBar";
import SchemeCard from "@/components/SchemeCard";
import { AppUserProfile, useAuthSession } from "@/lib/useAuthSession";

type LanguageCode = "en" | "hi" | "te" | "ta";
type BoolLike = boolean;

interface Scheme {
  scheme_name: string;
  details: string;
  benefits: string;
  eligibility: string;
  application: string;
  documents: string;
  level: string;
  schemeCategory: string;
  tags: string;
  score: number;
}

interface CategorySummary {
  category: string;
  count: number;
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AppUserProfile;
}

interface ChatResponse {
  query: string;
  answer: string;
  source_scheme: Scheme | null;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  scheme?: Scheme;
  relevantSchemes?: Scheme[];
  responseType?: "direct_answer" | "no_data_prompt" | "relevant_schemes";
  streaming?: boolean;
  error?: string;
}

const emptyProfileForm = {
  name: "",
  age: "",
  gender: "",
  state: "",
  occupation: "",
  income: "",
  category: "",
  disability: false,
  student_status: false,
  farmer_status: false,
};

export default function Home() {
  const { token, user, sessionLoading, setSession, updateUser, clearSession } =
    useAuthSession();
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileForm, setProfileForm] = useState(emptyProfileForm);

  const [recommendations, setRecommendations] = useState<Scheme[]>([]);
  const [recommendLoading, setRecommendLoading] = useState(false);

  const [eligible, setEligible] = useState<Scheme[]>([]);
  const [eligibleLoading, setEligibleLoading] = useState(false);

  const [chatQuery, setChatQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLanguage, setChatLanguage] = useState<LanguageCode>("en");
  const [chatLoading, setChatLoading] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const conversationIdRef = useRef<string>("");
  const messageSeqRef = useRef(0);

  const [categories, setCategories] = useState<CategorySummary[]>([]);

  function validateSignupPassword(rawPassword: string): string | null {
    if (rawPassword.length < 8) {
      return "Password must be at least 8 characters long.";
    }
    if (!/[A-Z]/.test(rawPassword)) {
      return "Password must include at least 1 uppercase letter.";
    }
    if (!/\d/.test(rawPassword)) {
      return "Password must include at least 1 number.";
    }
    if (!/[^A-Za-z0-9]/.test(rawPassword)) {
      return "Password must include at least 1 special character.";
    }
    if (new TextEncoder().encode(rawPassword).length > 72) {
      return "Password is too long. Please keep your password to 72 characters or fewer.";
    }
    return null;
  }

  useEffect(() => {
    if (!token) return;
    void fetchCategories();
  }, [token]);

  useEffect(() => {
    if (!user) return;

    setProfileForm({
      name: user.name ?? "",
      age: user.age?.toString() ?? "",
      gender: user.gender ?? "",
      state: user.state ?? "",
      occupation: user.occupation ?? "",
      income: user.income?.toString() ?? "",
      category: user.category ?? "",
      disability: Boolean(user.disability),
      student_status: Boolean(user.student_status),
      farmer_status: Boolean(user.farmer_status),
    });
  }, [user]);

  useEffect(() => {
    if (!token || !user) return;
    void loadRecommendations(token);
  }, [token, user]);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop =
        chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    const saved = localStorage.getItem("gs_conversation_id");
    if (saved) {
      conversationIdRef.current = saved;
      return;
    }
    const newId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `conv-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    conversationIdRef.current = newId;
    localStorage.setItem("gs_conversation_id", newId);
  }, []);

  const greetingName = useMemo(() => user?.name || "Citizen", [user]);
  const isAwaitingYesNoFollowup = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const msg = messages[i];
      if (msg.role === "assistant") {
        return msg.responseType === "no_data_prompt";
      }
    }
    return false;
  }, [messages]);
  const isTypingYesNoReply = useMemo(() => {
    const value = chatQuery.trim().toLowerCase();
    if (!value) return false;
    return /^(y|ye|yes|n|no|nah|nope)(\b|\s|$)/.test(value);
  }, [chatQuery]);

  const languageNames: Record<LanguageCode, string> = {
    en: "English",
    hi: "हिंदी",
    te: "తెలుగు",
    ta: "தமிழ்",
  };

  const chatI18n: Record<LanguageCode, Record<string, string>> = {
    en: {
      title: "Ask our AI Assistant",
      subtitle: "Ask me about government schemes, eligibility, benefits & more",
      empty: "No chat history yet. Ask me anything about government schemes!",
      search_placeholder: "e.g. housing scheme, farmer loan, scholarship...",
      search_btn: "Search",
      searching: "Searching...",
      search_aria: "Search government schemes",
      language_label: "Language:",
      awaiting_reply: "Awaiting your yes/no reply",
    },
    hi: {
      title: "हमारे AI सहायक से पूछें",
      subtitle: "सरकारी योजनाओं, पात्रता, लाभ और अन्य के बारे में पूछें",
      empty:
        "अभी कोई चैट इतिहास नहीं है। सरकारी योजनाओं के बारे में मुझसे कोई भी प्रश्न पूछें!",
      search_placeholder: "जैसे आवास योजना, कृषक ऋण, छात्रवृत्ति...",
      search_btn: "खोजें",
      searching: "खोज रहे हैं...",
      search_aria: "सरकारी योजनाएं खोजें",
      language_label: "भाषा:",
      awaiting_reply: "आपके हाँ/नहीं उत्तर की प्रतीक्षा है",
    },
    te: {
      title: "మా AI సహాయకుడిని అడగండి",
      subtitle:
        "ప్రభుత్వ పథకాలు, అర్హత, ప్రయోజనాలు మరియు మరిన్నింటి గురించి నన్నను అడగండి",
      empty:
        "ఇంకా చాట్ చరిత్ర లేదు. ప్రభుత్వ పథకాల గురించి నన్నను ఏదైనా అడగండి!",
      search_placeholder: "ఉదా. హౌసింగ్ పథకం, రైతు రుణం, స్కాలర్‌షిప్...",
      search_btn: "శోధించండి",
      searching: "శోధిస్తున్నారు...",
      search_aria: "ప్రభుత్వ పథకాలను శోధించండి",
      language_label: "భాష:",
      awaiting_reply: "మీ అవును/కాదు సమాధానం కోసం ఎదురుచూస్తున్నాము",
    },
    ta: {
      title: "எங்கள் AI உதவியாளரிடம் கேளுங்கள்",
      subtitle: "அரசு திட்டங்கள், தகுதி, நன்மைகள் மற்றும் பல பற்றி கேளுங்கள்",
      empty:
        "இன்னும் சாட் வரலாறு இல்லை. அரசு திட்டங்கள் பற்றி எனக்கு எதையும் கேளுங்கள்!",
      search_placeholder:
        "எ.கா. வீட்டுத் திட்டம், விவசாயி கடன், ஆண்டவர் உதவி...",
      search_btn: "தேடல்",
      searching: "தேடுகிறது...",
      search_aria: "அரசு திட்டங்களை தேடுங்கள்",
      language_label: "மொழி:",
      awaiting_reply: "உங்கள் ஆம்/இல்லை பதிலுக்கு காத்திருக்கிறது",
    },
  };

  const chatText = useMemo(() => chatI18n[chatLanguage], [chatLanguage]);

  function authHeaders(authToken: string): HeadersInit {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    };
  }

  async function fetchCategories() {
    const res = await fetch("/api/categories");
    if (!res.ok) return;
    const data = (await res.json()) as CategorySummary[];
    setCategories(data);
  }

  async function loadRecommendations(authToken: string) {
    setRecommendLoading(true);
    try {
      const res = await fetch("/api/recommendations?top_k=6", {
        headers: authHeaders(authToken),
      });
      if (!res.ok) throw new Error("Unable to load recommendations");
      const data = (await res.json()) as Scheme[];
      setRecommendations(data);
    } catch {
      setRecommendations([]);
    } finally {
      setRecommendLoading(false);
    }
  }

  async function handleAuthSubmit(e: FormEvent) {
    e.preventDefault();

    if (authMode === "signup") {
      const signupPasswordError = validateSignupPassword(password);
      if (signupPasswordError) {
        setAuthError(signupPasswordError);
        return;
      }
    }

    setAuthLoading(true);
    setAuthError("");

    try {
      const endpoint = authMode === "login" ? "/auth/login" : "/auth/signup";
      const payload =
        authMode === "login"
          ? { username, password }
          : {
              username,
              name: name.trim() || username,
              password,
            };

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const raw = await res.text();
        throw new Error(raw || "Authentication failed");
      }

      const data = (await res.json()) as AuthResponse;
      setSession(data.access_token, data.user);

      setProfileForm({
        name: data.user.name ?? "",
        age: data.user.age?.toString() ?? "",
        gender: data.user.gender ?? "",
        state: data.user.state ?? "",
        occupation: data.user.occupation ?? "",
        income: data.user.income?.toString() ?? "",
        category: data.user.category ?? "",
        disability: Boolean(data.user.disability),
        student_status: Boolean(data.user.student_status),
        farmer_status: Boolean(data.user.farmer_status),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Authentication failed";
      setAuthError(msg);
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleProfileSave(e: FormEvent) {
    e.preventDefault();
    if (!token) return;

    setProfileSaving(true);
    setProfileError("");

    try {
      const payload = {
        name: profileForm.name,
        age: profileForm.age ? Number(profileForm.age) : null,
        gender: profileForm.gender || null,
        state: profileForm.state || null,
        occupation: profileForm.occupation || null,
        income: profileForm.income ? Number(profileForm.income) : null,
        category: profileForm.category || null,
        disability: profileForm.disability,
        student_status: profileForm.student_status,
        farmer_status: profileForm.farmer_status,
      };

      const res = await fetch("/auth/profile", {
        method: "PUT",
        headers: authHeaders(token),
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const raw = await res.text();
        throw new Error(raw || "Failed to update profile");
      }

      const updated = (await res.json()) as AppUserProfile;
      updateUser(updated);
      await loadRecommendations(token);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save profile";
      setProfileError(msg);
    } finally {
      setProfileSaving(false);
    }
  }

  async function handleFindEligible() {
    setEligibleLoading(true);
    try {
      const payload = {
        age: profileForm.age ? Number(profileForm.age) : null,
        gender: profileForm.gender || null,
        state: profileForm.state || null,
        occupation: profileForm.occupation || null,
        income: profileForm.income ? Number(profileForm.income) : null,
        category: profileForm.category || null,
        disability: profileForm.disability,
        student_status: profileForm.student_status,
        farmer_status: profileForm.farmer_status,
        top_k: 10,
      };

      const res = await fetch("/api/find-eligible", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error("Failed to evaluate eligibility");
      const data = (await res.json()) as Scheme[];
      setEligible(data);
    } catch {
      setEligible([]);
    } finally {
      setEligibleLoading(false);
    }
  }

  function nextMessageId(role: "u" | "a"): string {
    messageSeqRef.current += 1;
    const baseId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}-${messageSeqRef.current}`;
    return `${baseId}-${role}`;
  }

  async function handleChatSearch(q: string) {
    if (!q.trim()) return;

    setChatQuery("");

    const greetingPattern =
      /^\s*(hi+|hello+|hey+|howdy|good\s*(morning|afternoon|evening|day)|what('s| is) up|sup|greetings|namaste|help|what can you do|what do you do|who are you)\??[!.]?\s*$/i;
    if (greetingPattern.test(q.trim())) {
      const displayName = user?.name || "there";
      const greetingReply =
        `Hello, ${displayName}! 👋 I'm your Government Scheme Assistant. Here's what I can help you with:\n\n` +
        `• 🔍 Search for government schemes by topic (e.g. "scholarships for SC students")\n` +
        `• 🎯 Find schemes you're eligible for based on your profile\n` +
        `• 📋 Get detailed information about benefits, eligibility & how to apply\n` +
        `• 💬 Ask questions in plain language — I'll find the relevant scheme and explain it\n\n` +
        `Just type your question or topic to get started!`;
      const userMsgId = nextMessageId("u");
      const assistantMsgId = nextMessageId("a");
      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: "user", content: q },
        {
          id: assistantMsgId,
          role: "assistant",
          content: greetingReply,
        },
      ]);

      return;
    }

    const userMsgId = nextMessageId("u");
    const assistantMsgId = nextMessageId("a");

    // Capture history before adding the new exchange
    const historyForApi = messages
      .filter((m) => m.content.trim() && !m.streaming)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: q },
      { id: assistantMsgId, role: "assistant", content: "", streaming: true },
    ]);
    setChatLoading(true);

    try {
      const queryForBackend =
        chatLanguage !== "en"
          ? `Please answer in ${languageNames[chatLanguage]}. Question: ${q}`
          : q;

      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: queryForBackend,
          top_k: 5,
          history: historyForApi,
          conversation_id: conversationIdRef.current,
          language: chatLanguage,
        }),
      });

      if (!res.ok) {
        const raw = await res.text();
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? {
                  ...m,
                  content: raw || "Search failed",
                  streaming: false,
                  error: raw,
                }
              : m,
          ),
        );
        return;
      }

      setChatLoading(false);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;
          try {
            const event = JSON.parse(jsonStr) as {
              type: string;
              text?: string;
              data?: Scheme;
              value?: "direct_answer" | "no_data_prompt" | "relevant_schemes";
              data_list?: Scheme[];
            };
            if (event.type === "token" && event.text) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: m.content + event.text }
                    : m,
                ),
              );
            } else if (event.type === "response_type" && event.value) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        responseType: event.value,
                      }
                    : m,
                ),
              );
            } else if (event.type === "scheme" && event.data) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, scheme: event.data } : m,
                ),
              );
            } else if (
              event.type === "relevant_schemes" &&
              Array.isArray(event.data)
            ) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, relevantSchemes: event.data as Scheme[] }
                    : m,
                ),
              );
            } else if (event.type === "error" && event.text) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, error: event.text, streaming: false }
                    : m,
                ),
              );
            } else if (event.type === "done") {
              setMessages((prev) => {
                return prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, streaming: false } : m,
                );
              });
            }
          } catch {
            // ignore malformed SSE lines
          }
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Search failed";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: msg, streaming: false, error: msg }
            : m,
        ),
      );
    } finally {
      setChatLoading(false);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId ? { ...m, streaming: false } : m,
        ),
      );
    }
  }
  function renderAnswer(text: string) {
    return text.split("\n").map((line, i) => {
      if (!line.trim()) return <div key={i} className="h-2" />;
      const boldMatch = line.match(/^\*\*(.+?)\*\*:?\s*(.*)/);
      if (boldMatch) {
        return (
          <p key={i} className="mt-3 font-bold text-amber-800 text-sm">
            {boldMatch[1]}
            {boldMatch[2] ? ` — ${boldMatch[2]}` : ""}
          </p>
        );
      }
      if (/^[-•*]\s/.test(line)) {
        return (
          <div key={i} className="flex gap-2 mt-1 ml-3">
            <span className="text-amber-500 font-bold mt-0.5">▸</span>
            <span className="text-sm text-gray-800 leading-relaxed">
              {line.replace(/^[-•*]\s/, "")}
            </span>
          </div>
        );
      }
      return (
        <p key={i} className="mt-1 text-sm text-gray-800 leading-relaxed">
          {line}
        </p>
      );
    });
  }

  function logout() {
    clearSession();
    setRecommendations([]);
    setEligible([]);
    setMessages([]);
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
        <section className="w-full max-w-lg bg-white rounded-2xl border border-orange-100 shadow-xl p-7">
          <h1 className="text-2xl font-extrabold text-gray-800 text-center">
            Government Scheme Assistant
          </h1>
          <p className="text-sm text-gray-500 text-center mt-2">
            {authMode === "login"
              ? "Login to access your personalized dashboard"
              : "Create account and get personalized scheme recommendations"}
          </p>

          <form onSubmit={handleAuthSubmit} className="mt-6 space-y-3">
            {authMode === "signup" && (
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Full name"
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5"
                required
              />
            )}
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5"
              required
            />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              type="password"
              className="w-full border border-gray-300 rounded-lg px-4 py-2.5"
              required
            />
            {authMode === "signup" && (
              <p className="text-xs text-gray-500 leading-relaxed">
                Password rules: at least 8 characters, 1 uppercase letter, 1
                number, and 1 special character.
              </p>
            )}
            {authError && <p className="text-sm text-red-600">{authError}</p>}
            <button
              type="submit"
              disabled={authLoading}
              className="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-2.5 rounded-lg"
            >
              {authLoading
                ? "Please wait..."
                : authMode === "login"
                  ? "Login"
                  : "Create Account"}
            </button>
          </form>

          <button
            type="button"
            onClick={() => {
              setAuthMode(authMode === "login" ? "signup" : "login");
              setAuthError("");
            }}
            className="mt-4 text-sm text-blue-600 hover:underline"
          >
            {authMode === "login"
              ? "New user? Create account"
              : "Already have an account? Login"}
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-green-50">
      <header className="border-b border-orange-100 bg-white/90 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-5 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold text-gray-800">
              Government Scheme Assistant
            </h1>
            <p className="text-sm text-gray-500">
              Hello {greetingName} - personalized schemes for your profile
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/voice"
              className="text-sm px-4 py-2 rounded-lg border border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100"
            >
              Voice
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

      <section className="max-w-6xl mx-auto px-4 py-8 space-y-8">
        <section className="bg-white rounded-2xl border border-orange-100 shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-800">
            Recommended Schemes For You
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Based on your saved profile and eligibility conditions
          </p>

          {recommendLoading && (
            <p className="mt-4 text-gray-500">Loading recommendations...</p>
          )}
          {!recommendLoading && recommendations.length === 0 && (
            <p className="mt-4 text-gray-500">
              No recommendations yet. Complete your profile to improve results.
            </p>
          )}
          {!recommendLoading && recommendations.length > 0 && (
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {recommendations.map((scheme, i) => {
                const palettes = [
                  "border-blue-200 bg-blue-50 text-blue-800",
                  "border-emerald-200 bg-emerald-50 text-emerald-800",
                  "border-violet-200 bg-violet-50 text-violet-800",
                  "border-amber-200 bg-amber-50 text-amber-800",
                  "border-rose-200 bg-rose-50 text-rose-800",
                  "border-cyan-200 bg-cyan-50 text-cyan-800",
                ];
                const palette = palettes[i % palettes.length];
                return (
                  <div
                    key={`rec-${i}`}
                    className={`rounded-xl border px-4 py-3 ${palette}`}
                  >
                    <p className="text-sm font-semibold">
                      {scheme.scheme_name}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="bg-white rounded-2xl border border-orange-100 shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-800">
            Find Schemes For Me
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Update your details and run eligibility filtering instantly
          </p>

          <form
            onSubmit={handleProfileSave}
            className="mt-5 grid md:grid-cols-2 gap-3"
          >
            <input
              value={profileForm.name}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, name: e.target.value }))
              }
              placeholder="Name"
              className="border border-gray-300 rounded-lg px-3 py-2"
            />
            <input
              value={profileForm.age}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, age: e.target.value }))
              }
              placeholder="Age"
              type="number"
              className="border border-gray-300 rounded-lg px-3 py-2"
            />
            <input
              value={profileForm.income}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, income: e.target.value }))
              }
              placeholder="Annual income"
              type="number"
              className="border border-gray-300 rounded-lg px-3 py-2"
            />
            <input
              value={profileForm.gender}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, gender: e.target.value }))
              }
              placeholder="Gender"
              className="border border-gray-300 rounded-lg px-3 py-2"
            />
            <input
              value={profileForm.state}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, state: e.target.value }))
              }
              placeholder="State"
              className="border border-gray-300 rounded-lg px-3 py-2"
            />
            <input
              value={profileForm.occupation}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, occupation: e.target.value }))
              }
              placeholder="Occupation"
              className="border border-gray-300 rounded-lg px-3 py-2"
            />
            <input
              value={profileForm.category}
              onChange={(e) =>
                setProfileForm((p) => ({ ...p, category: e.target.value }))
              }
              placeholder="Category (SC/ST/OBC/General)"
              className="border border-gray-300 rounded-lg px-3 py-2 md:col-span-2"
            />

            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={profileForm.disability}
                onChange={(e) =>
                  setProfileForm((p) => ({
                    ...p,
                    disability: e.target.checked,
                  }))
                }
              />
              Disability
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={profileForm.student_status}
                onChange={(e) =>
                  setProfileForm((p) => ({
                    ...p,
                    student_status: e.target.checked,
                  }))
                }
              />
              Student status
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={profileForm.farmer_status}
                onChange={(e) =>
                  setProfileForm((p) => ({
                    ...p,
                    farmer_status: e.target.checked,
                  }))
                }
              />
              Farmer status
            </label>

            <div className="md:col-span-2 flex flex-wrap gap-3 mt-2">
              <button
                type="submit"
                disabled={profileSaving}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
              >
                {profileSaving ? "Saving..." : "Save Profile"}
              </button>
              <button
                type="button"
                onClick={() => void handleFindEligible()}
                disabled={eligibleLoading}
                className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg"
              >
                {eligibleLoading ? "Checking..." : "Find Eligible Schemes"}
              </button>
            </div>
            {profileError && (
              <p className="md:col-span-2 text-sm text-red-600">
                {profileError}
              </p>
            )}
          </form>

          <div className="mt-6 space-y-3">
            {eligible.length > 0 &&
              eligible.map((scheme, i) => (
                <SchemeCard key={`eligible-${i}`} scheme={scheme} />
              ))}
            {eligibleLoading && (
              <p className="text-gray-500">Checking eligibility...</p>
            )}
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-orange-100 shadow-sm p-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <h2 className="text-xl font-bold text-gray-800">
                {chatText.title}
              </h2>
              <p className="text-sm text-gray-500 mt-1">{chatText.subtitle}</p>
            </div>
            <div className="flex items-center gap-4 flex-wrap">
              <label
                htmlFor="lang-select"
                className="text-sm font-medium text-gray-700"
              >
                {chatText.language_label}
              </label>
              <select
                id="lang-select"
                value={chatLanguage}
                onChange={(e) =>
                  setChatLanguage(e.target.value as LanguageCode)
                }
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white hover:border-orange-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
              >
                {(Object.keys(languageNames) as LanguageCode[]).map((lang) => (
                  <option key={lang} value={lang}>
                    {languageNames[lang]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div
            ref={chatContainerRef}
            className="mt-5 space-y-4 max-h-[28rem] overflow-y-auto pr-1 scroll-smooth"
          >
            {messages.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-10">
                {chatText.empty}
              </p>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed"
                      : "bg-gray-50 border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 w-full"
                  }`}
                >
                  {msg.role === "user" ? (
                    <p>{msg.content}</p>
                  ) : (
                    <>
                      <div className="leading-relaxed">
                        {renderAnswer(msg.content)}
                        {msg.streaming && (
                          <span className="inline-block w-0.5 h-4 bg-amber-600 animate-pulse ml-0.5 align-middle" />
                        )}
                      </div>
                      {msg.error && (
                        <p className="text-red-500 text-xs mt-2">{msg.error}</p>
                      )}
                      {msg.scheme && (
                        <div className="mt-3">
                          <SchemeCard scheme={msg.scheme} />
                        </div>
                      )}
                      {msg.relevantSchemes &&
                        msg.relevantSchemes.length > 0 && (
                          <div className="mt-3 space-y-3">
                            {msg.relevantSchemes.map((scheme, i) => (
                              <SchemeCard
                                key={`${msg.id}-rel-${i}`}
                                scheme={scheme}
                              />
                            ))}
                          </div>
                        )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4">
            {isAwaitingYesNoFollowup && !isTypingYesNoReply && (
              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
                <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
                {chatText.awaiting_reply}
              </div>
            )}
            <SearchBar
              value={chatQuery}
              onChange={setChatQuery}
              onSearch={(q) => void handleChatSearch(q)}
              loading={chatLoading}
              placeholder={chatText.search_placeholder}
              buttonText={chatText.search_btn}
              loadingText={chatText.searching}
              ariaLabel={chatText.search_aria}
            />
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-orange-100 shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-800">Browse Schemes</h2>
          <p className="text-sm text-gray-500 mt-1">
            Explore top scheme categories manually
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            {categories.map((item) => (
              <span
                key={item.category}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 text-gray-700 text-sm"
              >
                {item.category}
                <span className="text-xs text-gray-500">{item.count}</span>
              </span>
            ))}
            {categories.length === 0 && (
              <p className="text-gray-500">No categories available.</p>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}
