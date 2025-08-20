import os
import base64
import argparse
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.generativeai as genai
from dotenv import load_dotenv
import pickle

# Load environment variables
load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Gmail API scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def authenticate_gmail():
    """Authenticate and return Gmail API service."""
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



def create_message(sender, to, subject, body):
    """Create an email message."""
    message = MIMEText(body)
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw_message}

def send_message(service, user_id, message):
    """Send email via Gmail API."""
    try:
        sent_message = service.users().messages().send(userId=user_id, body=message).execute()
        print(f"✅ Email sent! Message ID: {sent_message['id']}")
        return sent_message
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="AI Email Agent with Gemini + Gmail API")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--prompt", required=True, help="Prompt for AI to draft email")
    args = parser.parse_args()

    service = authenticate_gmail()
    subject, body = ai_generate_email(args.prompt)
    message = create_message("me", args.to, subject, body)
    send_message(service, "me", message)

if __name__ == "__main__":
    main()
