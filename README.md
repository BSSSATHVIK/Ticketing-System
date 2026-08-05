# Ticketing System Databricks App

A Flask-based Databricks App that lets users create support tickets, assign priority, filter by status, and add messages to those tickets. All operational data lives in Lakebase.

## What it includes

- Browser UI for creating tickets, setting priority, filtering by status, and posting ticket messages
- `tickets` table in Lakebase
- `ticket_messages` table in Lakebase
- JSON endpoints for listing tickets and reading a ticket with its messages

## Files

- `app.py` - Flask app and Lakebase-backed ticket/message routes
- `templates/index.html` - UI for tickets and messages
- `lakebase.py` - Lakebase connection helper
- `app.yaml` - Databricks App deployment config

## Endpoints

- `GET /healthz` - health check
- `GET /tickets` - list all tickets
- `GET /tickets?status=open` - list tickets filtered by status
- `POST /tickets` - create a ticket
- `GET /tickets/<ticket_id>` - get one ticket plus its messages
- `PATCH /tickets/<ticket_id>` - update ticket status or priority
- `POST /tickets/<ticket_id>/messages` - add a message to a ticket

## Lakebase tables

The app creates these tables if they do not exist:

```sql
CREATE TABLE tickets (
  ticket_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  priority TEXT NOT NULL DEFAULT 'medium',
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ticket_messages (
  message_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
  message_text TEXT NOT NULL,
  author TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Run locally

```bash
python app.py
```

If you are running outside Databricks, set `LOCAL_USER_EMAIL` to control the fallback user identity.
