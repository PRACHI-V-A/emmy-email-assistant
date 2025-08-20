from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
import json

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText


app = FastAPI()


import os
import sqlite3

DB_PATH = os.path.join(os.getcwd(), "backend", "db.sqlite")
print(f"SQLite DB path: {DB_PATH}")

os.makedirs("backend", exist_ok=True)
print(f"DB directory 'backend' exists or created.")

print(f"DB exists before creation? {os.path.exists(DB_PATH)}")

conn = sqlite3.connect(DB_PATH)
print("Connected to SQLite DB")

cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS tokens (
    email TEXT PRIMARY KEY,
    token TEXT
)
""")
conn.commit()
print("Created tokens table if not existing")
conn.close()

# Allow frontend requests (Update with your actual Streamlit frontend URL, no trailing slash)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://emmy-email-assistant.streamlit.app"],  # Correct domain, no trailing slash
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.send"
]


REDIRECT_URI = "https://emmy-email-assistant.onrender.com/oauth2callback"


# Endpoint to get OAuth authorization URL
@app.get("/auth-url")
def get_auth_url():
    flow = Flow.from_client_secrets_file(
        "/etc/secrets/GOOGLE_CLIENT_SECRETS",
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )
    return {"auth_url": auth_url}


# OAuth2 callback endpoint
@app.get("/oauth2callback")
def oauth2callback(request: Request):
    flow = Flow.from_client_secrets_file(
        "/etc/secrets/GOOGLE_CLIENT_SECRETS",
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    # Store tokens as JSON string
    token_json = creds.to_json()

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO tokens (email, token) VALUES (?, ?)", (email, token_json))
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"message": "Authentication successful!", "email": email})


# Pydantic model for send_email request validation
class EmailRequest(BaseModel):
    user_email: str
    recipient: str
    subject: str
    body: str


@app.post("/send_email")
async def send_email(data: EmailRequest):
    creds = get_credentials(data.user_email)
    if not creds:
        raise HTTPException(status_code=403, detail="User not authenticated")

    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(data.body)
    message["to"] = data.recipient
    message["subject"] = data.subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

    return {"message": "Email sent successfully!"}


# Helper function to get Credentials object from DB JSON
def get_credentials(user_email: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM tokens WHERE email=?", (user_email,))
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    token_info = json.loads(row[0])
    creds = Credentials.from_authorized_user_info(token_info, SCOPES)
    return creds
