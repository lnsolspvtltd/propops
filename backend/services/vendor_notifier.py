"""Notify vendors of new job assignments via email."""
import logging

from backend.services.email_sender import send_email

logger = logging.getLogger(__name__)


async def notify_vendor(
    vendor_email: str,
    vendor_name: str,
    incident_title: str,
    incident_summary: str | None,
    tenant_name: str | None,
    unit_label: str | None,
    pm_contact_email: str,
) -> bool:
    """Send job assignment email to vendor. Returns True on success, False on failure."""
    subject = f"New job assigned: {incident_title}"
    lines = [
        f"Hi {vendor_name},",
        "",
        "A new maintenance job has been assigned to you.",
        "",
        f"Issue: {incident_title}",
    ]
    if incident_summary:
        lines.append(f"Details: {incident_summary}")
    if tenant_name:
        lines.append(f"Tenant: {tenant_name}")
    if unit_label:
        lines.append(f"Unit: {unit_label}")
    lines += ["", f"Contact the property manager at {pm_contact_email}.", "", "PropOps"]
    try:
        await send_email(to=vendor_email, subject=subject, body="\n".join(lines))
        logger.info("vendor_notifier: notified %s", vendor_email)
        return True
    except Exception as e:
        logger.error("vendor_notifier: failed to notify %s: %s", vendor_email, e)
        return False
