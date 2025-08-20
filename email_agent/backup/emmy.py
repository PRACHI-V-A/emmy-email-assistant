import os
import base64
import streamlit as st
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.generativeai as genai
import pickle
from dotenv import load_dotenv

# Load .env
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Gmail authentication
def authenticate_gmail():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build("gmail", "v1", credentials=creds)
    return service

# AI draft generation
def ai_generate_email(prompt):
    """Generate subject and body using Gemini without placeholders or hallucinated details."""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(
        f"""
        Write a complete professional, polite email based on this instruction: {prompt}.

        RULES:
        - NEVER use placeholders like [Recipient], [Project Name], [Reason], etc.
        - NEVER make up specific details (project names, dates, titles) unless explicitly given in the prompt.
        - If a detail is missing, phrase it generally (e.g., say "the recent project" instead of inventing a name).
        - Always include greeting, body, closing, and signature.
        - Always end with my real details:
            Prachi Adhalage
            prachiadhalage@gmail.com
        - NEVER use placeholders like [Company Name], [Previous Company Name], [Reason], etc.
        - If the user has NOT given a detail (like company name, project title, or platform), 
          write it GENERICALLY (e.g., "your company", "the recent project", "a leading platform") 
          but do NOT invent fake details.
        - Always include greeting, body, closing, and signature.
        - Always end with:
            Prachi Adhalage
            Software Engineer
            prachiadhalage@gmail.com

        Format the output exactly like this:

        Subject: <short, clear subject>
        Body:
        Dear <recipient or generic greeting>,
        <rest of the email body>
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


# Gmail message builder with attachment
def create_message(sender, to, subject, body, attachment=None):
    if attachment:
        message = MIMEMultipart()
        message["to"] = to
        message["from"] = sender
        message["subject"] = subject

        # Add body
        message.attach(MIMEText(body, "plain"))

        # Add attachment
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

# -------------------- STREAMLIT UI --------------------

st.set_page_config(page_title="💌 EMMY - Your AI Email Assistant", layout="centered")
st.title("💌 Meet EMMY")
st.write("Your AI-powered email assistant. Draft and send professional emails with attachments in seconds.")

# Initialize memory
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Input
to = st.text_input("Recipient Email")
prompt = st.text_area("What should Emmy write?")
uploaded_file = st.file_uploader("📎 Attach a file (optional)", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"])

if st.button("✨ Generate Draft"):
    if not to or not prompt:
        st.warning("Please enter both recipient email and prompt.")
    else:
        subject, body = ai_generate_email(prompt)
        st.session_state.chat_history.append({
            "role": "user",
            "content": f"To: {to}\n{prompt}"
        })
        st.session_state.chat_history = [{   # overwrite history
    "role": "emmy",
    "content": f"**Subject:** {subject}\n\n{body}",
    "to": to,
    "subject": subject,
    "body": body,
    "attachment": uploaded_file
}]

# Show chat history
# Show chat history
for idx, msg in enumerate(st.session_state.chat_history):
    if msg["role"] == "user":
        st.markdown(f"🧑 **You:** {msg['content']}")
    else:
        st.markdown(f"🤖 **EMMY’s Draft:**")

        # Editable subject + body
        new_subject = st.text_input("✏️ Edit Subject", msg["subject"], key=f"sub_{idx}")
        new_body = st.text_area("✏️ Edit Body", msg["body"], height=250, key=f"body_{idx}")

        # Save back into session state
        msg["subject"] = new_subject
        msg["body"] = new_body

        # Show attachment (if uploaded)
        if msg["attachment"]:
            st.markdown(f"📎 Attached: **{msg['attachment'].name}**")

        # Send button
        if st.button(f"📨 Send Email to {msg['to']}", key=f"send_{idx}"):
            service = authenticate_gmail()
            message = create_message("me", msg["to"], msg["subject"], msg["body"], msg["attachment"])
            status = send_message(service, "me", message)
            st.success(status)