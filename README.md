# EventHub API

A Django REST Framework API for browsing events, reserving seats, and cancelling reservations.

## Run locally

Requirements: Python 3.12 or newer.

```powershell
# From the repository root
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The local API runs at `http://127.0.0.1:8000/api/`. Django's browsable API is enabled for convenient manual requests. Request logs are written to the server console.

## Endpoints

| Method                  | URL                              | Description                               |
| ----------------------- | -------------------------------- | ----------------------------------------- |
| GET, POST               | `/api/events/`                   | List events or create an event            |
| GET, PUT, PATCH, DELETE | `/api/events/{id}/`              | Retrieve, update, or delete an event      |
| GET, POST               | `/api/reservations/`             | List reservations or reserve seats        |
| GET, PUT, PATCH, DELETE | `/api/reservations/{id}/`        | Retrieve, update, or delete a reservation |
| POST                    | `/api/reservations/{id}/cancel/` | Cancel a reservation and restore seats    |

Event list filters: `?status=upcoming`, `?venue=bangalore` (case-insensitive), or both.
Reservation list filter: `?event_id=1`.

## Example requests

Create an event:

```json
{
  "title": "PyCon India 2026",
  "venue": "NIMHANS Convention Centre, Bangalore",
  "date": "2026-09-20",
  "total_seats": 500,
  "available_seats": 500,
  "status": "upcoming"
}
```

Reserve seats:

```json
{
  "event": 1,
  "attendee_name": "Priya Sharma",
  "attendee_email": "priya@example.com",
  "seats_reserved": 2
}
```

Cancel with an empty POST body to `/api/reservations/1/cancel/`.

## Design decision

Seat deductions, reservation creation, edits, and cancellations run in database transactions. Reservation creation locks and rechecks the event row before changing availability, so simultaneous requests cannot both rely on the same stale seat count on databases with row-level locking. SQLite serializes writes differently, so PostgreSQL is recommended for a production deployment with concurrent booking traffic.

API screenshots available below
https://app.notion.com/p/Event-hub-4005d101bf1680939694c725ab156b3d?source=copy_link
