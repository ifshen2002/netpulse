"""V2 alert rule management REST API."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from db import engine
from services.alerting import reload_rules

router = APIRouter(prefix="/api", tags=["alert-rules"])

VALID_METRICS = {"latency", "packet_loss", "availability"}
VALID_OPERATORS = {">", "<", ">=", "<="}
VALID_SEVERITIES = {"warning", "critical"}


class AlertRuleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    metric: str
    operator: str
    threshold: float
    severity: str = "critical"

    @field_validator("metric")
    @classmethod
    def _metric_valid(cls, v: str) -> str:
        if v not in VALID_METRICS:
            raise ValueError(f"metric must be one of: {', '.join(sorted(VALID_METRICS))}")
        return v

    @field_validator("operator")
    @classmethod
    def _operator_valid(cls, v: str) -> str:
        if v not in VALID_OPERATORS:
            raise ValueError(f"operator must be one of: {', '.join(sorted(VALID_OPERATORS))}")
        return v

    @field_validator("severity")
    @classmethod
    def _severity_valid(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(VALID_SEVERITIES))}")
        return v


class AlertRuleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    metric: str | None = None
    operator: str | None = None
    threshold: float | None = None
    severity: str | None = None
    enabled: bool | None = None

    @field_validator("metric")
    @classmethod
    def _metric_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_METRICS:
            raise ValueError(f"metric must be one of: {', '.join(sorted(VALID_METRICS))}")
        return v

    @field_validator("operator")
    @classmethod
    def _operator_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_OPERATORS:
            raise ValueError(f"operator must be one of: {', '.join(sorted(VALID_OPERATORS))}")
        return v

    @field_validator("severity")
    @classmethod
    def _severity_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(VALID_SEVERITIES))}")
        return v


def _row_to_rule(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "metric": row[2],
        "operator": row[3],
        "threshold": float(row[4]),
        "severity": row[5],
        "enabled": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
    }


def _next_rule_id(num: int) -> str:
    if num <= 26:
        return f"rule-{chr(96 + num)}"
    return f"rule-{num}"


@router.get("/alert-rules")
async def list_alert_rules():
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                "SELECT id, name, metric, operator, threshold, severity, enabled, created_at "
                "FROM alert_rules ORDER BY created_at"
            )
        )).fetchall()

    return {"success": True, "data": [_row_to_rule(r) for r in rows]}


@router.get("/alert-rules/{rule_id}")
async def get_alert_rule(rule_id: str):
    async with engine.begin() as conn:
        row = (await conn.execute(
            text(
                "SELECT id, name, metric, operator, threshold, severity, enabled, created_at "
                "FROM alert_rules WHERE id = :id"
            ),
            {"id": rule_id},
        )).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Alert rule not found")

    return {"success": True, "data": _row_to_rule(row)}


@router.post("/alert-rules", status_code=201)
async def create_alert_rule(body: AlertRuleCreateIn):
    async with engine.begin() as conn:
        count = (await conn.execute(text("SELECT COUNT(*) FROM alert_rules"))).fetchone()[0]

        # Generate ID from name slug or sequential letter
        name_slug = body.name.lower().replace(" ", "-")[:40]
        existing = (await conn.execute(
            text("SELECT 1 FROM alert_rules WHERE id = :id"),
            {"id": name_slug},
        )).fetchone()

        if existing:
            rule_id = _next_rule_id(count + 1)
        else:
            rule_id = name_slug

        now = datetime.now(timezone.utc)
        await conn.execute(
            text(
                "INSERT INTO alert_rules "
                "(id, name, metric, operator, threshold, severity, enabled, created_at) "
                "VALUES (:id, :name, :metric, :operator, :threshold, :severity, :enabled, :now)"
            ),
            {
                "id": rule_id, "name": body.name, "metric": body.metric,
                "operator": body.operator, "threshold": body.threshold,
                "severity": body.severity, "enabled": True, "now": now,
            },
        )

    await reload_rules()
    return {"success": True, "data": {"id": rule_id, "name": body.name}}


@router.put("/alert-rules/{rule_id}")
async def update_alert_rule(rule_id: str, body: AlertRuleUpdateIn):
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text(
                "SELECT id, name, metric, operator, threshold, "
                "severity, enabled FROM alert_rules WHERE id = :id"
            ),
            {"id": rule_id},
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Alert rule not found")

        updates = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.metric is not None:
            updates["metric"] = body.metric
        if body.operator is not None:
            updates["operator"] = body.operator
        if body.threshold is not None:
            updates["threshold"] = body.threshold
        if body.severity is not None:
            updates["severity"] = body.severity
        if body.enabled is not None:
            updates["enabled"] = body.enabled

        if updates:
            set_clause = ", ".join(k + " = :" + k for k in updates)
            await conn.execute(
                text("UPDATE alert_rules SET " + set_clause + " WHERE id = :id"),  # nosec B608
                {**updates, "id": rule_id},
            )

    await reload_rules()
    return {"success": True, "data": {"id": rule_id, **updates}}


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    async with engine.begin() as conn:
        result = await conn.execute(
            text("DELETE FROM alert_rules WHERE id = :id"), {"id": rule_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert rule not found")

    await reload_rules()
    return {"success": True, "data": {"deleted": rule_id}}


@router.patch("/alert-rules/{rule_id}/toggle")
async def toggle_alert_rule(rule_id: str):
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT enabled FROM alert_rules WHERE id = :id"), {"id": rule_id}
        )).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Alert rule not found")

        new_val = not existing[0]
        await conn.execute(
            text("UPDATE alert_rules SET enabled = :enabled WHERE id = :id"),
            {"enabled": new_val, "id": rule_id},
        )

    await reload_rules()
    return {"success": True, "data": {"id": rule_id, "enabled": new_val}}
