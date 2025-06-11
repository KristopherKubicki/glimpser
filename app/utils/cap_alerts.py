"""Utilities for sending Common Alerting Protocol (CAP) messages."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from app.config import CAP_ENABLED, CAP_ENDPOINT, CAP_SENDER


def build_cap_message(event_type: str, description: str) -> bytes:
    """Return a minimal CAP XML message."""
    alert = ET.Element("alert")
    ET.SubElement(alert, "identifier").text = str(int(datetime.utcnow().timestamp()))
    ET.SubElement(alert, "sender").text = CAP_SENDER
    ET.SubElement(alert, "sent").text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.SubElement(alert, "status").text = "Actual"
    ET.SubElement(alert, "msgType").text = "Alert"
    ET.SubElement(alert, "scope").text = "Public"

    info = ET.SubElement(alert, "info")
    ET.SubElement(info, "category").text = "Safety"
    ET.SubElement(info, "event").text = event_type
    ET.SubElement(info, "urgency").text = "Immediate"
    ET.SubElement(info, "severity").text = "Minor"
    ET.SubElement(info, "certainty").text = "Observed"
    ET.SubElement(info, "description").text = description

    return ET.tostring(alert, encoding="utf-8")


def send_cap_alert(event_type: str, description: str) -> None:
    """Send a CAP alert to the configured endpoint."""
    if CAP_ENABLED.lower() != "true" or not CAP_ENDPOINT or not CAP_SENDER:
        logging.info("CAP alerts are disabled.")
        return

    xml_data = build_cap_message(event_type, description)
    try:
        requests.post(
            CAP_ENDPOINT,
            data=xml_data,
            headers={"Content-Type": "application/xml"},
            timeout=5,
        )
        logging.info("CAP alert sent successfully")
    except Exception as exc:  # requests.RequestException or others
        logging.error("Error sending CAP alert: %s", exc)


def cap_alert(event_type: str, details: str) -> None:
    """Wrapper that builds a description from event info."""
    send_cap_alert(event_type, details)
