# 🤖 Cloud-Hosted LinkedIn Automation, GitHub Dev Vlog & AI Comment Reply Agent

An autonomous, cloud-ready LinkedIn content generation, developer vlog, and **AI-powered comment reply automation system** powered by **NVIDIA NIM AI (Kimi-k3 model)**, **Unsplash REST API**, **GitHub API Deep Code Inspection**, **Flask + Gunicorn**, and **LinkedIn REST API v2 (`socialActions` endpoints)**.

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
                                               │                        │ NVIDIA NIM API       │
                                               │                        │ (Moonshot Kimi-k3)   │
                                               │                        └──────────┬───────────┘
                                               │                                   │
                                               │                                   ▼
                                               │                        ┌──────────────────────┐
                                               │                        │ Unsplash REST API    │
                                               │                        │ (Refined Tech Search)│
                                               │                        └──────────┬───────────┘
                                               │                                   │
                                               │                                   ▼
                                               ▼                                   ▼
                                  ┌─────────────────────────────┐      ┌──────────────────────┐
                                  │ 1-Tap Post Approval URL     │ ───> │ LinkedIn REST API v2 │
                                  │ (Async Non-Blocking Email)  │      │ (Text or Media Post) │
                                  └─────────────────────────────┘      └──────────┬───────────┘
                                                                                  │
                                                                                  ▼
┌─────────────────────────┐      ┌───────────────────────────┐         ┌──────────────────────┐
│ Background Poll Daemon  │ ───> │ SQLite WAL Persistent     │ <────── │ LinkedIn Comments    │
│ (Multi-Worker Daemon)   │      │ Store (pending_comments)  │         │ /socialActions/      │
└─────────────────────────┘      └─────────────┬─────────────┘         └──────────────────────┘
                                               │
                                               ▼
                                 ┌───────────────────────────┐
                                 │ LLM Reply Generator       │
                                 │ (Injection & Spam Filter) │
                                 └─────────────┬─────────────┘
                                               │
                                               ▼
                                 ┌───────────────────────────┐
                                 │ Dual Mode Engine          │
                                 │ (Approval / Automatic)    │
                                 └───────────────────────────┘
```

---

## 🚀 Key Features & Stack

- **💬 AI-Powered LinkedIn Comment Reply Automation**:
  - Automatically fetches comments on published LinkedIn posts using official LinkedIn REST APIs (`socialActions/{urn}/comments`).
  - Generates warm, concise, professional, and contextual responses using LLM (`moonshotai/kimi-k3`).
  - **Language Matching**: Automatically detects and responds in the exact same language as the commenter.
- **🛡️ Multi-Layer Security & Prompt Injection Defense**:
  - Input truncation and HTML entity escaping on comment text.
  - Regex filtering for jailbreak directives (`ignore previous instructions`, `system override`, `dan mode`).
  - Active detection for spam, crypto scams, and malicious links.
  - Strict system prompt separation with `<untrusted_comment>` boundary tags to prevent persona hijack.
- **⚙️ Dual Reply Modes & Global Safety Controls**:
  - **Approval Mode (Default)**: Holds generated replies in `pending_approval` for human review before publishing.
  - **Automatic Mode**: Automatically publishes replies for safe comments when enabled.
  - **Global Kill Switch (`GLOBAL_AUTO_REPLY_DISABLED`)**: Emergency brake to instantly pause automatic publishing.
  - **Rate Limiting Guardrails**: Configurable hourly (`MAX_REPLIES_PER_HOUR=10`) and daily caps (`MAX_REPLIES_PER_DAY=50`).
- **⚡ Multi-Worker Concurrency & Transactional Persistence**:
  - Powered by **SQLite WAL (Write-Ahead Logging)** mode with atomic test-and-set UPDATE operations (`claim_pending_comment`).
  - Ensures multi-worker Gunicorn safety without duplicate reply generation or double-publishing.
- **🧠 Deep Code & Model Intelligence**:
  - Automatically fetches commit history, `README.md`, and source code directly via GitHub API.
  - Dynamically extracts tech stack details and AI models without hardcoding.

---

## 🔐 LinkedIn Developer Permissions & OAuth Scopes

To retrieve comments and post replies, your LinkedIn OAuth 2.0 Access Token requires the following official permission scopes:

| Feature | Required LinkedIn OAuth Scope | API Endpoint |
| :--- | :--- | :--- |
| **Publish LinkedIn Posts** | `w_member_social` or `w_organization_social` | `POST /rest/posts` |
| **Fetch Post Comments** | `r_member_social` or `r_social_actions` | `GET /rest/socialActions/{urn}/comments` |
| **Publish Comment Replies** | `w_member_social` or `w_social_actions` | `POST /rest/socialActions/{urn}/comments` |

---

## 🛠️ Environment Variables Setup

Create a `.env` file in the root directory:

```env
# NVIDIA NIM AI Configuration
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_MODEL=moonshotai/kimi-k3

