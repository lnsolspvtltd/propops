import imaplib
import logging
from email.parser import BytesParser
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.core.security import decrypt
import asyncio

logger = logging.getLogger(__name__)

_polling_task = None
_stop_polling = False

def poll_imap(
    host: str,
    port: int,
    username: str,
    password_enc: str,
    db: Session,
):
    try:
        # Decrypt password
        password = decrypt(password_enc)

        # Connect to IMAP server
        imap = imaplib.IMAP4_SSL(host, port)
        imap.login(username, password)

        # Select inbox
        imap.select("INBOX")

        # Search for unread messages
        status, data = imap.search(None, "UNSEEN")
        if not data:
            return False

        # Process each message
        for num in data[0].split():
            _, msg_data = imap.fetch(num, "(RFC822)")
            msg = BytesParser().parsebytes(msg_data[0][1])

            # Extract relevant information (example: subject and sender)
            subject = msg['subject']
            sender = msg['from']

            # Log the message details
            logger.info(f"New message received: Subject: {subject}, Sender: {sender}")

        return True

    except Exception as e:
        logger.error(f"Error polling IMAP: {e}", exc_info=True)
        return False

async def start_inbox_poller():
    global _polling_task, _stop_polling
    _stop_polling = False
    logger.info("Starting inbox poller")
    # Placeholder for background polling task
    # In a real implementation, this would start a background task
    # that periodically calls poll_imap for configured accounts
    pass

async def stop_inbox_poller():
    global _polling_task, _stop_polling
    _stop_polling = True
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    logger.info("Stopped inbox poller")