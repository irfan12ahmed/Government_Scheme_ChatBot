import json
import os
import re
import hmac
import hashlib
import secrets
import base64
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Generator, Optional
from urllib.parse import urlparse

import faiss
import joblib
import nltk
import numpy as np
import pandas as pd
import torch
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Force CPU execution for encoder loading/inference.
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
torch.cuda.is_available = lambda: False  # type: ignore

_orig_torch_load = torch.load  # type: ignore


def _cpu_torch_load(*args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("map_location", "cpu")
    kwargs.setdefault("weights_only", False)
    return _orig_torch_load(*args, **kwargs)


torch.load = _cpu_torch_load  # type: ignore

nltk.download("stopwords", quiet=True)
nltk.download("wordnet", quiet=True)
nltk.download("omw-1.4", quiet=True)

# ---- Paths ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
MODEL_DIR = os.path.join(ROOT_DIR, "model")
DATA_DIR = os.path.join(ROOT_DIR, "dataset")

# Load variables from backend/.env if present.
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---- Security ----
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Minimum FAISS similarity score to treat a candidate as a confident DB match.
# For IndexFlatIP (cosine similarity 0–1): values below this fall back to general LLM knowledge.
# Set to -1.0 to disable and always use the top DB result.
FAISS_MIN_SCORE = float(os.getenv("FAISS_MIN_SCORE", "0.2"))
CHAT_STATE_TTL_SECONDS = int(os.getenv("CHAT_STATE_TTL_SECONDS", "1800"))
NO_DATA_PROMPT = "sorry i dont have the data, can i give any relevent schemes for you"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ---- Database -------------------------------------------------------------------------------------------------------
# Use PostgreSQL in production by setting DATABASE_URL, for example:
# postgresql+psycopg2://postgres:password@localhost:5432/govt_schemes
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'app.db')}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    password_hash = Column(String(255), nullable=False)

    age = Column(Integer, nullable=True)
    gender = Column(String(50), nullable=True)
    state = Column(String(100), nullable=True)
    occupation = Column(String(100), nullable=True)
    income = Column(Float, nullable=True)
    category = Column(String(50), nullable=True)

    disability = Column(Boolean, default=False)
    student_status = Column(Boolean, default=False)
    farmer_status = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)

# ---- NLP + Model load--------------------------------------------------------
stop_words = set(stopwords.words("english"))
lemmatizer = WordNetLemmatizer()


def clean_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in stop_words]
    return " ".join(lemmatizer.lemmatize(t) for t in tokens)


print("Loading semantic encoder ...")
encoder = joblib.load(os.path.join(MODEL_DIR, "semantic_encoder.pkl"))

print("Loading FAISS index ...")
faiss_index = faiss.read_index(os.path.join(MODEL_DIR, "scheme_index.faiss"))

print("Loading dataset ...")
df = pd.read_csv(os.path.join(DATA_DIR, "govt_schemes.csv")).fillna("")
print(f"Ready - {len(df)} schemes loaded.")

