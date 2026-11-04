# mock_toast_server.py
# Run this on port 8001 to simulate Toast API responses

from fastapi import FastAPI, Query
import uvicorn

app = FastAPI(title="Mock Toast API Server")

# Hardcoded mock data for "My Test Restaurant" on 2025-09-22
MOCK_RESTAURANT_DATA = {
    "my test restaurant": {
        "2025-09-26": {
            "Alice": {
                "beer_sales": 120.00,
                "beer_count": 20,
                "liquor_sales": 80.00,
                "liquor_count": 10,
                "wine_sales": 60.00,
                "wine_count": 8,
                "total_alcohol_sales": 260.00,
                "total_food_sales": 300.00,
                "start_time": "17:00",
                "end_time": "23:00"
            },
            "Bob": {
                "beer_sales": 90.00,
                "beer_count": 15,
                "liquor_sales": 100.00,
                "liquor_count": 12,
                "wine_sales": 40.00,
                "wine_count": 5,
                "total_alcohol_sales": 230.00,
                "total_food_sales": 250.00,
                "start_time": "16:00",
                "end_time": "22:00"
            },
            "Charlie": {
                "beer_sales": 60.00,
                "beer_count": 10,
                "liquor_sales": 70.00,
                "liquor_count": 8,
                "wine_sales": 30.00,
                "wine_count": 4,
                "total_alcohol_sales": 160.00,
                "total_food_sales": 200.00,
                "start_time": "18:00",
                "end_time": "00:00"
            },
            "Sarah": {
                "beer_sales": 30.00,
                "beer_count": 5,
                "liquor_sales": 40.00,
                "liquor_count": 4,
                "wine_sales": 20.00,
                "wine_count": 2,
                "total_alcohol_sales": 90.00,
                "total_food_sales": 100.00,
                "start_time": "15:00",
                "end_time": "21:00"
            }
        }
    }
}

@app.post("/authentication/v1/authentication/login")
async def mock_login(credentials: dict):
    return {
        "token": {
            "accessToken": "mock_token_12345",
            "tokenType": "Bearer"
        }
    }

@app.get("/orders/v2/orders")
async def mock_orders(
    businessDate: str = None,
    startDate: str = None,
    endDate: str = None,
    server_name: str = Query(None),
    restaurant_name: str = Query(None)
):
    # Print received parameters for debugging
    print(f"Received: restaurant_name={restaurant_name}, server_name={server_name}, businessDate={businessDate}")
    # Print available keys for debugging
    print("Available restaurants:", list(MOCK_RESTAURANT_DATA.keys()))
    print("Available dates:", list(MOCK_RESTAURANT_DATA.get((restaurant_name or "my test restaurant").strip().lower(), {}).keys()))
    print("Available servers:", list(MOCK_RESTAURANT_DATA.get((restaurant_name or "my test restaurant").strip().lower(), {}).get((businessDate or startDate or "2025-09-22").strip(), {}).keys()))

    # Use businessDate or startDate for date
    date = (businessDate or startDate or "2025-09-22").strip()
    rest_name = (restaurant_name or "my test restaurant").strip().lower()
    server_key = (server_name or "").strip().lower()

    # Case-insensitive lookup for restaurant and server
    if rest_name in MOCK_RESTAURANT_DATA and date in MOCK_RESTAURANT_DATA[rest_name]:
        # Find matching server (case-insensitive)
        server_map = {k.lower(): k for k in MOCK_RESTAURANT_DATA[rest_name][date].keys()}
        if server_key and server_key in server_map:
            actual_server = server_map[server_key]
            totals = MOCK_RESTAURANT_DATA[rest_name][date][actual_server]
            return {
                "data": [],
                "totals": totals
            }
        else:
            # Return combined totals for all servers
            combined = {
                "beer_sales": 0,
                "beer_count": 0,
                "liquor_sales": 0,
                "liquor_count": 0,
                "wine_sales": 0,
                "wine_count": 0,
                "total_alcohol_sales": 0,
                "total_food_sales": 0,
                "start_time": None,
                "end_time": None
            }
            for sdata in MOCK_RESTAURANT_DATA[rest_name][date].values():
                for k in ["beer_sales", "beer_count", "liquor_sales", "liquor_count", "wine_sales", "wine_count", "total_alcohol_sales", "total_food_sales"]:
                    combined[k] += sdata[k]
            # For combined, set start_time and end_time to earliest/latest
            start_times = [sdata["start_time"] for sdata in MOCK_RESTAURANT_DATA[rest_name][date].values()]
            end_times = [sdata["end_time"] for sdata in MOCK_RESTAURANT_DATA[rest_name][date].values()]
            combined["start_time"] = min(start_times)
            combined["end_time"] = max(end_times)
            return {
                "data": [],
                "totals": combined
            }
    # Otherwise, return zeros
    return {
        "data": [],
        "totals": {
            "beer_sales": 0,
            "beer_count": 0,
            "liquor_sales": 0,
            "liquor_count": 0,
            "wine_sales": 0,
            "wine_count": 0,
            "total_alcohol_sales": 0,
            "total_food_sales": 0,
            "start_time": None,
            "end_time": None
        }
    }

@app.get("/")
async def mock_status():
    return {
        "status": "Mock Toast API Server Running",
        "message": "This is a test server simulating Toast API responses",
        "endpoints": [
            "POST /authentication/v1/authentication/login",
            "GET /orders/v2/orders"
        ]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)