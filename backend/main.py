from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
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
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

app = FastAPI()

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
    allow_origins=["https://emmy-email-assistant.streamlit.app"],  # No trailing slash
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
    FLOW_SECRET_PATH = "/etc/secrets/GOOGLE_CLIENT_SECRETS"  # Use your actual secrets path
    flow = Flow.from_client_secrets_file(FLOW_SECRET_PATH, scopes=SCOPES, redirect_uri=REDIRECT_URI)

    auth_url, _ = flow.authorization_url(
        prompt="select_account",         # Force Google to show account selector every time
        access_type="offline",
        include_granted_scopes="true",
    )
    return {"auth_url": auth_url}

# OAuth2 callback endpoint with error handling
@app.get("/oauth2callback")
def oauth2callback(request: Request):
    try:
        FLOW_SECRET_PATH = "/etc/secrets/GOOGLE_CLIENT_SECRETS"  # Use your actual secrets path
        flow = Flow.from_client_secrets_file(FLOW_SECRET_PATH, scopes=SCOPES, redirect_uri=REDIRECT_URI)
        flow.fetch_token(authorization_response=str(request.url))

        creds = flow.credentials
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email = profile["emailAddress"]

        token_json = creds.to_json()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO tokens (email, token) VALUES (?, ?)", (email, token_json))
        conn.commit()
        conn.close()

        return JSONResponse({"message": "Authentication successful!", "email": email})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# Endpoint to get authenticated user email for frontend
@app.get("/get_authenticated_user")
def get_authenticated_user():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM tokens LIMIT 1")
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return JSONResponse({"email": None}, status_code=404)
    return {"email": row[0]}

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

# Email sending endpoint with file attachment support
@app.post("/send_email")
async def send_email(
    user_email: str = Form(...),
    recipient: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    file: UploadFile | None = File(None)
):
    creds = get_credentials(user_email)
    if not creds:
        raise HTTPException(status_code=403, detail="User not authenticated")

    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(body)

    if file:
        file_content = await file.read()

        msg = MIMEMultipart()
        msg.attach(message)
        msg["to"] = recipient
        msg["subject"] = subject

        part = MIMEBase("application", "octet-stream")
        part.set_payload(file_content)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={file.filename}")
        msg.attach(part)

        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    else:
        message["to"] = recipient
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

    return {"message": "Email sent successfully!"}

# logout code this is 

@app.post("/logout")
async def logout(user_email: str = Form(...)):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tokens WHERE email=?", (user_email,))
        conn.commit()
        conn.close()
        return {"message": f"User {user_email} logged out successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout failed: {e}")
