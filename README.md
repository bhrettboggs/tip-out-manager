# Tip-Out Manager

A web app that calculates end-of-shift tip-outs for restaurant servers and tracks the staff and schedules behind them. Each restaurant defines its own tip-out positions (bar, server assistants, food runners, and so on), each with its own percentage. The app works out what every server owes each position and keeps a dated record of every tip-out.

It can pull each server's alcohol and food sales from the Toast POS API. If Toast isn't connected, a manager types the sales in by hand.

Built with **FastAPI**, **SQLAlchemy**, and **SQLite**. The pages are server-rendered HTML, so there's no front-end build step.

## How the tip-out is calculated

Each restaurant sets up any number of **tip positions**. Every position has a percentage and a calculation base:

| Calculation base | Applied to |
|---|---|
| Food Sales | The server's food sales during the shift |
| Alcohol Sales | The server's alcohol sales |
| Total Sales | Food + alcohol |

For each server, each shift, and each active position:

```
position_total = base_amount × position%
per_person     = position_total ÷ number_of_staff_in_that_position
server_keeps   = server_tips − sum of all position_totals
```

A position with zero staff on shift is skipped.

## Features

- **Custom tip positions.** Add or remove positions and their percentages per restaurant.
- **Employee management.** Employee records with roles (server, tip recipient, manager), activation and deactivation.
- **Scheduling.** Daily and weekly schedules, plus bulk scheduling.
- **Daily status dashboard.** Shows which servers are done, still working, or off today, with running totals.
- **Quick tip-out.** Run tip-outs for one server or for everyone on shift at once, plus a shift summary.
- **Toast integration.** Fills in each server's sales and shift times from Toast.
- **Manual entry fallback.** If Toast is down or not set up, the same form takes sales numbers by hand.
- **Reports.** Weekly reports, trend analysis and performance reports.
- **Payroll export.** Export tip-out data as CSV for payroll.
- **Delete.** Remove a tip-out after it's saved.

## Project structure

```
toast_project/
├── main.py               # The app: models, Toast client, routes, and HTML/CSS
├── mock_toast_server.py  # Fake Toast API on port 8001 for local testing
├── installer.py          # Optional setup: installs dependencies, creates .env and folders
├── fix_database.py       # One-off migration for databases created before server_employee_id existed
├── debug_database.py     # Prints the tables and rows in the database
├── setup.py              # Package metadata
├── start_unix.sh         # Start script for Mac/Linux
├── start_windows.bat     # Start script for Windows
└── requirements.txt      # Python dependencies
```

## Getting started

Requires Python 3.10+.

```bash
git clone https://github.com/bhrettboggs/tip-out-manager.git
cd tip-out-manager/toast_project
pip install -r requirements.txt
python main.py
```

Then open **http://localhost:8080**. The SQLite database (`tipout_management.db`) is created the first time the app runs. On Windows you can double-click `start_windows.bat`; on Mac/Linux run `./start_unix.sh`.

### Trying it with the mock Toast server

`main.py` points its Toast client at `http://localhost:8001`, the mock server, rather than the real Toast API. To test the Toast flow:

1. In a second terminal, run `python mock_toast_server.py`.
2. Register a restaurant named **My Test Restaurant**. Enter any value for the Toast client ID and secret, and enter `My Test Restaurant` as the restaurant GUID.
3. Add the servers `Alice, Bob, Charlie, Sarah`.
4. Calculate a tip-out for one of them on **2025-09-26**. The sales and shift times fill in from the mock data.

### Useful URLs

| URL | What it shows |
|---|---|
| `/` | Home: log in or register a restaurant |
| `/debug` | JSON health check with restaurant, position and tip-out counts |
| `/docs` | FastAPI's auto-generated API docs |

## Known limitations

This is a personal project, not production software.

- **No real authentication.** Logging in only requires the restaurant name.
- **Toast credentials are stored in plain text** in the SQLite database.
- **The Toast base URL is hard-coded** to the mock server. Connecting to the real Toast API means changing `base_url` in the `ToastAPI` class.
- **Employee contact details and wage rates are stored unencrypted.** Don't deploy this with real staff data on a shared machine.
- `main.py` is a single ~7,400-line file; splitting routes, models and templates into modules is the obvious next refactor.

## License

MIT. See [LICENSE](LICENSE).
