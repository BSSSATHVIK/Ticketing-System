"""
Databricks App for a simple support ticketing system.

The app stores operational data in Lakebase and provides:
- a browser UI for creating tickets and posting messages
- JSON endpoints for listing tickets and reading ticket details

Run locally:
    python app.py
"""

from __future__ import annotations

import logging
import os
import uuid
from http import HTTPStatus

from databricks.sdk import WorkspaceClient
from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ticketing-app")

app = Flask(__name__)
_w = WorkspaceClient()

TICKETS_TABLE_NAME = os.environ.get("TICKETS_TABLE_NAME", "tickets")
TICKET_MSG_TABLE_NAME = os.environ.get("TICKET_MSG_TABLE_NAME", "ticket_messages")
ALLOWED_STATUSES = {"open", "in_progress", "resolved", "closed"}


def ensure_tickets_table() -> None:
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TICKETS_TABLE_NAME} (
            ticket_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def ensure_ticket_msg_table() -> None:
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TICKET_MSG_TABLE_NAME} (
            message_id TEXT PRIMARY KEY,
            ticket_id TEXT NOT NULL REFERENCES {TICKETS_TABLE_NAME}(ticket_id) ON DELETE CASCADE,
            message_text TEXT NOT NULL,
            author TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def ensure_schema() -> None:
    ensure_tickets_table()
    ensure_ticket_msg_table()


def _current_user_email() -> str:
    header_email = request.headers.get("X-Forwarded-Email")
    if header_email:
        return header_email
    try:
        return _w.current_user.me().user_name
    except Exception:
        return os.getenv("LOCAL_USER_EMAIL", "local-user@example.com")


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    form_data = request.form.to_dict()
    return form_data if isinstance(form_data, dict) else {}


def _normalize_status(value: str | None) -> str:
    status = (value or "open").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {value!r}")
    return status


def _ticket_row(ticket_id: str):
    rows = lakebase.run_query(
        f"""
        SELECT ticket_id, title, status, created_by, created_at
        FROM {TICKETS_TABLE_NAME}
        WHERE ticket_id = %s
        """,
        (ticket_id,),
    )
    return rows[0] if rows else None


def _message_rows(ticket_id: str):
    return lakebase.run_query(
        f"""
        SELECT message_id, ticket_id, message_text, author, created_at
        FROM {TICKET_MSG_TABLE_NAME}
        WHERE ticket_id = %s
        ORDER BY created_at ASC
        """,
        (ticket_id,),
    )


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(HTTPException)
def handle_http_exception(err: HTTPException):
    return jsonify({"error": err.description}), err.code


@app.errorhandler(Exception)
def handle_exception(err):
    logger.exception("Unhandled exception while processing request")
    return jsonify({"error": "Internal server error"}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/tickets", methods=["GET"])
def list_tickets():
    ensure_schema()
    rows = lakebase.run_query(
        f"""
        SELECT
            t.ticket_id,
            t.title,
            t.status,
            t.created_by,
            t.created_at,
            COUNT(m.message_id)::int AS message_count
        FROM {TICKETS_TABLE_NAME} t
        LEFT JOIN {TICKET_MSG_TABLE_NAME} m ON m.ticket_id = t.ticket_id
        GROUP BY t.ticket_id, t.title, t.status, t.created_by, t.created_at
        ORDER BY t.created_at DESC
        """
    )
    return jsonify(rows)


@app.route("/tickets", methods=["POST"])
def create_ticket():
    ensure_schema()
    data = _payload()
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    try:
        status = _normalize_status(data.get("status"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    created_by = str(data.get("created_by", "")).strip() or _current_user_email()
    ticket_id = str(uuid.uuid4())

    lakebase.run_write(
        f"""
        INSERT INTO {TICKETS_TABLE_NAME} (ticket_id, title, status, created_by)
        VALUES (%s, %s, %s, %s)
        """,
        (ticket_id, title, status, created_by),
    )

    return jsonify(_ticket_row(ticket_id)), 201


@app.route("/tickets/<ticket_id>", methods=["GET"])
def get_ticket(ticket_id: str):
    ensure_schema()
    ticket = _ticket_row(ticket_id)
    if ticket is None:
        abort(404, description="Ticket not found")
    return jsonify({"ticket": ticket, "messages": _message_rows(ticket_id)})


@app.route("/tickets/<ticket_id>/messages", methods=["POST"])
def add_message(ticket_id: str):
    ensure_schema()
    ticket = _ticket_row(ticket_id)
    if ticket is None:
        abort(404, description="Ticket not found")

    data = _payload()
    message_text = str(data.get("message_text", "")).strip()
    if not message_text:
        return jsonify({"error": "Message text is required"}), 400

    author = str(data.get("author", "")).strip() or _current_user_email()
    message_id = str(uuid.uuid4())

    lakebase.run_write(
        f"""
        INSERT INTO {TICKET_MSG_TABLE_NAME} (message_id, ticket_id, message_text, author)
        VALUES (%s, %s, %s, %s)
        """,
        (message_id, ticket_id, message_text, author),
    )

    return jsonify({"message_id": message_id, "ticket_id": ticket_id}), 201


@app.route("/records")
def redirect_records():
    return jsonify({"error": "Use /tickets for this app"}), 410


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", "8000"))
    app.run(debug=True, host=host, port=port)