# Unsplash Image API
UNSPLASH_ACCESS_KEY=your-unsplash-access-key

# LinkedIn OAuth API Credentials & Scopes (r_member_social, w_member_social)
LINKEDIN_ACCESS_TOKEN=your-linkedin-access-token
AUTHOR_URN=urn:li:person:YOUR_LINKEDIN_MEMBER_ID

# Gmail SMTP Email Notification (App Password)
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-gmail-app-password
RECIPIENT_EMAIL=recipient-email@gmail.com

# Server & Security Configuration
SERVER_BASE_URL=https://linkedin-automation-xav0.onrender.com
API_SECRET=your-secure-random-api-secret
PORT=5000

# Comment Reply Automation Configuration
COMMENT_REPLY_MODE=approval             # 'approval' (default) or 'auto'
AUTO_REPLY_ENABLED=false                # Set to true for automated reply publishing
GLOBAL_AUTO_REPLY_DISABLED=false        # Global kill switch (set to true to halt auto replies)
COMMENT_POLL_INTERVAL=300               # Background poll interval in seconds (default: 5 min)
MAX_REPLIES_PER_HOUR=10                 # Maximum allowed comment replies per hour
MAX_REPLIES_PER_DAY=50                  # Maximum allowed comment replies per day
```

---

## 🌐 API Endpoints

### 1. Trigger GitHub Developer Vlog
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/trigger-github \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: your-secure-random-api-secret" \
  -d '{"force_latest": true}'
```

### 2. List Comments & Suggested Replies
```bash
curl -X GET https://linkedin-automation-xav0.onrender.com/comments
```

### 3. Ingest Raw Comment (Webhook / Manual Test)
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/comments/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: your-secure-random-api-secret" \
  -d '{
    "comment_id": "c_12345",
    "post_urn": "urn:li:activity:789",
    "comment_text": "Great insights on AI agent architecture!",
    "post_context": "Building autonomous developer vlog agents."
  }'
```

### 4. Approve & Publish Suggested Reply
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/comments/c_12345/approve
```
*(Or click the `GET /comments/<comment_id>/approve` link in email notifications).*

### 5. Reject Suggested Reply
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/comments/c_12345/reject
```

### 6. Edit Suggested Reply Text
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/comments/c_12345/edit \
  -H "Content-Type: application/json" \
  -d '{"reply_text": "Thanks! We implemented it using SQLite WAL mode and NVIDIA NIM.", "approve": true}'
```

### 7. View / Update Configuration (Mode & Kill Switch)
```bash
curl -X POST https://linkedin-automation-xav0.onrender.com/comments/config \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: your-secure-random-api-secret" \
  -d '{
    "reply_mode": "approval",
    "global_kill_switch": false,
    "max_replies_per_hour": 15
  }'
```

---

## 🧪 Testing

Run the full test suite covering concurrency, prompt injection defenses, rate limits, and API mocking:

```bash
python test_suite.py
```

---

## 🤝 Contributing

Contributions, feedback, and pull requests are welcome! Feel free to star ⭐ the repository.

*🤖 Auto-generated Dev Log & AI Comment Reply System | Built with Python, NVIDIA NIM, and Cloud Microservices.*
