"""Send the generated monthly email via SMTP.

Reads credentials from environment (set as GitHub Actions secrets):
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS
  EMAIL_FROM (default = SMTP_USER), EMAIL_TO (comma-separated)

Works with Gmail (App Password), SendGrid, Mailgun, AWS SES SMTP, etc.
Run build_email.py first. Dry-run (no send) if SMTP_HOST is unset.
"""
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date

from lib import OUTPUT


def main():
    html_path = os.path.join(OUTPUT, "monthly_email.html")
    txt_path = os.path.join(OUTPUT, "monthly_email.txt")
    with open(html_path) as f:
        html_body = f.read()
    text_body = ""
    if os.path.exists(txt_path):
        with open(txt_path) as f:
            text_body = f.read()

    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("EMAIL_TO", "")
    if not host or not to:
        print("SMTP_HOST or EMAIL_TO unset — dry run, not sending.")
        print("Recipients would be:", to or "(none)")
        return

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    sender = os.environ.get("EMAIL_FROM", user)
    recipients = [x.strip() for x in to.split(",") if x.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Clinical Catalyst Brief — %s" % date.today().strftime("%B %Y")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            if user:
                s.login(user, pw)
            s.sendmail(sender, recipients, msg.as_string())
    else:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            if user:
                s.login(user, pw)
            s.sendmail(sender, recipients, msg.as_string())
    print("Sent monthly brief to %d recipient(s)." % len(recipients))


if __name__ == "__main__":
    main()
