import os
import json
import smtplib
import logging
import threading
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
import requests

# Load environment variables from .env file
load_dotenv()

# App Configuration
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "nvapi-YOUR_NVIDIA_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "YOUR_UNSPLASH_ACCESS_KEY")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "YOUR_LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.getenv("AUTHOR_URN", "urn:li:person:YOUR_MEMBER_ID")

# GitHub Configuration
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Email Configuration (SMTP)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your_email@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "your_app_password")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "your_email@gmail.com")
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "")
API_SECRET = os.getenv("API_SECRET", "")

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Persistent storage file for pending post approvals across server restarts/workers
PENDING_FILE = "pending_posts.json"

def load_pending_posts():
    """Loads pending posts from JSON file for cloud persistence across server restarts."""
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {PENDING_FILE}: {e}")
    return {}

def save_pending_posts(data):
    """Saves pending posts dictionary to JSON file."""
    try:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {PENDING_FILE}: {e}")

PENDING_POSTS = load_pending_posts()

# Initialize NVIDIA Client using OpenAI SDK
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

# --- HELPER FUNCTIONS ---

def verify_api_secret(req):
    """Verifies optional API_SECRET header or query parameter for remote triggering security."""
    if not API_SECRET:
        return True
    header_secret = req.headers.get("X-API-Secret") or req.headers.get("Authorization")
    query_secret = req.args.get("secret")
    body_secret = (req.get_json(silent=True) or {}).get("secret")
    
    if header_secret == API_SECRET or header_secret == f"Bearer {API_SECRET}":
        return True
    if query_secret == API_SECRET or body_secret == API_SECRET:
        return True
    return False

def get_base_url(req=None):
    """Determines effective server base URL for approval email links."""
    if SERVER_BASE_URL and not SERVER_BASE_URL.startswith("http://localhost"):
        return SERVER_BASE_URL.rstrip('/')
    if req and hasattr(req, 'host_url') and req.host_url:
        return req.host_url.rstrip('/')
    return SERVER_BASE_URL.rstrip('/') if SERVER_BASE_URL else "http://localhost:5000"

def generate_post_and_keyword(topic: str):
    """Generates LinkedIn post copy and a single keyword for fetching an online image."""
    logger.info(f"Generating post copy for topic: {topic}")
    prompt = (
        f"You are a top tech thought leader writing a high-value, viral LinkedIn post about '{topic}'.\n\n"
        f"POST STRUCTURE REQUIREMENTS:\n"
        f"1. VIRAL HOOK: Start with a powerful, attention-grabbing opening line about '{topic}'.\n"
        f"2. CORE INSIGHT: Explain what '{topic}' is, why it's trending, and why every developer/tech professional needs to care.\n"
        f"3. OPEN SOURCE TOOLS & FRAMEWORKS: Mention 2-3 popular open-source repositories, libraries, or tools related to '{topic}' (e.g., if AI agents: LangChain, AutoGen, CrewAI; if Cloud: Docker, Kubernetes, Terraform).\n"
        f"4. CATCHY VISUAL ASCII WORKFLOW: Include a 3-4 line text/emoji/ASCII architecture diagram explaining how this concept works step-by-step.\n"
        f"5. KEY TAKEAWAYS: Provide 3 punchy, actionable bullet points ('Key Things to Know').\n"
        f"6. COMMUNITY ENGAGEMENT PROMPT: End by asking the audience for their recommendations, favorite tools, or thoughts to drive comments and likes (e.g., '💡 What's your go-to open-source tool for this? What would you add? Drop your recommendations below! 👇').\n"
        f"7. Hashes & Footer: Clean formatting, emojis, and hashtags (#TechTrends #{topic.replace(' ', '')} #BuildInPublic #OpenSource #SoftwareEngineering).\n"
        f"8. Add a brief note near the end: '🤖 Auto-generated Tech Post | #AI #LinkedInAutomation'.\n"
        f"9. At the very end of your response, add a line formatted exactly like 'KEYWORD: <single_word_search_term>' for Unsplash image search.\n"
    )
    
    model_name = os.getenv("NVIDIA_MODEL", "moonshotai/kimi-k3")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800
    )
    
    output = response.choices[0].message.content
    if "KEYWORD:" in output:
        parts = output.split("KEYWORD:")
        text = parts[0].strip()
        keyword = parts[1].strip().split()[0]
    else:
        text = output.strip()
        keyword = topic.split()[0]
        
    logger.info(f"Generated Post Keyword: '{keyword}'")
    return text, keyword

