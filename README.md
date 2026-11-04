# Tip-Out Manager

A small web app that calculates end-of-shift tip-outs for restaurant servers. Each restaurant sets its own tip-out percentages. The app then works out what each server owes the bar and the service assistants, and keeps a daily record of every tip-out.

It can pull each server's alcohol and food sales from the Toast POS API. If Toast isn't connected, a manager types the sales in by hand.

Built with **FastAPI**, **SQLAlchemy**, and **SQLite**. The pages are server-rendered HTML, so there's no front-end build step.

## How the tip-out is calculated

Each restaurant stores two percentages:

| Setting | Applied to |
|---|---|
| Bartender % | The server's total **alcohol** sales |
| Assistant % | The server's **food** sales during the shift |

For each server and each shift:

```
bartender_tipout     = alcohol_sales × bartender%
assistant_pool       = food_sales × assistant%
assistant_per_person = assistant_pool ÷ number_of_assistants
total_tipout         = bartender_tipout + assistant_per_person
server_keeps         = server_tips − total_tipout
```

## Features

- **Restaurant accounts.** Register a restaurant with its tip-out percentages, server roster, and optional Toast API credentials.
- **Daily status dashboard.** Shows every server's status for today (done, still working, or not on shift) with a progress bar and running bartender and assistant totals.
- **Toast integration.** Fills in each server's sales and shift times from Toast, and uses Toast to see who's working today.
- **Manual entry fallback.** If Toast is down or not set up, the same form takes sales numbers by hand.
- **Duplicate protection.** Re-running a tip-out for the same server and date warns you, then updates the record instead of creating a second one.
- **Daily totals.** A summary of all tip-outs for any date.
- **Edit and delete.** Fix or remove a tip-out after it's saved. Deleting asks for confirmation.
- **Settings.** Change percentages, the server list, or Toast credentials at any time.

## Project structure

```
toast_project/
├── main.py               # The app: models, Toast client, routes, and HTML/CSS
├── mock_toast_server.py  # Fake Toast API on port 8001 for local testing
├── reset_database.py     # Deletes and recreates tipout_management.db
├── debug_database.py     # Prints the tables and rows in the database
├── simple_app.py         # Earlier stripped-down version (no Toast, fresh DB each run)
└── test_app.py           # Minimal FastAPI page used to debug setup issues
```

## Getting started

Requires Python 3.10+.

```bash
git clone https://github.com/bhrettboggs/tip-out-manager.git
cd tip-out-manager/toast_project
pip install fastapi uvicorn sqlalchemy httpx python-multipart
```

Start the app:

```bash
python main.py
```

Then open **http://localhost:8080**. The SQLite database (`tipout_management.db`) is created the first time the app runs.

### Trying it with the mock Toast server

`main.py` currently points its Toast client at `http://localhost:8001`, the mock server, rather than the real Toast API. To test the Toast flow:

1. In a second terminal, run `python mock_toast_server.py`.
2. Register a restaurant named **My Test Restaurant**. Enter any value for the Toast client ID and secret, and enter `My Test Restaurant` as the restaurant GUID.
3. Add the servers `Alice, Bob, Charlie, Sarah`.
4. Calculate a tip-out for one of them on **2025-09-26**. The sales and shift times fill in from the mock data.

### Useful URLs

| URL | What it shows |
|---|---|
| `/` | Home: log in or register a restaurant |
| `/debug` | JSON health check with restaurant and tip-out counts |
| `/docs` | FastAPI's auto-generated API docs |

## Known limitations

This is a class and personal project, not production software.

- **No real authentication.** Logging in only requires the restaurant name.
- **Toast credentials are stored in plain text** in the SQLite database.
- **The Toast base URL is hard-coded** to the mock server. Connecting to the real Toast API means changing `base_url` in the `ToastAPI` class.
- The daily status dashboard always shows **today's** date.

## License

MIT. See [LICENSE](LICENSE).
