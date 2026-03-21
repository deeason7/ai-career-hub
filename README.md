# 🚀 AI Career Hub

A production-grade, AI-powered career acceleration platform built with a senior-level engineering stack.

[![CI](https://github.com/YOUR_USERNAME/ai-career-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-career-hub/actions/workflows/ci.yml)
[![Deploy](https://github.com/YOUR_USERNAME/ai-career-hub/actions/workflows/deploy.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-career-hub/actions/workflows/deploy.yml)

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 👤 Multi-Resume Management | Upload, store, and switch between multiple resumes per user |
| 📝 AI Cover Letter Generator | RAG-based zero-hallucination generation using Ollama + FAISS |
| 🎯 ATS Score Analyzer | Keyword & semantic scoring against any job description |
| 🔍 Skill Gap Analysis | Identify missing skills and get upskilling recommendations |
| 🎙️ Interview Question Generator | Role-specific questions generated from your resume + JD |
| 📊 Application Tracker | Kanban-style job application pipeline |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                      Nginx                          │
│            (Reverse Proxy / SSL)                    │
└───────────┬─────────────────────────┬───────────────┘
            │                         │
     ┌──────▼──────┐          ┌───────▼──────┐
     │  Streamlit  │          │   FastAPI    │
     │  Frontend   │          │   Backend    │
     └─────────────┘          └──────┬───────┘
                                     │
               ┌─────────────────────┼────────────────┐
               │                     │                │
       ┌───────▼──────┐    ┌────────▼──────┐  ┌──────▼──────┐
       │  PostgreSQL  │    │     Redis     │  │   Ollama    │
       │  (Database)  │    │ (Task Queue)  │  │   (Local    │
       └──────────────┘    └───────┬───────┘  │    LLM)     │
                                   │          └─────────────┘
                          ┌────────▼──────┐
                          │  Celery Worker│
                          │  (Async AI    │
                          │   Tasks)      │
                          └───────────────┘
```

---

## 🛠️ Tech Stack

**Backend:** FastAPI · SQLModel · PostgreSQL · Alembic · Celery · Redis  
**AI/ML:** Ollama (LLaMA 3.2) · LangChain · FAISS · nomic-embed-text  
**Frontend:** Streamlit  
**Infrastructure:** Docker · Docker Compose · Nginx  
**CI/CD:** GitHub Actions → Render.com  

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Git
- [Ollama](https://ollama.com) installed locally (for AI features)

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/ai-career-hub.git
cd ai-career-hub
```

### 2. Set up environment variables
```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your values
```

### 3. Start everything
```bash
docker compose up --build
```

### 4. Access the app
| Service | URL |
|---------|-----|
| Frontend (Streamlit) | http://localhost:8501 |
| Backend API (Swagger) | http://localhost:8000/docs |
| Flower (Celery UI) | http://localhost:5555 |

---

## 🌿 Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production. Protected. Auto-deploys to Render. |
| `develop` | Integration. Feature PRs merge here first. |
| `feature/*` | New features (e.g. `feature/ats-scorer`) |
| `release/*` | Release candidates (e.g. `release/v1.0`) |
| `hotfix/*` | Emergency production fixes |

---

## 🧪 Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v --tb=short
```

> **Note:** Tests use real services (PostgreSQL, Redis) via Docker. Start them before running tests:
> ```bash
> docker compose up db redis -d
> ```

---

## 📦 Deployment (Render.com)

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full step-by-step instructions.

---

## 📐 API Documentation

Once running, full interactive API docs are available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## 🗺️ Roadmap

- [ ] LinkedIn job scraper integration
- [ ] Resume version diffing
- [ ] Email alert for application status changes
- [ ] OpenAI API fallback
- [ ] React/Next.js frontend upgrade

---

## 🤝 Contributing

1. Fork the repo
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit: `git commit -m 'feat: add amazing feature'`
4. Push: `git push origin feature/amazing-feature`
5. Open a Pull Request to `develop`

---

## 📄 License

MIT © 2026 AI Career Hub