# ---- FastAPI ----
app = FastAPI(title="Govt Scheme Assistant API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Pydantic schemas ----
class UserSignup(BaseModel):
    username: str
    name: str
    password: str

    age: Optional[int] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    occupation: Optional[str] = None
    income: Optional[float] = None
    category: Optional[str] = None

    disability: bool = False
    student_status: bool = False
    farmer_status: bool = False


class UserLogin(BaseModel):
    username: str
    password: str


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    occupation: Optional[str] = None
    income: Optional[float] = None
    category: Optional[str] = None
    disability: Optional[bool] = None
    student_status: Optional[bool] = None
    farmer_status: Optional[bool] = None


class UserPublic(BaseModel):
    id: int
    username: str
    name: str

    age: Optional[int]
    gender: Optional[str]
    state: Optional[str]
    occupation: Optional[str]
    income: Optional[float]
    category: Optional[str]

    disability: bool
    student_status: bool
    farmer_status: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class ChatRequest(BaseModel):
    query: str
    top_k: int = 1
    history: list[ConversationMessage] = []
    conversation_id: Optional[str] = None
    language: str = "en"


class EligibilityRequest(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    occupation: Optional[str] = None
    income: Optional[float] = None
    category: Optional[str] = None
    disability: bool = False
    student_status: bool = False
    farmer_status: bool = False
    top_k: int = 10


class SchemeResult(BaseModel):
    scheme_name: str
    details: str
    benefits: str
    eligibility: str
    application: str
    documents: str
    level: str
    schemeCategory: str
    tags: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SchemeResult]


class ChatResponse(BaseModel):
    query: str
    answer: str
    response_type: str = "direct_answer"
    source_scheme: Optional[SchemeResult] = None
    relevant_schemes: list[SchemeResult] = Field(default_factory=list)


class VoiceAssistantChatRequest(BaseModel):
    query: str
    language: str = "en"
    history: list[ConversationMessage] = Field(default_factory=list)


class VoiceAssistantChatResponse(BaseModel):
    query: str
    answer: str
    language: str = "en"


class CategoryResponse(BaseModel):
    category: str
    count: int


class SpeechRequest(BaseModel):
    """Request for speech-to-text transcription or text-to-speech synthesis."""
    audio_base64: Optional[str] = None  # Base64-encoded audio for transcription
    text: Optional[str] = None  # Text to synthesize for TTS
    language: str = "en"  # Language code: en, hi, te, ta
    format: str = "wav"  # Audio format: wav, mp3, ogg


class SpeechResponse(BaseModel):
    """Response for speech operations."""
    success: bool
    data: Optional[str] = None  # Base64-encoded audio (TTS) or transcribed text (STT)
    error: Optional[str] = None
    language: str = "en"


class ChatState(BaseModel):
    pending_relevant_suggestions: bool = False
    last_query: str = ""
    updated_at: float = Field(default_factory=time.time)


chat_state_store: dict[str, ChatState] = {}

# ---- Speech/Audio Helpers ----
# Language to Whisper locale mapping for STT
SPEECH_LANGUAGE_MAP = {
    "en": "en",
    "hi": "hi",
    "te": "te",
    "ta": "ta",
}

# Language to gTTS language code mapping for TTS
TTS_LANGUAGE_MAP = {
    "en": "en",
    "hi": "hi",
    "te": "te",
    "ta": "ta",
}


def normalize_language_code(lang: str) -> str:
    """Normalize and validate language code, fallback to English if unsupported."""
    normalized = lang.strip().lower()
    if normalized in SPEECH_LANGUAGE_MAP:
        return normalized
    return "en"


def format_speech_error(error: str, language: str = "en") -> str:
    """Format error message for speech operations."""
    error_messages = {
        "en": "Speech processing failed. Try again or use text input.",
        "hi": "भाषण प्रसंस्करण विफल। पुनः प्रयास करें या पाठ इनपुट का उपयोग करें।",
        "te": "ఆడియో ప్రక్రియ విఫలమైంది. మళ్లీ ప్రయత్నించండి లేదా టెక్స్ట్ ఇన్‌పుట్‌ను ఉపయోగించండి.",
        "ta": "பேச்சு செயலாக்கம் தோல్வியடைந்தது. மீண்டும் முயற்சிக்கவும் அல்லது உரை உள்ளீட்டைப் பயன்படுத்தவும்.",
    }
    lang_normalized = normalize_language_code(language)
    return error_messages.get(lang_normalized, error_messages["en"])


# ---- Helpers ----
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    # Format: pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>
    iterations = 390000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, iterations_s, salt_b64, digest_b64 = hashed_password.split("$", 3)
            iterations = int(iterations_s)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected_digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
            computed_digest = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt,
                iterations,
            )
            return hmac.compare_digest(computed_digest, expected_digest)
        except Exception:
            return False

    # Backward compatibility for existing bcrypt hashes from previous versions.
    if hashed_password.startswith("$2"):
        try:
            import bcrypt

            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    return False


def ensure_password_length_limit(password: str) -> None:
    # bcrypt supports at most 72 bytes for the input password.
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password is too long. Please keep your password to 72 characters or fewer.",
        )


def ensure_password_policy(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long.",
        )

    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must include at least 1 uppercase letter.",
        )

    if not re.search(r"\d", password):
        raise HTTPException(
            status_code=400,
            detail="Password must include at least 1 number.",
        )

    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must include at least 1 special character.",
        )


def ensure_password_valid(password: str) -> None:
    ensure_password_length_limit(password)
    ensure_password_policy(password)


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def to_user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        name=user.name,
        age=user.age,
        gender=user.gender,
        state=user.state,
        occupation=user.occupation,
        income=user.income,
        category=user.category,
        disability=bool(user.disability),
        student_status=bool(user.student_status),
        farmer_status=bool(user.farmer_status),
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise unauthorized
    except JWTError as exc:
        raise unauthorized from exc

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise unauthorized
    return user


def profile_to_query(profile: EligibilityRequest) -> str:
    parts = []
    if profile.age is not None:
        parts.append(f"age {profile.age}")
    if profile.gender:
        parts.append(profile.gender)
    if profile.state:
        parts.append(profile.state)
    if profile.occupation:
        parts.append(profile.occupation)
    if profile.category:
        parts.append(profile.category)
    if profile.income is not None:
        parts.append(f"income {int(profile.income)}")
    if profile.student_status:
        parts.append("student")
    if profile.farmer_status:
        parts.append("farmer")
    if profile.disability:
        parts.append("disability")
    return " ".join(parts) if parts else "government welfare scheme"


def text_blob(row: pd.Series) -> str:
    return " ".join(
        [
            str(row.get("scheme_name", "")),
            str(row.get("details", "")),
            str(row.get("eligibility", "")),
            str(row.get("benefits", "")),
            str(row.get("schemeCategory", "")),
            str(row.get("tags", "")),
            str(row.get("level", "")),
        ]
    ).lower()


