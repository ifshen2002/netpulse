"""Notification subscription matching and in-app delivery."""

import json
import logging

from sqlalchemy import text

from services.auth import new_id

logger = logging.getLogger(__name__)


async def match_and_deliver(
    conn,
    *,
    alert_id: str,
    incident_id: str | None,
    project_id: str | None,
    alert_type: str,
    message: str,
    severity: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> int:
    """Find matching subscriptions and create in-app notifications. Returns count delivered."""
    if not project_id:
        return 0

    rows = (await conn.execute(
        text(
            "SELECT id, user_id FROM notification_subscriptions "
            "WHERE project_id = :project_id AND enabled = true "
            "AND (resource_type IS NULL OR resource_type = :resource_type) "
            "AND (severity IS NULL OR severity = :severity)"
        ),
        {
            "project_id": project_id,
            "resource_type": resource_type,
            "severity": severity,
        },
    )).fetchall()

    delivered = 0
    for row in rows:
        user_id = row[1]
        notification_id = new_id()
        title = f"[{severity.upper()}] {alert_type}"
        body = message
        await conn.execute(
            text(
                "INSERT INTO in_app_notifications "
                "(id, user_id, alert_id, incident_id, project_id, title, body, severity, status, created_at) "
                "VALUES (:id, :user_id, :alert_id, :incident_id, :project_id, :title, :body, :severity, 'unread', NOW())"
            ),
            {
                "id": notification_id,
                "user_id": user_id,
                "alert_id": alert_id,
                "incident_id": incident_id,
                "project_id": project_id,
                "title": title,
                "body": body,
                "severity": severity,
            },
        )
        delivered += 1

    return delivered


async def broadcast_notification(manager, notification_id: str, user_id: str, title: str, body: str, severity: str, alert_id: str, incident_id: str | None, project_id: str) -> None:
    """Push a notification_created event to the target user's connections only."""
    await manager.broadcast(
        json.dumps(
            {
                "type": "notification_created",
                "notification_id": notification_id,
                "user_id": user_id,
                "title": title,
                "body": body,
                "severity": severity,
                "alert_id": alert_id,
                "incident_id": incident_id,
                "project_id": project_id,
            }
        ),
        user_id=user_id,
    )
