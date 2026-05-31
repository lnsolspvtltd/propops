import imaplib
from email.parser import BytesParser
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.crypto import decrypt
import logging

logger = logging.getLogger(__name__)

async def poll_imap(
    host: str,
    port: int,
    username: str,
    password_enc: str,
    db: AsyncSession,
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
        if not data or not data[0]:
            imap.logout()
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

        # Logout from IMAP server
        imap.logout()
        return True

    except Exception as e:
        logger.error(f"Error polling IMAP: {e}", exc_info=True)
        return False