def fetch_github_activity(username: str, token: str = None, force_latest: bool = False):
    """Fetches user's commits and repositories from GitHub API."""
    target_user = username or GITHUB_USERNAME
    if not target_user:
        raise Exception("GitHub username is not provided in request or environment (GITHUB_USERNAME).")

    headers = {"User-Agent": "LinkedIn-Automation-Agent"}
    auth_token = token or GITHUB_TOKEN
    if auth_token and not auth_token.startswith("YOUR_"):
        headers["Authorization"] = f"token {auth_token}"

    logger.info(f"Fetching GitHub events for user: {target_user}")
    events_url = f"https://api.github.com/users/{target_user}/events/public"
    res = requests.get(events_url, headers=headers, timeout=15)

    if res.status_code == 403:
        logger.warning(f"GitHub API rate limit hit (403) on shared cloud IP. Using fallback dev log mode for '{target_user}'.")
        return {
            "has_commits_today": False,
            "username": target_user,
            "commits": [],
            "repos": [{
                "name": "software-automation",
                "full_name": f"{target_user}/software-automation",
                "description": "Full-stack AI Agents & Cloud Infrastructure Projects",
                "language": "Python / Cloud Architecture",
                "html_url": f"https://github.com/{target_user}"
            }]
        }
    elif res.status_code != 200:
        logger.error(f"GitHub API error ({res.status_code}): {res.text}")
        raise Exception(f"GitHub API request failed for user '{target_user}': status {res.status_code}")

    events = res.json()
    today_utc = datetime.now(timezone.utc).date()

    commits_data = []
    repo_set = set()

    for ev in events:
        if ev.get("type") == "PushEvent":
            created_at = ev.get("created_at")
            ev_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").date() if created_at else None
            
            if force_latest or (ev_date and ev_date == today_utc):
                repo_name = ev.get("repo", {}).get("name")
                payload = ev.get("payload", {})
                commits = payload.get("commits", [])
                
                for c in commits:
                    msg = c.get("message", "").strip()
                    if msg:
                        commits_data.append({
                            "repo": repo_name,
                            "message": msg,
                            "date": created_at
                        })
                        if repo_name:
                            repo_set.add(repo_name)

    # Fallback to recent public repositories if no commits recorded today
    if not commits_data:
        logger.info(f"No commits found today for '{target_user}'. Checking recent repositories...")
        repos_url = f"https://api.github.com/users/{target_user}/repos?sort=updated&per_page=3"
        r_res = requests.get(repos_url, headers=headers, timeout=15)
        latest_repos = []
        if r_res.status_code == 200:
            for repo in r_res.json():
                latest_repos.append({
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "description": repo.get("description") or "Open source project",
                    "language": repo.get("language") or "Code",
                    "html_url": repo.get("html_url")
                })
        return {
            "has_commits_today": False,
            "username": target_user,
            "commits": [],
            "repos": latest_repos
        }

    repos_meta = []
    for rname in repo_set:
        r_url = f"https://api.github.com/repos/{rname}"
        r_res = requests.get(r_url, headers=headers, timeout=10)
        if r_res.status_code == 200:
            rdata = r_res.json()
            repos_meta.append({
                "name": rdata.get("name"),
                "full_name": rdata.get("full_name"),
                "description": rdata.get("description") or "Project updates & features",
                "language": rdata.get("language") or "Software Development",
                "stars": rdata.get("stargazers_count", 0),
                "html_url": rdata.get("html_url")
            })

    return {
        "has_commits_today": True,
        "username": target_user,
        "commits": commits_data,
        "repos": repos_meta
    }

