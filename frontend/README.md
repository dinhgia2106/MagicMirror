# Holiday Manager Frontend

Web-based control panel for managing MagicMirror holidays.

## Quick Start

1. Start the backend server first
2. Open `index.html` in browser
3. Configure API URL in settings panel (bottom-right)

## Configuration

Edit `config.json`:

```json
{
  "apiUrl": "http://localhost:8000",
  "language": "vi",
  "dateFormat": "DD/MM/YYYY",
  "theme": "dark"
}
```

## Features

- Add/Edit/Delete holidays
- Filter by type (Solar/Lunar/Rule-based)
- Search holidays
- Dark theme UI
- Vietnamese language support

## Project Structure

```
frontend/
├── index.html          # Main page
├── config.json         # Configuration
├── css/
│   ├── style.css       # Main styles
│   ├── form.css        # Form styles
│   └── list.css        # List styles
└── js/
    ├── config.js       # Config loader
    ├── api.js          # API client
    ├── ui.js           # UI rendering
    └── app.js          # Main logic
```

## Network Access

To access from another device on the same network:

1. Edit `config.json`:
   ```json
   {
     "apiUrl": "http://192.168.1.x:8000"
   }
   ```
2. Or use the settings panel in the UI
