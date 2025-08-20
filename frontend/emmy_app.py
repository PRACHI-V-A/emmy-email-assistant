import streamlit as st
import requests
import os
import base64
import pickle
from dotenv import load_dotenv
import google.generativeai as genai
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="💌 EMMY - Your AI Email Assistant", layout="centered")
st.title("💌 Meet EMMY")
st.write("Your AI-powered email assistant. Draft and send professional emails with attachments in seconds.")

# Initialize memory
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ---------------- Gmail Authentication ----------------
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def authenticate_gmail():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("../backend/credentials.json", SCOPES)

            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build("gmail", "v1", credentials=creds)
    return service


# ---------------- AI Draft Generation ----------------
def ai_generate_email(prompt):
    """Generate subject and body using Gemini without placeholders."""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(
        f"""
        Write a complete professional, polite email based on this instruction: {prompt}.

        RULES:
        - NEVER use placeholders like [Recipient], [Project Name], [Reason], etc.
        - NEVER invent fake details.
        - If a detail is missing, keep it general (e.g., "the recent project").
        - Always include greeting, body, closing, and signature.
        - End with:
            Prachi Adhalage
            Software Engineer
            prachiadhalage@gmail.com
        Format exactly:
        Subject: <short subject>
        Body:
        Dear <recipient/generic>,
        <body>
        Sincerely,
        Prachi Adhalage
        prachiadhalage@gmail.com
        """
    )

    text = response.text
    subject, body = "Generated Email", text.strip()

    if "Subject:" in text:
        subject = text.split("Subject:")[1].split("\n")[0].strip()
        body = text.split("Body:")[1].strip()

    return subject, body


# ---------------- Gmail Message Builder ----------------
def create_message(sender, to, subject, body, attachment=None):
    if attachment:
        message = MIMEMultipart()
        message["to"] = to
        message["from"] = sender
        message["subject"] = subject

        message.attach(MIMEText(body, "plain"))

        # Reset file pointer
        attachment.seek(0)
        filename = attachment.name
        file_data = attachment.read()

        part = MIMEBase("application", "octet-stream")
        part.set_payload(file_data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        message.attach(part)
    else:
        message = MIMEText(body)
        message["to"] = to
        message["from"] = sender
        message["subject"] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw_message}


def send_message(service, user_id, message):
    try:
        sent_message = service.users().messages().send(userId=user_id, body=message).execute()
        return f"✅ Email sent successfully! ID: {sent_message['id']}"
    except Exception as e:
        return f"❌ Error: {e}"


# ---------------- Streamlit UI ----------------
st.subheader("Step 1: Connect your Gmail")
st.markdown("Click below to log in and allow Emmy to send emails on your behalf.")

if st.button("🔑 Authenticate with Gmail"):
    service = authenticate_gmail()
    if service:
        st.success("Gmail authenticated successfully!")

to = st.text_input("Recipient Email")
prompt = st.text_area("What should Emmy write?")
uploaded_file = st.file_uploader("📎 Attach a file (optional)", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"])

if st.button("✨ Generate Draft"):
    if not to or not prompt:
        st.warning("Please enter both recipient email and prompt.")
    else:
        subject, body = ai_generate_email(prompt)
        st.session_state.chat_history.append({
            "role": "emmy",
            "to": to,
            "subject": subject,
            "body": body,
            "attachment": uploaded_file
        })

# Show chat history
for idx, msg in enumerate(st.session_state.chat_history):
    st.markdown(f"🤖 **EMMY’s Draft:**")

    new_subject = st.text_input("✏️ Edit Subject", msg["subject"], key=f"sub_{idx}")
    new_body = st.text_area("✏️ Edit Body", msg["body"], height=250, key=f"body_{idx}")

    msg["subject"] = new_subject
    msg["body"] = new_body

    if msg["attachment"]:
        st.markdown(f"📎 Attached: **{msg['attachment'].name}**")

    if st.button(f"📨 Send Email to {msg['to']}", key=f"send_{idx}"):
        service = authenticate_gmail()
        message = create_message("me", msg["to"], msg["subject"], msg["body"], msg["attachment"])
        status = send_message(service, "me", message)
        st.success(status)