def parse_income_limit(text: str) -> Optional[float]:
    lowered = text.lower()
    patterns = [
        r"(?:income|annual income|family income)\s*(?:below|under|less than|upto|up to|not exceed(?:ing)?)\s*rs\.?\s*([\d,]+)",
        r"(?:income|annual income|family income)\s*(?:below|under|less than|upto|up to|not exceed(?:ing)?)\s*([\d,]+)",
    ]
    for pat in patterns:
        match = re.search(pat, lowered)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def age_is_eligible(user_age: Optional[int], text: str) -> bool:
    if user_age is None:
        return True
    lowered = text.lower()

    range_match = re.search(r"(\d{1,2})\s*(?:to|\-|–)\s*(\d{1,2})\s*year", lowered)
    if range_match:
        min_age = int(range_match.group(1))
        max_age = int(range_match.group(2))
        return min_age <= user_age <= max_age

    min_match = re.search(r"(?:above|greater than|minimum)\s*(\d{1,2})\s*year", lowered)
    if min_match and user_age < int(min_match.group(1)):
        return False

    max_match = re.search(r"(?:below|less than|maximum|up to|upto)\s*(\d{1,2})\s*year", lowered)
    if max_match and user_age > int(max_match.group(1)):
        return False

    return True


def gender_is_eligible(user_gender: Optional[str], text: str) -> bool:
    if not user_gender:
        return True

    g = user_gender.lower().strip()
    lowered = text.lower()
    female_only = any(k in lowered for k in ["women", "woman", "female", "girl"])
    male_only = any(k in lowered for k in ["male", "men", "boy"])

    if female_only and g not in ["female", "woman", "women", "f"]:
        return False
    if male_only and g not in ["male", "man", "men", "m"]:
        return False
    return True


def category_is_eligible(user_category: Optional[str], text: str) -> bool:
    if not user_category:
        return True

    lowered = text.lower()
    category = user_category.lower().strip()
    category_tokens = {
        "sc": ["sc", "scheduled caste"],
        "st": ["st", "scheduled tribe"],
        "obc": ["obc", "other backward"],
        "general": ["general", "unreserved"],
    }

    if category not in category_tokens:
        return True

    mentioned = any(token in lowered for values in category_tokens.values() for token in values)
    if not mentioned:
        return True

    return any(token in lowered for token in category_tokens[category])


def state_is_eligible(user_state: Optional[str], text: str) -> bool:
    if not user_state:
        return True

    lowered = text.lower()
    normalized_state = user_state.lower().strip()

    if any(k in lowered for k in ["all india", "pan india", "central sector", "nationwide"]):
        return True

    common_state_markers = [
        "andhra", "arunachal", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
        "haryana", "himachal", "jharkhand", "karnataka", "kerala", "madhya pradesh",
        "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha",
        "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
        "uttar pradesh", "uttarakhand", "west bengal", "delhi", "jammu", "ladakh",
    ]
    mentions_state = any(s in lowered for s in common_state_markers)
    if not mentions_state:
        return True

    return normalized_state in lowered


def occupation_is_eligible(profile: EligibilityRequest, text: str) -> bool:
    lowered = text.lower()

    if profile.student_status and any(k in lowered for k in ["student", "scholarship"]):
        return True
    if profile.farmer_status and any(k in lowered for k in ["farmer", "agriculture", "kisan"]):
        return True

    if profile.occupation:
        occ = profile.occupation.lower().strip()
        occupation_keywords = {
            "student": ["student", "scholarship"],
            "farmer": ["farmer", "agriculture", "kisan"],
            "worker": ["worker", "labor", "labour"],
        }
        if occ in occupation_keywords:
            return any(k in lowered for k in occupation_keywords[occ]) or "for all" in lowered
    return True


def income_is_eligible(user_income: Optional[float], text: str) -> bool:
    if user_income is None:
        return True
    limit = parse_income_limit(text)
    if limit is None:
        return True
    return user_income <= limit


def disability_is_eligible(is_disabled: bool, text: str) -> bool:
    lowered = text.lower()
    disability_targeted = any(k in lowered for k in ["disability", "disabled", "divyang", "pwd"])
    if disability_targeted and not is_disabled:
        return False
    return True


def is_eligible(profile: EligibilityRequest, row: pd.Series) -> bool:
    blob = text_blob(row)
    return (
        age_is_eligible(profile.age, blob)
        and gender_is_eligible(profile.gender, blob)
        and category_is_eligible(profile.category, blob)
        and state_is_eligible(profile.state, blob)
        and occupation_is_eligible(profile, blob)
        and income_is_eligible(profile.income, blob)
        and disability_is_eligible(profile.disability, blob)
    )


