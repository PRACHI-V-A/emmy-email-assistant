import streamlit as st
import requests
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# Configure Gemini API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

BACKEND_URL = "https://emmy-email-assistant.onrender.com"

st.set_page_config(page_title="💌 EMMY - Your AI Email Assistant", layout="centered")
st.title("💌 Meet EMMY")
st.write("Your AI-powered email assistant. Draft and send professional emails with attachments in seconds.")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Step 1: Authenticate Gmail via backend
if st.button("🔑 Authenticate with Gmail"):
    try:
        response = requests.get(f"{BACKEND_URL}/auth-url")
        response.raise_for_status()
        auth_url = response.json().get("auth_url")
        if auth_url:
            st.markdown(f"[Click here to authenticate your Gmail account]({auth_url})")
        else:
            st.error("Failed to retrieve authentication URL.")
    except Exception as e:
        st.error(f"Error while getting authentication URL: {e}")

to = st.text_input("Recipient Email")
prompt = st.text_area("What should Emmy write?")
uploaded_file = st.file_uploader("📎 Attach a file (optional)", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"])

def ai_generate_email(prompt):
    """Generate subject and body using Gemini without placeholders."""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(f"""
        Write a complete professional, polite email based on this instruction: {prompt}.

        RULES:
        - NEVER use placeholders.
        - NEVER invent fake details.
        - Include greeting, body, closing, signature.
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
        """)

    text = response.text
    subject, body = "Generated Email", text.strip()
    if "Subject:" in text:
        subject = text.split("Subject:")[1].split("\n").strip()
        body = text.split("Body:")[1].strip()
    return subject, body

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

for idx, msg in enumerate(st.session_state.chat_history):
    st.markdown(f"🤖 **EMMY’s Draft:**")

    new_subject = st.text_input("✏️ Edit Subject", msg["subject"], key=f"sub_{idx}")
    new_body = st.text_area("✏️ Edit Body", msg["body"], height=250, key=f"body_{idx}")

    msg["subject"] = new_subject
    msg["body"] = new_body

    if msg["attachment"]:
        st.markdown(f"📎 Attached: **{msg['attachment'].name}**")

    if st.button(f"📨 Send Email to {msg['to']}", key=f"send_{idx}"):
        payload = {
            "user_email": "",  # You need to capture and supply the authenticated user's email here
            "recipient": msg["to"],
            "subject": msg["subject"],
            "body": msg["body"]
        }
        files = None
        if msg["attachment"]:
            files = {
                "file": (msg["attachment"].name, msg["attachment"].getvalue())
            }
        try:
            response = requests.post(f"{BACKEND_URL}/send_email", json=payload, files=files)
            if response.ok:
                st.success("✅ Email sent successfully!")
            else:
                st.error(f"❌ Failed to send email: {response.text}")
        except Exception as e:
            st.error(f"Error sending email: {e}")
