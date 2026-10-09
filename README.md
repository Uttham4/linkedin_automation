# LinkedIn Automated Email Approval & Publishing System

An automated LinkedIn content generation and interactive email approval workflow system powered by NVIDIA LLM, Unsplash image search, SMTP email with inline preview, and LinkedIn REST API.

---

## System Flow Architecture

```
┌──────────────────┐
│ NVIDIA API (LLM) │ ──> Generates Post Text + Image Keyword (e.g., "artificial intelligence")
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Unsplash API    │ ──> Searches online & downloads target image binary
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Email SMTP Server│ ──> Sends email with post draft, image preview, & [Approve] link
└────────┬─────────┘
         │  (User receives email & clicks "Approve")
         ▼
┌──────────────────┐     ┌─────────────────────┐     ┌───────────────────────┐
│ Approval Webhook │ ──> │ Upload Image to     │ ──> │ Publish to LinkedIn   │
│  (Flask Server)  │     │ LinkedIn Asset API  │     │ (`/rest/posts`)       │
└──────────────────┘     └─────────────────────┘     └───────────────────────┘
```

---

## 1. Prerequisites & API Credentials

1. **NVIDIA API Key**: Obtain a key from [NVIDIA Integrated APIs](https://build.nvidia.com/).
2. **Unsplash Access Key**: Obtain a free Access Key from [Unsplash Developers](https://unsplash.com/developers).
3. **LinkedIn OAuth Access Token & Member URN**:
   - Access token with `w_member_social` permission scope.
   - Author URN (e.g., `urn:li:person:YOUR_MEMBER_ID`).
4. **Gmail App Password**:
   - Enable 2-Factor Authentication on your Google Account.
   - Generate an **App Password** under Account Security -> App Passwords.

---

## 2. Installation

1. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables in `.env`:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and populate your credentials.

---

## 3. Running the Server

1. Start the Flask application:
   ```bash
   python app.py
   ```

2. Expose your server via `ngrok` (so email links work outside localhost):
   ```bash
   ngrok http 5000
   ```

3. Update `SERVER_BASE_URL` in `.env` with your public ngrok URL:
   ```env
   SERVER_BASE_URL=https://xxxx.ngrok-free.app
   ```

---

## 4. Triggering Post Generation

Send a `POST` request to trigger the automation flow:

```bash
curl -X POST http://localhost:5000/trigger-generation \
  -H "Content-Type: application/json" \
  -d '{"topic": "Scalable Cloud Architecture"}'
```

---

## 5. Email Review & Approval

1. Check your email inbox for the subject **"LinkedIn Post Draft: Approval Required"**.
2. Review the generated copy and inline Unsplash image preview.
3. Click **✓ Approve & Publish to LinkedIn**.
4. The system uploads the binary image to LinkedIn and publishes the post.