def row_to_result(row: pd.Series, score: float = 0.0) -> SchemeResult:
    return SchemeResult(
        scheme_name=str(row.get("scheme_name", "")),
        details=str(row.get("details", "")),
        benefits=str(row.get("benefits", "")),
        eligibility=str(row.get("eligibility", "")),
        application=str(row.get("application", "")),
        documents=str(row.get("documents", "")),
        level=str(row.get("level", "")),
        schemeCategory=str(row.get("schemeCategory", "")),
        tags=str(row.get("tags", "")),
        score=float(score),
    )


def semantic_candidates(query: str, top_k: int) -> list[tuple[int, float]]:
    cleaned = clean_text(query)
    embedding = encoder.encode([cleaned], convert_to_numpy=True).astype(np.float32)
    distances, indices = faiss_index.search(embedding, max(top_k, 1))

    out: list[tuple[int, float]] = []
    for score, idx in zip(distances[0], indices[0]):
        if 0 <= idx < len(df):
            out.append((int(idx), float(score)))
    return out


def build_scheme_context(scheme: pd.Series) -> str:
    return (
        f"Scheme Name: {str(scheme.get('scheme_name', ''))}\n"
        f"Details: {str(scheme.get('details', ''))}\n"
        f"Benefits: {str(scheme.get('benefits', ''))}\n"
        f"Eligibility: {str(scheme.get('eligibility', ''))}\n"
        f"How to Apply: {str(scheme.get('application', ''))}\n"
        f"Documents Required: {str(scheme.get('documents', ''))}\n"
        f"Level: {str(scheme.get('level', ''))}\n"
        f"Category: {str(scheme.get('schemeCategory', ''))}"
    )


_GROQ_SYSTEM_PROMPT = (
    "You are a helpful AI assistant specializing in Indian government welfare schemes. "
    "Your job is to help Indian citizens understand government schemes, their benefits, "
    "eligibility criteria, and how to apply for them. "
    "When scheme data is provided, base your answer primarily on that data. "
    "When no specific scheme data is provided, answer from your general knowledge of "
    "Indian government schemes. Always be concise, accurate, and practical. "
    "Structure answers with labeled sections when helpful: **Summary**, **Eligibility**, "
    "**Benefits**, **How to Apply**. Use bullet points starting with '- ' for lists."
)


def _build_groq_messages(
    query: str,
    history: list[ConversationMessage],
    scheme_context: Optional[str] = None,
) -> list[dict]:
    """Build Groq API chat messages including conversation history."""
    messages: list[dict] = [{"role": "system", "content": _GROQ_SYSTEM_PROMPT}]
    for msg in history[-8:]:
        role = msg.role if msg.role in ("user", "assistant") else "user"
        messages.append({"role": role, "content": msg.content})
    user_content = (
        f"Use the following scheme information to answer:\n\n{scheme_context}\n\nQuestion: {query}"
        if scheme_context
        else query
    )
    messages.append({"role": "user", "content": user_content})
    return messages


def generate_answer_with_groq(
    query: str,
    scheme: pd.Series,
    history: Optional[list[ConversationMessage]] = None,
) -> str:
    scheme_name = str(scheme.get("scheme_name", "this scheme"))
    fallback = (
        f"Based on the retrieved scheme ({scheme_name}), here is what I found. "
        f"Eligibility: {str(scheme.get('eligibility', 'Not specified'))}. "
        f"Benefits: {str(scheme.get('benefits', 'Not specified'))}."
    )

    if not GROQ_API_KEY:
        return fallback

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        context = build_scheme_context(scheme)
        groq_messages = _build_groq_messages(query, history or [], scheme_context=context)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=groq_messages,
            temperature=0.2,
        )
        message = completion.choices[0].message.content if completion.choices else None
        if message and message.strip():
            return message.strip()
        return fallback
    except Exception:
        return fallback


def _build_voice_assistant_messages(
    query: str,
    language: str,
    history: list[ConversationMessage],
) -> list[dict[str, str]]:
    language_map = {
        "en": "English",
        "hi": "Hindi",
        "te": "Telugu",
        "ta": "Tamil",
    }
    language_name = language_map.get(normalize_language_code(language), "English")

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are a voice assistant focused on Indian government schemes. "
                "Answer only from general knowledge and user-provided context. "
                "Do not claim data was fetched from any local dataset. "
                "Keep answers concise, practical, and easy to understand."
            ),
        }
    ]
    for msg in history[-8:]:
        role = msg.role if msg.role in ("user", "assistant") else "user"
        messages.append({"role": role, "content": msg.content})
    messages.append(
        {
            "role": "user",
            "content": f"Respond in {language_name}. User question: {query}",
        }
    )
    return messages


