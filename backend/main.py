from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = FastAPI()

# Allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change to frontend URL if deployed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB setup for tokens
DB_PATH = "backend/db.sqlite"
os.makedirs("backend", exist_ok=True)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS tokens (
    email TEXT PRIMARY KEY,
    token TEXT
)
""")
conn.commit()
conn.close()

# Google OAuth setup
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
REDIRECT_URI = "https://emmy-email-assistant.onrender.com"

@app.get("/auth")
def auth():
    flow = Flow.from_client_secrets_file(
        "backend/credentials.json",
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)

@app.get("/oauth2callback")
def oauth2callback(request: Request):
    flow = Flow.from_client_secrets_file(
        "backend/credentials.json",
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    # Store tokens
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO tokens (email, token) VALUES (?, ?)", (email, creds.to_json()))
    conn.commit()
    conn.close()

    return JSONResponse({"message": "Authentication successful!", "email": email})

def get_credentials(user_email: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM tokens WHERE email=?", (user_email,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    creds = Credentials.from_authorized_user_info(eval(row[0]), SCOPES)
    return creds

@app.post("/send_email")
async def send_email(data: dict):
    user_email = data.get("user_email")
    recipient = data.get("recipient")
    subject = data.get("subject")
    body = data.get("body")

    creds = get_credentials(user_email)
    if not creds:
        return JSONResponse({"error": "User not authenticated"}, status_code=403)

    service = build("gmail", "v1", credentials=creds)

    from email.mime.text import MIMEText
    import base64

    message = MIMEText(body)
    message["to"] = recipient
    message["subject"] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

    return {"message": "Email sent successfully!"}
