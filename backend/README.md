# Holiday Management Backend

Flask REST API for managing MagicMirror holidays.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python app.py
```

Server runs on `http://0.0.0.0:8000`

## Configuration

Edit `config.env`:

```env
HOLIDAY_API_HOST=0.0.0.0
HOLIDAY_API_PORT=8000
HOLIDAY_API_DEBUG=false
CORS_ORIGINS=*
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/holidays` | List all |
| GET | `/api/holidays?q=text` | Search |
| GET | `/api/holidays/:id` | Get one |
| POST | `/api/holidays` | Create |
| PUT | `/api/holidays/:id` | Update |
| DELETE | `/api/holidays/:id` | Delete |

## Project Structure

```
backend/
├── app.py              # Entry point
├── config.env          # Configuration
├── requirements.txt    # Dependencies
├── config/
│   └── settings.py     # Settings loader
├── models/
│   └── holiday.py      # Data models
├── services/
│   └── holiday_service.py  # Business logic
├── routes/
│   └── holidays.py     # API routes
└── data/
    └── holidays.json   # Data storage
```

## Holiday Types

- **solar**: Fixed date (month/day)
- **lunar**: Lunar calendar date
- **specific**: One-time event (year/month/day)
- **rule**: Pattern-based (e.g., 2nd Monday of May)
