# 🤖 Cloud-Hosted LinkedIn Automation & GitHub Dev Vlog Agent

An autonomous, cloud-ready LinkedIn content generation & developer vlog workflow powered by **NVIDIA NIM AI (Kimi-k3 model)**, **Unsplash REST API**, **GitHub API Deep Code Inspection**, **Flask + Gunicorn**, and **LinkedIn REST API v2**.

---

## 🏗️ System Architecture & Workflow

```text
┌─────────────────────────┐      ┌───────────────────────────┐      ┌───────────────────────────────┐
│ GitHub Actions / Cron   │ ───> │ Render Cloud Microservice │ ───> │ GitHub API Code & README      │
│  (Daily Auto-Schedule)  │      │   (Flask / Gunicorn)      │      │ Deep Repository Inspection    │
└─────────────────────────┘      └─────────────┬─────────────┘      └───────────────┬───────────────┘
                                               │                                    │
                                               │                                    ▼
                                               │                        ┌──────────────────────┐
                                               ├──────────────────────> │ NVIDIA NIM API       │
                                               │                        │ (Moonshot Kimi-k3)   │
                                               │                        └──────────┬───────────┘
                                               │                                   │
                                               │                                   ▼
                                               │                        ┌──────────────────────┐
                                               │                        │ Unsplash REST API    │
                                               │                        │ (Refined Tech Search)│
                                               │                        └──────────┬───────────┘
                                               │                                   │
                                               ▼                                   ▼
                                  ┌─────────────────────────────┐      ┌──────────────────────┐
                                  │ 1-Tap Post Approval URL     │ ───> │ LinkedIn REST API v2 │
                                  │ (Async Non-Blocking Email)  │      │ (Text or Media Post) │
                                  └─────────────────────────────┘      └──────────────────────┘
```

---

## 🚀 Key Features & Stack

- **🧠 Deep Code & Model Intelligence**:
  - Automatically fetches commit history, `README.md`, and source code (`app.py`, `package.json`, `Dockerfile`) directly via GitHub API.
  - Dynamically extracts and details the exact **AI Models** (`moonshotai/kimi-k3`), **APIs**, and **tech stack** without hardcoding.
- **🖼️ Smart Visual & Text-Only Fallback**:
  - Converts keywords into curated software developer search terms (`software developer dark workspace`) to prevent unrelated images.
  - Automatically falls back to clean, professional **text-only LinkedIn posts** if images are skipped or unavailable.
- **⚡ Asynchronous Cloud Microservice**:
  - Hosted on **Render.com** with **Gunicorn** and non-blocking background threads for SMTP notifications to guarantee sub-second HTTP response times without worker timeouts.
- **🔐 Stateless Security & Persistent Storage**:
  - Uses signed JSON tokens and `API_SECRET` headers to prevent unauthorized post triggers.
- **⏰ Autonomous Daily Execution**:
  - Integrated with **GitHub Actions** (`.github/workflows/daily_post.yml`) to generate dev logs automatically every day.

---

## 🛠️ Technologies Used

| Category | Technology / API |
| :--- | :--- |
| **Core Engine** | Python 3.14 / Flask / Gunicorn |
| **AI Post Generation** | NVIDIA NIM API (`moonshotai/kimi-k3`) |
| **Visual Media** | Unsplash REST API (`api.unsplash.com`) |
| **Publishing Platform** | LinkedIn REST API v2 (`/rest/posts` & `/rest/images`) |
| **Code Inspection** | GitHub REST API v3 |
| **Container & Cloud** | Render.com / Docker / GitHub Actions |

---

## 🔑 Environment Variables Setup

Create a `.env` file in the root directory:

```env
# NVIDIA NIM AI Configuration
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_MODEL=moonshotai/kimi-k3

# Unsplash Image API
UNSPLASH_ACCESS_KEY=your-unsplash-access-key

# LinkedIn OAuth API Credentials
LINKEDIN_ACCESS_TOKEN=your-linkedin-access-token
AUTHOR_URN=urn:li:person:YOUR_LINKEDIN_MEMBER_ID

# Gmail SMTP Email Notification (App Password)
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-gmail-app-password
RECIPIENT_EMAIL=recipient-email@gmail.com

# GitHub API & Remote Server Config
GITHUB_USERNAME=Uttham4
GITHUB_TOKEN=ghp_your_github_personal_access_token
SERVER_BASE_URL=https://linkedin-automation-xav0.onrender.com
API_SECRET=your-secure-random-api-secret
```

---

## 🌐 API Endpoints

### 1. Trigger GitHub Developer Vlog
Analyzes recent commits and repository code to generate a project update post:
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/trigger-github \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: your-secure-random-api-secret" \
  -d '{"force_latest": true}'
```

### 2. Trigger Custom Topic Post
Generates a post on any custom technical topic:
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/trigger-generation \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: your-secure-random-api-secret" \
  -d '{"topic": "Autonomous AI Agents & Cloud Microservices"}'
```

### 3. Approve & Publish Post
Publishes the pending post draft to LinkedIn:
```text
GET https://linkedin-automation-xav0.onrender.com/approve?post_id=<POST_ID>
```

---

## ☁️ Cloud Deployment (Render / Docker)

1. Connect your GitHub repository to **Render.com**.
2. Select **Web Service** with runtime **Docker** or **Python 3**.
3. Add environment variables in the Render Dashboard.
4. Deployment builds automatically using `Procfile` and `render.yaml`.

---

## 🤝 Contributing

Contributions, feedback, and pull requests are welcome! Feel free to star ⭐ the repository.

*🤖 Auto-generated Dev Log System | Built with Python, NVIDIA NIM, and Cloud Microservices.*