def generate_voice_assistant_answer_with_groq(
    query: str,
    language: str,
    history: Optional[list[ConversationMessage]] = None,
) -> str:
    fallback_by_lang = {
        "en": "I am unable to answer right now. Please try again.",
        "hi": "मैं अभी उत्तर देने में असमर्थ हूँ। कृपया फिर से प्रयास करें।",
        "te": "నేను ఇప్పుడు సమాధానం ఇవ్వలేకపోతున్నాను. దయచేసి మళ్లీ ప్రయత్నించండి.",
        "ta": "இப்போது பதிலளிக்க முடியவில்லை. தயவுசெய்து மீண்டும் முயற்சிக்கவும்.",
    }
    normalized_language = normalize_language_code(language)
    fallback = fallback_by_lang.get(normalized_language, fallback_by_lang["en"])

    if not GROQ_API_KEY:
        return fallback

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=_build_voice_assistant_messages(
                query=query,
                language=normalized_language,
                history=history or [],
            ),
            temperature=0.2,
        )
        message = completion.choices[0].message.content if completion.choices else None
        if message and message.strip():
            return message.strip()
        return fallback
    except Exception:
        return fallback


def get_personalized_schemes(profile: EligibilityRequest, top_k: int) -> list[SchemeResult]:
    profile_query = profile_to_query(profile)
    candidates = semantic_candidates(profile_query, top_k * 8)

    chosen: list[SchemeResult] = []
    seen: set[int] = set()

    for idx, score in candidates:
        if idx in seen:
            continue
        row = df.iloc[idx]
        if is_eligible(profile, row):
            chosen.append(row_to_result(row, score))
            seen.add(idx)
        if len(chosen) >= top_k:
            return chosen

    # Fallback: eligibility-only scan if semantic candidates are sparse.
    for idx, row in df.iterrows():
        if idx in seen:
            continue
        if is_eligible(profile, row):
            chosen.append(row_to_result(row, 0.0))
            seen.add(int(idx))
        if len(chosen) >= top_k:
            break

    return chosen


def profile_from_user(user: User, top_k: int) -> EligibilityRequest:
    return EligibilityRequest(
        age=user.age,
        gender=user.gender,
        state=user.state,
        occupation=user.occupation,
        income=user.income,
        category=user.category,
        disability=bool(user.disability),
        student_status=bool(user.student_status),
        farmer_status=bool(user.farmer_status),
        top_k=top_k,
    )


def _conversation_key(payload: ChatRequest) -> str:
    raw = (payload.conversation_id or "").strip()
    if raw:
        return raw[:120]
    return "anonymous"


def _cleanup_chat_state() -> None:
    now = time.time()
    expired = [
        key
        for key, value in chat_state_store.items()
        if (now - value.updated_at) > CHAT_STATE_TTL_SECONDS
    ]
    for key in expired:
        del chat_state_store[key]


def _get_chat_state(conversation_key: str) -> ChatState:
    _cleanup_chat_state()
    state = chat_state_store.get(conversation_key)
    if not state:
        state = ChatState()
        chat_state_store[conversation_key] = state
    return state


def _save_chat_state(conversation_key: str, state: ChatState) -> None:
    state.updated_at = time.time()
    chat_state_store[conversation_key] = state


def detect_requested_section(query: str) -> Optional[str]:
    lowered = query.lower()
    section_patterns = {
        "eligibility": ["eligibility", "eligible", "who can apply", "am i eligible"],
        "application": ["how to apply", "apply", "application process", "steps to apply"],
        "benefits": ["benefits", "advantage", "what do i get"],
        "documents": ["documents", "document required", "papers required"],
        "details": ["details", "about this scheme", "overview", "what is this"],
    }
    for section, patterns in section_patterns.items():
        if any(pattern in lowered for pattern in patterns):
            return section
    return None


def is_yes_reply(query: str) -> bool:
    return bool(re.match(r"^\s*(yes|y|yeah|yep|sure|ok|okay|haan|han|ji)\s*[.!?]*\s*$", query.lower()))


def is_no_reply(query: str) -> bool:
    return bool(re.match(r"^\s*(no|n|nope|nah|nahi|na)\s*[.!?]*\s*$", query.lower()))


def _section_value(scheme: pd.Series, section: str) -> str:
    section_map = {
        "eligibility": str(scheme.get("eligibility", "Not specified")),
        "application": str(scheme.get("application", "Not specified")),
        "benefits": str(scheme.get("benefits", "Not specified")),
        "documents": str(scheme.get("documents", "Not specified")),
        "details": str(scheme.get("details", "Not specified")),
    }
    return section_map.get(section, str(scheme.get("details", "Not specified")))


def build_section_only_answer(scheme: pd.Series, section: str) -> str:
    label_map = {
        "eligibility": "Eligibility",
        "application": "How to Apply",
        "benefits": "Benefits",
        "documents": "Documents Required",
        "details": "Details",
    }
    label = label_map.get(section, "Details")
    return (
        f"**Scheme:** {str(scheme.get('scheme_name', 'N/A'))}\n\n"
        f"**{label}**\n{_section_value(scheme, section)}"
    )


