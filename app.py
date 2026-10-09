import os
import json
import smtplib
import logging
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
        f"Write an engaging LinkedIn post about '{topic}'. "
        f"Include a brief note or hashtag line near the end mentioning that this is an automated/AI-assisted post (e.g., '🤖 Auto-generated post | #AI #Automation'). "
        f"At the very end of your response, add a line formatted exactly like 'KEYWORD: <single_word_search_term>' "
        f"representing the visual concept of the post."
    )
    
    model_name = os.getenv("NVIDIA_MODEL", "moonshotai/kimi-k3")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=600
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

    if has_commits:
        commit_summary = "\n".join([f"- Repo: {c['repo']} | Commit: {c['message']}" for c in commits[:8]])
        repos_summary = "\n".join([f"- {r['full_name']} ({r['language']}): {r['description']}" for r in repos])

        prompt = (
            f"You are writing an authentic LinkedIn post as a software developer sharing a daily dev log / vlog update.\n\n"
            f"Developer GitHub: @{username}\n"
            f"Today's Commits & Code Progress:\n{commit_summary}\n\n"
            f"Projects Worked On:\n{repos_summary}\n\n"
            f"Requirements:\n"
            f"1. Write an engaging, inspiring, and authentic developer log post for LinkedIn (150-250 words).\n"
            f"2. Summarize what was built/improved today, technical highlights, and why it's exciting.\n"
            f"3. Include relevant emojis, clean formatting, and tech hashtags (e.g. #BuildInPublic #SoftwareEngineering #Coding #GitHub).\n"
            f"4. Add a brief note near the end: '🤖 Auto-generated Dev Log | #AI #LinkedInAutomation'.\n"
            f"5. At the very end of your response, add a line formatted exactly like 'KEYWORD: <single_word_search_term>' "
            f"representing the visual concept of the post (e.g., coding, server, python, devops).\n"
        )
    else:
        repos_summary = "\n".join([f"- {r['full_name']} ({r['language']}): {r['description']}" for r in repos[:3]])
        prompt = (
            f"You are writing a LinkedIn post as a software developer doing a project showcase / tech reflection.\n\n"
            f"Developer GitHub: @{username}\n"
            f"Active Projects:\n{repos_summary}\n\n"
            f"Requirements:\n"
            f"1. Write a compelling developer post about ongoing software engineering work and continuous learning (150-200 words).\n"
            f"2. Discuss architectural goals, building projects in public, and engineering best practices.\n"
            f"3. Include hashtags (#BuildInPublic #SoftwareDevelopment #TechCommunity).\n"
            f"4. Add a brief note near the end: '🤖 Auto-generated Dev Log | #AI #LinkedInAutomation'.\n"
            f"5. End with 'KEYWORD: <single_word_search_term>' for image search.\n"
        )

    model_name = os.getenv("NVIDIA_MODEL", "moonshotai/kimi-k3")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=700
    )

    output = response.choices[0].message.content
    if "KEYWORD:" in output:
        parts = output.split("KEYWORD:")
        text = parts[0].strip()
        keyword = parts[1].strip().split()[0]
    else:
        text = output.strip()
        keyword = "coding"

    logger.info(f"Generated GitHub Vlog Post Keyword: '{keyword}'")
    return text, keyword

def fetch_online_image(keyword: str, output_filepath="temp_image.jpg"):
    """Fetches a free high-resolution image from Unsplash based on keyword."""
    logger.info(f"Fetching online image from Unsplash for keyword: '{keyword}'")
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
        logger.error(f"Unsplash API error ({res.status_code}): {res.text}")
        raise Exception(f"Failed to fetch online image from Unsplash: {res.text}")

def send_approval_email(post_id: str, post_text: str, image_path: str, base_url: str = None):
    """Sends an email with an inline image preview and approval button link."""
    logger.info(f"Sending approval email for post_id: {post_id}")
    effective_url = (base_url or get_base_url()).rstrip('/')

    msg = MIMEMultipart("related")
    msg["Subject"] = "LinkedIn Post Draft: Approval Required"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    approve_url = f"{effective_url}/approve?post_id={post_id}"

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2>Your AI-Generated LinkedIn Post Draft</h2>
        <p><strong>Post Copy:</strong></p>
        <blockquote style="background: #f4f4f4; padding: 15px; border-left: 5px solid #0077b5; font-size: 14px; white-space: pre-wrap;">
          {post_text.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')}
        </blockquote>
        <p><strong>Online Fetched Image Preview:</strong></p>
        <p><img src="cid:post_image" style="max-width: 500px; width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" /></p>
        <br>
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

    # Attach image inline
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

    return email_sent, approve_url

def publish_to_linkedin(text_content: str, image_path: str):
    """3-step LinkedIn API image upload and publish routine."""
    logger.info("Starting LinkedIn publication workflow...")
    linkedin_version = os.getenv("LINKEDIN_API_VERSION", "202608")
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": linkedin_version,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    
    # 1. Initialize image upload
    init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
    init_payload = {"initializeUploadRequest": {"owner": AUTHOR_URN}}
    logger.info("Initializing image upload on LinkedIn...")
    init_res = requests.post(init_url, headers=headers, json=init_payload, timeout=15)
    
    if init_res.status_code not in (200, 201):
        logger.error(f"LinkedIn image initialization failed ({init_res.status_code}): {init_res.text}")
        return False

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
        return False
        
    logger.info("Binary image uploaded to LinkedIn successfully.")

    # 3. Publish post
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
        "lifecycleState": "PUBLISHED",
        "content": {"media": {"id": image_urn}}
    }
    
    logger.info("Publishing post to LinkedIn...")
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
        
        email_sent, approve_url = send_approval_email(post_id, post_text, image_path, base_url=get_base_url(request))
        
        return jsonify({
            "status": "success",
            "message": "Topic post generated successfully!",
            "post_id": post_id,
            "approve_url": approve_url,
            "email_sent": email_sent,
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

        email_sent, approve_url = send_approval_email(post_id, post_text, image_path, base_url=get_base_url(request))

        return jsonify({
            "status": "success",
            "message": "GitHub commit vlog generated successfully!",
            "post_id": post_id,
            "approve_url": approve_url,
            "email_sent": email_sent,
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
