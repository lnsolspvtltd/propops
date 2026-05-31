import imaplib
import asyncio
import logging
from email.parser import BytesParser
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.security import decrypt

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

        # Connect to IMAP server (run blocking operations in thread pool)
        imap = await asyncio.to_thread(imaplib.IMAP4_SSL, host, port)
        await asyncio.to_thread(imap.login, username, password)

        # Select inbox
        await asyncio.to_thread(imap.select, "INBOX")

        # Search for unread messages
        status, data = await asyncio.to_thread(imap.search, None, "UNSEEN")
        if not data:
            return False

        # Process each message
        for num in data[0].split():
            _, msg_data = await asyncio.to_thread(imap.fetch, num, "(RFC822)")
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