def _is_allowed_web_source(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    allowed_suffixes = ("gov.in", "nic.in", "india.gov.in", "mygov.in")
    return any(hostname.endswith(suffix) for suffix in allowed_suffixes)


def web_search_relevant_schemes(query: str, limit: int = 5) -> list[SchemeResult]:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        return []

    max_needed = max(1, min(limit, 5))
    seen_names: set[str] = set()
    results: list[SchemeResult] = []

    try:
        with DDGS() as ddgs:
            raw_results = ddgs.text(
                f"{query} india government scheme official",
                max_results=20,
            )
            for rank, item in enumerate(raw_results, start=1):
                title = str(item.get("title", "")).strip()
                body = str(item.get("body", "")).strip()
                href = str(item.get("href", "")).strip()
                if not title or not href:
                    continue
                if not _is_allowed_web_source(href):
                    continue
                normalized_name = title.lower()
                if normalized_name in seen_names:
                    continue
                seen_names.add(normalized_name)

                results.append(
                    SchemeResult(
                        scheme_name=title,
                        details=body or "Found from official web source.",
                        benefits="Refer official source for confirmed benefits.",
                        eligibility="Refer official source for confirmed eligibility.",
                        application=href,
                        documents="Check official portal for required documents.",
                        level="",
                        schemeCategory="Web",
                        tags="web,official",
                        score=float(max(0.0, 1.0 - (rank - 1) * 0.05)),
                    )
                )
                if len(results) >= max_needed:
                    break
    except Exception:
        return []

    return results


def get_db_relevant_schemes(query: str, limit: int = 5) -> list[SchemeResult]:
    max_needed = max(1, min(limit, 5))
    candidates = semantic_candidates(query, max(max_needed * 8, 20))
    out: list[SchemeResult] = []
    seen: set[int] = set()
    for idx, score in candidates:
        if idx in seen:
            continue
        if score < FAISS_MIN_SCORE:
            continue
        out.append(row_to_result(df.iloc[idx], score))
        seen.add(idx)
        if len(out) >= max_needed:
            break
    return out


def summarize_web_schemes_with_groq(query: str, schemes: list[SchemeResult]) -> str:
    if not schemes:
        return "Sorry, I could not find relevant schemes right now."

    fallback = f"I found {len(schemes)} relevant schemes from official web sources."
    if not GROQ_API_KEY:
        return fallback

    snippet_lines = []
    for item in schemes[:5]:
        snippet_lines.append(
            f"- {item.scheme_name}: {item.details[:180]} (Source: {item.application})"
        )
    snippets = "\n".join(snippet_lines)

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize government scheme web search findings. "
                        "Be concise and do not add information outside provided snippets."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {query}\n\n"
                        f"Web snippets:\n{snippets}\n\n"
                        "Write a short response in 2-3 lines before listing schemes."
                    ),
                },
            ],
            temperature=0.2,
        )
        message = completion.choices[0].message.content if completion.choices else None
        if message and message.strip():
            return message.strip()
    except Exception:
        return fallback

    return fallback


# ---- Endpoints ----
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "total_schemes": len(df),
        "database": "connected",
    }


@app.post("/api/audio/transcribe", response_model=SpeechResponse)
def transcribe_audio(payload: SpeechRequest) -> SpeechResponse:
    """Convert audio (base64-encoded) to text using Whisper STT."""
    import base64
    import tempfile
    import os
    
    try:
        if not payload.audio_base64:
            raise ValueError("No audio data provided")
        
        language = normalize_language_code(payload.language)
        
        # Decode base64 audio
        try:
            audio_bytes = base64.b64decode(payload.audio_base64)
        except Exception as e:
            raise ValueError(f"Invalid base64 audio: {str(e)}")
        
        if len(audio_bytes) == 0:
            raise ValueError("Audio data is empty")
        
        # Write to temporary file
        audio_ext = payload.format if payload.format in ["wav", "mp3", "ogg"] else "wav"
        with tempfile.NamedTemporaryFile(suffix=f".{audio_ext}", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            # Use Whisper for transcription
            import whisper
            model = whisper.load_model("base", device="cpu")
            result = model.transcribe(tmp_path, language=SPEECH_LANGUAGE_MAP.get(language, "en"))
            transcribed_text = result.get("text", "").strip()
            
            if not transcribed_text:
                raise ValueError("No speech detected in audio")
            
            return SpeechResponse(
                success=True,
                data=transcribed_text,
                language=language,
            )
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        error_msg = str(e)
        return SpeechResponse(
            success=False,
            data=None,
            error=format_speech_error(error_msg, payload.language),
            language=normalize_language_code(payload.language),
        )


@app.post("/api/audio/synthesize", response_model=SpeechResponse)
def synthesize_audio(payload: SpeechRequest) -> SpeechResponse:
    """Convert text to speech (base64-encoded audio) using gTTS."""
    import base64
    import tempfile
    import os
    
    try:
        if not payload.text or not payload.text.strip():
            raise ValueError("No text provided for synthesis")
        
        language = normalize_language_code(payload.language)
        tts_lang = TTS_LANGUAGE_MAP.get(language, "en")
        
        try:
            from gtts import gTTS
        except ImportError:
            raise ValueError("gTTS library not installed")
        
        # Generate speech using gTTS
        tts = gTTS(text=payload.text, lang=tts_lang, slow=False)
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        tts.save(tmp_path)
        
        try:
            # Read and encode to base64
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
            
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            
            return SpeechResponse(
                success=True,
                data=audio_base64,
                language=language,
            )
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    except Exception as e:
        error_msg = str(e)
        return SpeechResponse(
            success=False,
            data=None,
            error=format_speech_error(error_msg, payload.language),
            language=normalize_language_code(payload.language),
        )


@app.post("/auth/signup", response_model=TokenResponse)
def signup(payload: UserSignup, db: Session = Depends(get_db)) -> TokenResponse:
    ensure_password_valid(payload.password)
    existing = db.query(User).filter(User.username == payload.username.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=payload.username.strip(),
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        age=payload.age,
        gender=payload.gender,
        state=payload.state,
        occupation=payload.occupation,
        income=payload.income,
        category=payload.category,
        disability=payload.disability,
        student_status=payload.student_status,
        farmer_status=payload.farmer_status,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.username)
    return TokenResponse(access_token=token, user=to_user_public(user))


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    ensure_password_length_limit(payload.password)
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user.username)
    return TokenResponse(access_token=token, user=to_user_public(user))