def generate_github_vlog_post(github_info: dict):
    """Generates a developer vlog / project update LinkedIn post based on GitHub activity."""
    username = github_info["username"]
    has_commits = github_info["has_commits_today"]
    commits = github_info["commits"]
    repos = github_info["repos"]

    logger.info(f"Generating GitHub vlog post for {username}. Has commits today: {has_commits}")

    # Focus exclusively on the SINGLE most recent project
    primary_repo = repos[0] if repos else {
        "name": "linkedin_automation",
        "full_name": f"{username}/linkedin_automation",
        "description": "AI-powered automated content workflow & LinkedIn posting agent",
        "language": "Python / Flask / LLM"
    }
    repo_name = primary_repo.get("name", "project")
    repo_full_name = primary_repo.get("full_name", f"{username}/{repo_name}")
    repo_desc = primary_repo.get("description") or "AI Automation & Developer Workflows"
    repo_lang = primary_repo.get("language") or "Python"

    if has_commits:
        recent_commits = [c['message'] for c in commits if repo_name in c.get('repo', '')]
        if not recent_commits:
            recent_commits = [c['message'] for c in commits[:4]]
        commit_details = "\n".join([f"- {m}" for m in recent_commits[:5]])
    else:
        commit_details = f"Recent updates to {repo_name}: Architecture enhancements, cloud deployment, and API integrations."

    prompt = (
        f"You are a passionate software engineer writing a high-engagement, viral LinkedIn post showcasing your MOST RECENT project.\n\n"
        f"Developer GitHub: @{username}\n"
        f"Featured Project Name: {repo_full_name}\n"
        f"Primary Programming Language: {repo_lang}\n"
        f"Project Description: {repo_desc}\n"
        f"Latest Commit Messages / Code Progress:\n{commit_details}\n\n"
        f"CRITICAL POST REQUIREMENTS:\n"
        f"1. SINGLE PROJECT FOCUS: Focus 100% on THIS ONE PROJECT ({repo_name}). Do NOT mention or hardcode unrelated external tools.\n"
        f"2. ATTENTION-GRABBING HOOK: Start with a powerful, compelling opening line about {repo_name}.\n"
        f"3. DYNAMIC TECH STACK (NO HARDCODING): Dynamically infer the exact tech stack from the project name ({repo_name}), primary language ({repo_lang}), commits, and description. List the specific frameworks, libraries, APIs, and tools that belong to THIS SPECIFIC project (e.g., if TypeScript/Superset: React, TypeScript, Apache Superset, REST APIs; if Python/AI: Python, Flask, LLM APIs, REST Webhooks, Docker, Cloud Host). Include repo link: github.com/{repo_full_name}.\n"
        f"4. DETAILED MULTI-STAGE ARCHITECTURE WORKFLOW: Construct a clean, detailed 4-6 step text/emoji/ASCII architecture diagram showing how data & components flow under the hood specifically for THIS project (e.g., Client/Trigger ➔ API Router ➔ Processing Engine ➔ External APIs / DB ➔ Cloud Deployment).\n"
        f"5. PRACTICAL REAL-WORLD USES: Explain 2-3 concrete benefits / real-world use cases of why someone would use or build this project.\n"
        f"6. COMMUNITY RECOMMENDATIONS & FEEDBACK: Explicitly ask the LinkedIn developer community for their recommendations, feedback, or suggestions for improvement to drive comments & likes (e.g., '💡 What features would you add next? How would you optimize this architecture? Drop your recommendations below! 👇').\n"
        f"7. HASHTAGS & FOOTER: Clean formatting, emojis, and hashtags (#BuildInPublic #SoftwareEngineering #{repo_lang.replace(' ', '').replace('/', '')} #TechCommunity).\n"
        f"8. Add a brief note near the end: '🤖 Auto-generated Dev Log | #AI #LinkedInAutomation'.\n"
        f"9. At the very end of your response, add a line formatted exactly like 'KEYWORD: <single_word_search_term>' for image search. If no image is appropriate for this specific project, put 'KEYWORD: NONE'.\n"
    )

    model_name = os.getenv("NVIDIA_MODEL", "moonshotai/kimi-k3")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=750
    )

    output = response.choices[0].message.content
    if "KEYWORD:" in output:
        parts = output.split("KEYWORD:")
        text = parts[0].strip()
        keyword = parts[1].strip().split()[0]
    else:
        text = output.strip()
        keyword = repo_lang.split()[0] if repo_lang else "coding"

    logger.info(f"Generated GitHub Vlog Post Keyword: '{keyword}'")
    return text, keyword

def fetch_online_image(keyword: str, output_filepath="temp_image.jpg"):
    """Fetches a free high-resolution image from Unsplash based on keyword. Returns None if fetch fails or no relevant image."""
    if not keyword or keyword.lower() in ("none", "null", "noimage"):
        logger.info("No valid image keyword provided. Skipping image download.")
        return None
        
    logger.info(f"Fetching online image from Unsplash for keyword: '{keyword}'")
    try:
        url = f"https://api.unsplash.com/photos/random?query={keyword}&client_id={UNSPLASH_ACCESS_KEY}"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            img_url = res.json()["urls"]["regular"]
            img_data = requests.get(img_url, timeout=30).content
            with open(output_filepath, "wb") as f:
                f.write(img_data)
            logger.info(f"Image downloaded successfully to {output_filepath}")
            return output_filepath
        else:
            logger.warning(f"Unsplash API returned {res.status_code}. Skipping image attachment.")
            return None
    except Exception as e:
        logger.warning(f"Failed to fetch online image from Unsplash ({e}). Proceeding without image.")
        return None

