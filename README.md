# 🏛️ YOJANABOT - Government Scheme Chatbot

An AI-powered Government Scheme Recommendation Platform that helps citizens discover, understand, and verify Central and State Government schemes through personalized recommendations, semantic search, and conversational AI.

The application combines **FAISS Semantic Search**, **Rule-Based Eligibility Checking**, and **Retrieval-Augmented Generation (RAG)** using **Groq LLM** to provide accurate, multilingual, and context-aware responses.

> **Project Status:** Completed ✅

---

# 🚀 Core Features

### 🤖 AI-Powered Chatbot
- Conversational chatbot powered by **Groq LLM**
- Uses **Retrieval-Augmented Generation (RAG)** for grounded responses
- Supports real-time streaming responses with a typewriter effect

### 🎯 Personalized Recommendations
- Recommends government schemes based on the user's profile
- Combines semantic search with eligibility rules
- Filters schemes using:
  - Age
  - Gender
  - State
  - Occupation
  - Income
  - Category
  - Disability
  - Student/Farmer status

### 🔍 Semantic Search
- Uses **FAISS Vector Search**
- Sentence Transformer embeddings
- Returns the most relevant government schemes instead of keyword matching

### ✅ Eligibility Checker
Users can instantly check which schemes they are eligible for without creating an account.

### 🌐 Web Search Fallback
If no matching scheme exists in the local dataset:

- Searches official **.gov.in** websites
- Retrieves trusted government information
- Summarizes results using Groq AI

### 🌍 Multilingual Support

Supports four languages:

- English
- Hindi
- Telugu
- Tamil

### 📂 Browse by Category

Explore schemes from categories such as:

- Agriculture
- Education
- Health
- Housing
- Employment
- Women Welfare
- Social Security

### 🔐 Secure Authentication

- JWT Authentication
- Password Hashing
- Protected APIs
- User Profile Management

### ⚡ Smart Follow-up Conversation

If no schemes are found:

- Chatbot asks whether to search the web
- Understands Yes/No responses
- Continues the conversation naturally

---

# 🛠 Tech Stack

## Frontend

- Next.js 15
- TypeScript
- Tailwind CSS

## Backend

- FastAPI
- Python
- SQLAlchemy
- SQLite

## AI & Machine Learning

- Groq API
- Llama 3.3 70B
- FAISS
- Sentence Transformers
- Retrieval-Augmented Generation (RAG)

## Authentication

- JWT
- PBKDF2 Password Hashing

## Testing

- Pytest

---

# 📦 Project Structure

```
Government_Scheme_Chatbot/

│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── tests/
│   ├── .env
│   └── .env.example
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── public/
│   └── next.config.ts
│
├── dataset/
│   └── govt_schemes.csv
│
├── model/
│   ├── scheme_index.faiss
│   ├── scheme_embeddings.npy
│   └── encoder.pkl
│
└── README.md
```

---

# 🚀 Getting Started

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- Groq API Key

---

# 1. Clone Repository

```bash
git clone https://github.com/yourusername/Government_Scheme_Chatbot.git

cd Government_Scheme_Chatbot
```

---

# 2. Backend Setup

Create virtual environment

```bash
python -m venv venv
```

Activate

### Windows

```bash
venv\Scripts\activate
```

Install dependencies

```bash
pip install -r backend/requirements.txt
```

Copy environment file

```bash
cp backend/.env.example backend/.env
```

Example

```env
JWT_SECRET=your_secret_key

GROQ_API_KEY=your_groq_api_key

GROQ_MODEL=llama-3.3-70b-versatile
```

Run backend

```bash
uvicorn backend.main:app --reload
```

---

# 3. Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

---

# Application URLs

Frontend

```
http://localhost:3000
```

Backend

```
http://localhost:8000
```

---

# 📚 API Endpoints

## Authentication

| Method | Endpoint |
|---------|----------|
| POST | /auth/signup |
| POST | /auth/login |
| GET | /auth/me |
| PUT | /auth/profile |

---

## Government Schemes

| Method | Endpoint |
|---------|----------|
| POST | /api/search |
| POST | /api/chat |
| POST | /api/chat/stream |
| POST | /api/find-eligible |
| GET | /api/recommendations |
| GET | /api/categories |

---

# 🧠 How It Works

```
                  User
                    │
                    ▼
          Next.js Frontend
                    │
                    ▼
             FastAPI Backend
                    │
        ┌───────────┴────────────┐
        │                        │
        ▼                        ▼
 User Authentication      User Profile
        │                        │
        └───────────┬────────────┘
                    ▼
         Recommendation Engine
                    │
                    ▼
        FAISS Semantic Search
                    │
                    ▼
      Government Scheme Dataset
                    │
                    ▼
             Groq LLM (RAG)
                    │
                    ▼
          AI Generated Response
```

---

# 🌍 Supported Languages

| Language | Support |
|----------|---------|
| English | ✅ |
| Hindi | ✅ |
| Telugu | ✅ |
| Tamil | ✅ |

---

# 🧪 Testing

Run all tests

```bash
pytest backend/tests -v
```

Generate coverage

```bash
pytest --cov=backend
```

---

# 📸 Screenshots

## Login Page

(Add Screenshot)

---

## Dashboard

(Add Screenshot)

---

## AI Chatbot

(Add Screenshot)

---

## Recommendations

(Add Screenshot)

---

## Eligibility Checker

(Add Screenshot)

---

# 🔮 Future Enhancements

- Voice-based chatbot
- OCR for government documents
- Mobile application
- AI-powered scheme comparison
- Personalized notifications
- Regional language expansion
- Admin dashboard
- User feedback and ratings

---

# 🤝 Contributing

Contributions are welcome!

1. Fork the repository

2. Create a new branch

```
git checkout -b feature-name
```

3. Commit changes

```
git commit -m "Added new feature"
```

4. Push

```
git push origin feature-name
```

5. Create Pull Request

---

# 📄 License

This project is licensed under the **MIT License**.

---

# 👨‍💻 Author

**Mohamed Dadapeer**

GitHub: https://github.com/MohamedDadapeer5/Government_Scheme_ChatBot

LinkedIn: https://www.linkedin.com/in/mohamed-dadapeer-637750343/

---

⭐ If you like this project, don't forget to **Star** the repository.