@app.get("/auth/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return to_user_public(current_user)


@app.put("/auth/profile", response_model=UserPublic)
def update_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(current_user, key, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return to_user_public(current_user)


@app.post("/api/search", response_model=SearchResponse)
def search_schemes(payload: SearchRequest) -> SearchResponse:
    candidates = semantic_candidates(payload.query, payload.top_k)
    results = [row_to_result(df.iloc[idx], score) for idx, score in candidates]
    return SearchResponse(query=payload.query, results=results)


@app.post("/api/voice-assistant/chat", response_model=VoiceAssistantChatResponse)
def voice_assistant_chat(payload: VoiceAssistantChatRequest) -> VoiceAssistantChatResponse:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    language = normalize_language_code(payload.language)
    answer = generate_voice_assistant_answer_with_groq(
        query=query,
        language=language,
        history=payload.history,
    )

    return VoiceAssistantChatResponse(
        query=query,
        answer=answer,
        language=language,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    conversation_key = _conversation_key(payload)
    state = _get_chat_state(conversation_key)
    query = payload.query.strip()

    if state.pending_relevant_suggestions and is_no_reply(query):
        state.pending_relevant_suggestions = False
        _save_chat_state(conversation_key, state)
        return ChatResponse(
            query=payload.query,
            answer="No problem. Ask me about any other scheme whenever you want.",
            response_type="direct_answer",
            source_scheme=None,
        )

    if state.pending_relevant_suggestions and is_yes_reply(query):
        db_results = get_db_relevant_schemes(state.last_query or payload.query, limit=5)
        used_web = False
        relevant = db_results
        if not relevant:
            relevant = web_search_relevant_schemes(state.last_query or payload.query, limit=5)
            used_web = True
        state.pending_relevant_suggestions = False
        _save_chat_state(conversation_key, state)
        if relevant:
            answer = (
                summarize_web_schemes_with_groq(state.last_query or payload.query, relevant)
                if used_web
                else f"Here are {len(relevant)} relevant schemes for you."
            )
            return ChatResponse(
                query=payload.query,
                answer=answer,
                response_type="relevant_schemes",
                source_scheme=None,
                relevant_schemes=relevant,
            )
        return ChatResponse(
            query=payload.query,
            answer="Sorry, I could not find relevant schemes right now.",
            response_type="direct_answer",
            source_scheme=None,
        )

    candidates = semantic_candidates(query, max(payload.top_k, 5))
    has_confident_match = bool(candidates) and candidates[0][1] >= FAISS_MIN_SCORE
    if not has_confident_match:
        state.pending_relevant_suggestions = True
        state.last_query = query
        _save_chat_state(conversation_key, state)
        return ChatResponse(
            query=payload.query,
            answer=NO_DATA_PROMPT,
            response_type="no_data_prompt",
            source_scheme=None,
        )

    idx, score = candidates[0]
    scheme = df.iloc[idx]
    requested_section = detect_requested_section(query)
    if requested_section:
        answer = build_section_only_answer(scheme, requested_section)
    else:
        answer = generate_answer_with_groq(payload.query, scheme, history=payload.history)

    state.pending_relevant_suggestions = False
    _save_chat_state(conversation_key, state)
    return ChatResponse(
        query=payload.query,
        answer=answer,
        response_type="direct_answer",
        source_scheme=row_to_result(scheme, score),
    )


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    conversation_key = _conversation_key(payload)
    state = _get_chat_state(conversation_key)
    query = payload.query.strip()

    if state.pending_relevant_suggestions and is_no_reply(query):
        state.pending_relevant_suggestions = False
        _save_chat_state(conversation_key, state)

        def no_followup_gen() -> Generator[str, None, None]:
            yield f"data: {json.dumps({'type': 'response_type', 'value': 'direct_answer'})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'text': 'No problem. Ask me about any other scheme whenever you want.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(no_followup_gen(), media_type="text/event-stream")

    if state.pending_relevant_suggestions and is_yes_reply(query):
        db_results = get_db_relevant_schemes(state.last_query or payload.query, limit=5)
        used_web = False
        relevant = db_results
        if not relevant:
            relevant = web_search_relevant_schemes(state.last_query or payload.query, limit=5)
            used_web = True
        state.pending_relevant_suggestions = False
        _save_chat_state(conversation_key, state)

        def yes_followup_gen() -> Generator[str, None, None]:
            if relevant:
                lead_text = (
                    summarize_web_schemes_with_groq(state.last_query or payload.query, relevant)
                    if used_web
                    else f"Here are {len(relevant)} relevant schemes for you."
                )
                yield f"data: {json.dumps({'type': 'response_type', 'value': 'relevant_schemes'})}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'text': lead_text})}\n\n"
                yield f"data: {json.dumps({'type': 'relevant_schemes', 'data': [item.model_dump() for item in relevant]})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'response_type', 'value': 'direct_answer'})}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'text': 'Sorry, I could not find relevant schemes right now.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(yes_followup_gen(), media_type="text/event-stream")

    candidates = semantic_candidates(query, max(payload.top_k, 5))
    has_confident_match = bool(candidates) and candidates[0][1] >= FAISS_MIN_SCORE

    if not has_confident_match:
        state.pending_relevant_suggestions = True
        state.last_query = query
        _save_chat_state(conversation_key, state)

        def no_data_gen() -> Generator[str, None, None]:
            yield f"data: {json.dumps({'type': 'response_type', 'value': 'no_data_prompt'})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'text': NO_DATA_PROMPT})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(no_data_gen(), media_type="text/event-stream")

    idx, score = candidates[0]
    scheme = df.iloc[idx]
    source_scheme = row_to_result(scheme, score)
    scheme_event = f"data: {json.dumps({'type': 'scheme', 'data': source_scheme.model_dump()})}\n\n"
    requested_section = detect_requested_section(query)

    def stream_gen() -> Generator[str, None, None]:
        yield f"data: {json.dumps({'type': 'response_type', 'value': 'direct_answer'})}\n\n"
        if requested_section:
            section_answer = build_section_only_answer(scheme, requested_section)
            yield f"data: {json.dumps({'type': 'token', 'text': section_answer})}\n\n"
            yield scheme_event
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        if not GROQ_API_KEY:
            fallback = (
                f"**Scheme:** {str(scheme.get('scheme_name', 'N/A'))}\n\n"
                f"**Eligibility**\n{str(scheme.get('eligibility', 'Not specified'))}\n\n"
                f"**Benefits**\n{str(scheme.get('benefits', 'Not specified'))}\n\n"
                f"**How to Apply**\n{str(scheme.get('application', 'Not specified'))}"
            )
            yield f"data: {json.dumps({'type': 'token', 'text': fallback})}\n\n"
            yield scheme_event
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        try:
            from groq import Groq

            client = Groq(api_key=GROQ_API_KEY)
            context = build_scheme_context(scheme)
            groq_messages = _build_groq_messages(
                payload.query, payload.history, scheme_context=context
            )
            groq_stream = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=groq_messages,
                temperature=0.2,
                stream=True,
            )
            for chunk in groq_stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield f"data: {json.dumps({'type': 'token', 'text': delta})}\n\n"
            yield scheme_event
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    state.pending_relevant_suggestions = False
    _save_chat_state(conversation_key, state)
    return StreamingResponse(stream_gen(), media_type="text/event-stream")


@app.post("/api/find-eligible", response_model=list[SchemeResult])
def find_eligible(payload: EligibilityRequest) -> list[SchemeResult]:
    return get_personalized_schemes(payload, top_k=payload.top_k)


@app.get("/api/recommendations", response_model=list[SchemeResult])
def recommendations(
    top_k: int = Query(default=6, ge=1, le=25),
    current_user: User = Depends(get_current_user),
) -> list[SchemeResult]:
    profile = profile_from_user(current_user, top_k=top_k)
    return get_personalized_schemes(profile, top_k=top_k)


@app.get("/api/categories", response_model=list[CategoryResponse])
def categories() -> list[CategoryResponse]:
    categories_series = df.get("schemeCategory", pd.Series(dtype=str)).astype(str)
    cleaned = categories_series[categories_series.str.strip() != ""]
    counts = cleaned.value_counts().head(15)
    return [CategoryResponse(category=str(cat), count=int(cnt)) for cat, cnt in counts.items()]