def send_approval_email(post_id: str, post_text: str, image_path: str = None, base_url: str = None):
    """Sends an email with an inline image preview (if available) and approval button link."""
    logger.info(f"Sending approval email for post_id: {post_id}")
    effective_url = (base_url or get_base_url()).rstrip('/')
    approve_url = f"{effective_url}/approve?post_id={post_id}"

    msg = MIMEMultipart("related")
    msg["Subject"] = "LinkedIn Post Draft: Approval Required"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    image_html = ""
    if image_path and os.path.exists(image_path):
        image_html = '<p><strong>Online Fetched Image Preview:</strong></p><p><img src="cid:post_image" style="max-width: 500px; width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" /></p><br>'

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2>Your AI-Generated LinkedIn Post Draft</h2>
        <p><strong>Post Copy:</strong></p>
        <blockquote style="background: #f4f4f4; padding: 15px; border-left: 5px solid #0077b5; font-size: 14px; white-space: pre-wrap;">
          {post_text.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')}
        </blockquote>
        {image_html}
        <a href="{approve_url}" 
           style="background-color: #0077b5; color: white; padding: 14px 28px; text-decoration: none; font-weight: bold; border-radius: 6px; display: inline-block; font-size: 16px;">
           ✓ Approve & Publish to LinkedIn
        </a>
      </body>
    </html>
    """
    
    msg_alternative = MIMEMultipart("alternative")
    msg.attach(msg_alternative)
    msg_alternative.attach(MIMEText(html_content, "html"))

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<post_image>")
            msg.attach(img)

    email_sent = False
    try:
        logger.info("Attempting Gmail SMTP via Port 587 (STARTTLS)...")
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        logger.info("Approval email sent successfully via Port 587.")
        email_sent = True
    except Exception as e587:
        logger.warning(f"Port 587 connection failed ({e587}), trying Port 465 (SSL)...")
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
            logger.info("Approval email sent successfully via Port 465.")
            email_sent = True
        except Exception as e465:
            logger.error(f"SMTP connection blocked or failed on cloud host: {e465}")
            email_sent = False

def send_approval_email_async(post_id: str, post_text: str, image_path: str = None, base_url: str = None):
    """Fires background thread to send email without blocking the HTTP response."""
    def _send_worker():
        try:
            send_approval_email(post_id, post_text, image_path, base_url)
        except Exception as e:
            logger.error(f"Background email delivery failed: {e}")
            
    thread = threading.Thread(target=_send_worker, daemon=True)
    thread.start()

def publish_to_linkedin(text_content: str, image_path: str = None):
    """3-step LinkedIn API image upload and publish routine, with clean text-only fallback."""
    logger.info("Starting LinkedIn publication workflow...")
    linkedin_version = os.getenv("LINKEDIN_API_VERSION", "202608")
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": linkedin_version,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    
    image_urn = None
    if image_path and os.path.exists(image_path):
        # 1. Initialize image upload
        init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
        init_payload = {"initializeUploadRequest": {"owner": AUTHOR_URN}}
        logger.info("Initializing image upload on LinkedIn...")
        init_res = requests.post(init_url, headers=headers, json=init_payload, timeout=15)
        
        if init_res.status_code in (200, 201):
            init_data = init_res.json()["value"]
            upload_url = init_data["uploadUrl"]
            image_urn = init_data["image"]
            logger.info(f"LinkedIn upload URL obtained. Image URN: {image_urn}")

            # 2. Upload binary image file
            with open(image_path, "rb") as f:
                upload_res = requests.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
                    data=f,
                    timeout=60
                )
            if upload_res.status_code not in (200, 201):
                logger.error(f"LinkedIn binary upload failed ({upload_res.status_code}): {upload_res.text}")
                image_urn = None
            else:
                logger.info("Binary image uploaded to LinkedIn successfully.")
        else:
            logger.error(f"LinkedIn image initialization failed ({init_res.status_code}): {init_res.text}")
            image_urn = None

    # 3. Publish post (with media if image_urn exists, or clean text-only)
    post_url = "https://api.linkedin.com/rest/posts"
    post_payload = {
        "author": AUTHOR_URN,
        "commentary": text_content,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED"
    }
    
    if image_urn:
        post_payload["content"] = {"media": {"id": image_urn}}
    
    logger.info(f"Publishing post to LinkedIn (Has image media: {image_urn is not None})...")
    res = requests.post(post_url, headers=headers, json=post_payload, timeout=15)
    if res.status_code in (200, 201):
        logger.info("Post published to LinkedIn successfully!")
        return True
    else:
        logger.error(f"LinkedIn post publication failed ({res.status_code}): {res.text}")
        return False

# --- FLASK ROUTES ---

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "online",
        "service": "LinkedIn Remote Automation & GitHub Vlog Agent",
        "endpoints": {
            "trigger_topic": "POST /trigger-generation",
            "trigger_github": "POST /trigger-github",
            "approve": "GET /approve?post_id=<ID>"
        }
    })

@app.route("/trigger-generation", methods=["POST"])
def trigger_generation():
    """Trigger endpoint to kick off generation based on topic."""
    if not verify_api_secret(request):
        return jsonify({"status": "error", "message": "Unauthorized. Invalid API Secret."}), 401
        
    try:
        data = request.get_json(silent=True) or {}
        topic = data.get("topic", "Artificial Intelligence Trends, new AI models and AI agents")
        logger.info(f"Trigger received for topic: '{topic}'")
        
        post_text, keyword = generate_post_and_keyword(topic)
        
        post_id = os.urandom(8).hex()
        image_path = f"temp_{post_id}.jpg"
        
        fetch_online_image(keyword, output_filepath=image_path)
        
        PENDING_POSTS[post_id] = {"text": post_text, "image_path": image_path}
        save_pending_posts(PENDING_POSTS)
        
        effective_url = get_base_url(request).rstrip('/')
        approve_url = f"{effective_url}/approve?post_id={post_id}"
        
        send_approval_email_async(post_id, post_text, image_path, base_url=effective_url)
        
        return jsonify({
            "status": "success",
            "message": "Topic post generated successfully!",
            "post_id": post_id,
            "approve_url": approve_url,
            "keyword_used": keyword,
            "post_text": post_text
        }), 200
        
    except Exception as e:
        logger.exception("Error during topic post generation flow")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/trigger-github", methods=["POST"])
def trigger_github():
    """Trigger endpoint to check GitHub commits today and send developer vlog post for email approval."""
    if not verify_api_secret(request):
        return jsonify({"status": "error", "message": "Unauthorized. Invalid API Secret."}), 401

    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", GITHUB_USERNAME)
        force_latest = data.get("force_latest", False)

        logger.info(f"Triggering GitHub commit agent for user: '{username}'")
        github_info = fetch_github_activity(username=username, force_latest=force_latest)
        
        post_text, keyword = generate_github_vlog_post(github_info)

        post_id = os.urandom(8).hex()
        image_path = f"temp_{post_id}.jpg"

        fetch_online_image(keyword, output_filepath=image_path)

        PENDING_POSTS[post_id] = {"text": post_text, "image_path": image_path}
        save_pending_posts(PENDING_POSTS)

        effective_url = get_base_url(request).rstrip('/')
        approve_url = f"{effective_url}/approve?post_id={post_id}"

        send_approval_email_async(post_id, post_text, image_path, base_url=effective_url)

        return jsonify({
            "status": "success",
            "message": "GitHub commit vlog generated successfully!",
            "post_id": post_id,
            "approve_url": approve_url,
            "has_commits_today": github_info["has_commits_today"],
            "commits_found": len(github_info["commits"]),
            "keyword_used": keyword,
            "post_text": post_text
        }), 200

    except Exception as e:
        logger.exception("Error during GitHub post generation flow")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/approve", methods=["GET"])
def approve_post():
    """Webhook triggered when user clicks 'Approve' link in email."""
    post_id = request.args.get("post_id")
    
    # Reload pending posts from file if missing from memory
    global PENDING_POSTS
    if not PENDING_POSTS:
        PENDING_POSTS = load_pending_posts()
    
    if not post_id or post_id not in PENDING_POSTS:
        return "<h3>Error: Invalid or already processed Post ID.</h3>", 400
        
    post_data = PENDING_POSTS.pop(post_id)
    save_pending_posts(PENDING_POSTS)

    try:
        success = publish_to_linkedin(post_data["text"], post_data["image_path"])
        
        # Clean up local image file
        if os.path.exists(post_data["image_path"]):
            os.remove(post_data["image_path"])
            
        if success:
            return "<h3>Success! The developer vlog post and image have been published to LinkedIn.</h3>", 200
        else:
            return "<h3>Failed to publish post to LinkedIn API. Check server logs for details.</h3>", 500
    except Exception as e:
        logger.exception("Exception while publishing to LinkedIn")
        return f"<h3>Error during publishing: {str(e)}</h3>", 500

@app.errorhandler(500)
@app.errorhandler(Exception)
def handle_internal_error(error):
    logger.exception(f"Unhandled error encountered: {error}")
    return jsonify({
        "status": "error",
        "message": str(error) or "Internal server error occurred on cloud host."
    }), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
