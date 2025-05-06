# Module de notifications (email et Slack)
import smtplib
from email.mime.text import MIMEText
import requests

def send_email_notification(subject, body, to_email, smtp_server, smtp_port, smtp_user, smtp_password):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = to_email
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"Erreur envoi email: {e}")
        return False

def send_slack_notification(webhook_url, message):
    try:
        response = requests.post(webhook_url, json={"text": message})
        return response.status_code == 200
    except Exception as e:
        print(f"Erreur envoi Slack: {e}")
        return False
