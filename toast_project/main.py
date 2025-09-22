from fastapi import FastAPI, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from datetime import datetime
import json
import httpx
from typing import Optional, List
import asyncio
import uvicorn

app = FastAPI()

# Database setup - FIXED VERSION
DATABASE_URL = "sqlite:///./tipout_management.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models - FIXED VERSION
class Restaurant(Base):
    __tablename__ = "restaurants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    toast_client_id = Column(String, nullable=True)
    toast_client_secret = Column(String, nullable=True)
    toast_restaurant_guid = Column(String, nullable=True)
    toast_management_group_guid = Column(String, nullable=True)
    bartender_percent = Column(Float, nullable=False)
    assistant_percent = Column(Float, nullable=False)
    server_names = Column(String, nullable=False)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    tipouts = relationship("Tipout", back_populates="restaurant", cascade="all, delete-orphan")

class Tipout(Base):
    __tablename__ = "tipouts"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    server_name = Column(String, nullable=False)
    date = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    num_assistants = Column(Integer, nullable=False)
    total_alc_sales = Column(Float, nullable=False, default=0.0)
    total_food_sales = Column(Float, nullable=False, default=0.0)
    time_based_food_sales = Column(Float, nullable=False, default=0.0)
    server_tips = Column(Float, nullable=False)
    bartender_tipout = Column(Float, nullable=False)
    assistant_tipout = Column(Float, nullable=False)
    assistant_per_person = Column(Float, nullable=False)
    toast_sync = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="tipouts")

# Create tables with error handling
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully")
except Exception as e:
    print(f"❌ Database creation error: {e}")

# FIXED Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Toast API Integration - SIMPLIFIED FOR TESTING
class ToastAPI:
    def __init__(self, client_id: str, client_secret: str, restaurant_guid: str, management_group_guid: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.restaurant_guid = restaurant_guid
        self.management_group_guid = management_group_guid
        self.base_url = "http://localhost:8001"
        self.token = None

    async def get_access_token(self):
        """Get OAuth access token from Toast (or mock server)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/authentication/v1/authentication/login",
                    json={
                        "clientId": self.client_id,
                        "clientSecret": self.client_secret,
                        "userAccessType": "TOAST_MACHINE_CLIENT"
                    }
                )
                if response.status_code == 200:
                    self.token = response.json()["token"]["accessToken"]
                    return True
                return False
        except Exception as e:
            print(f"Toast auth error: {e}")
            return False

    async def get_sales_data(self, date: str, start_time: str = None, end_time: str = None, server_name: str = None):
        if not self.token:
            if not await self.get_access_token():
                return None

        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Toast-Restaurant-External-ID": self.restaurant_guid
            }
            params = {
                "businessDate": date,
                "server_name": server_name,
                "restaurant_name": self.restaurant_guid.lower()  # Use the guid as the name for mock
            }
            if start_time and end_time:
                params.update({
                    "startTime": start_time,
                    "endTime": end_time
                })
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self.base_url}/orders/v2/orders",
                    headers=headers,
                    params=params
                )
                if response.status_code != 200:
                    print(f"Toast API error: {response.status_code}")
                    return None
                orders_data = response.json()
                return orders_data.get("totals", {})
        except Exception as e:
            print(f"Toast API error: {e}")
            return None
    
    def _is_alcoholic_item(self, item):
        """Determine if an item is alcoholic"""
        item_name = item.get("name", "").lower()
        alcohol_keywords = ["beer", "wine", "cocktail", "whiskey", "vodka", "rum", "gin", 
                           "tequila", "bourbon", "scotch", "martini", "margarita", "ipa"]
        return any(keyword in item_name for keyword in alcohol_keywords)

STYLE = """
<style>
body {
    background: linear-gradient(135deg, #f8ffae 0%, #43c6ac 100%);
    font-family: 'Segoe UI', 'Arial', sans-serif;
    margin: 0;
    padding: 0;
}
.centered {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    padding: 20px;
}
h2, h3 {
    color: #2d3e50;
    font-size: 2.5em;
    margin-bottom: 0.5em;
    font-family: 'Trebuchet MS', 'Arial', sans-serif;
}
label {
    font-size: 1.2em;
    color: #2d3e50;
    font-weight: bold;
    display: block;
    margin-top: 10px;
}
input, select, button {
    font-size: 1.1em;
    padding: 0.5em;
    margin: 0.3em 0;
    border-radius: 8px;
    border: 1px solid #43c6ac;
    width: 250px;
}
input[type="number"], input[type="time"] {
    width: 120px;
}
button {
    background-color: #43c6ac;
    color: white;
    font-weight: bold;
    cursor: pointer;
    transition: background 0.2s;
    width: auto;
    padding: 0.7em 1.5em;
}
button:hover {
    background-color: #2d3e50;
}
hr {
    border: 1px solid #43c6ac;
    margin: 1em 0;
    width: 100%;
}
p, a {
    font-size: 1.2em;
    color: #2d3e50;
}
a {
    text-decoration: none;
    color: #43c6ac;
    font-weight: bold;
}
a:hover {
    color: #2d3e50;
}
.value-highlight {
    color: #e67e22;
    font-weight: bold;
    font-size: 1.2em;
}
.error {
    color: #e74c3c;
    font-weight: bold;
}
.toast-status {
    background-color: #2ecc71;
    color: white;
    padding: 10px;
    border-radius: 5px;
    margin: 10px 0;
}
.manual-entry {
    background-color: #f39c12;
    color: white;
    padding: 10px;
    border-radius: 5px;
    margin: 10px 0;
}
</style>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return STYLE + """
    <div class="centered">
    <h2>Restaurant Tipout Management</h2>
    <h3>🥂 Toast POS Integration</h3>
    <form action="/login" method="get">
        <button type="submit">Login to Existing Restaurant</button>
    </form>
    <hr>
    <form action="/register" method="get">
        <button type="submit">Register New Restaurant</button>
    </form>
    </div>
    """

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return STYLE + """
    <div class="centered">
    <h2>Restaurant Login</h2>
    <form action="/authenticate" method="post">
        <label>Restaurant Name:</label>
        <input type="text" name="restaurant_name" required><br>
        <button type="submit">Login</button>
    </form>
    <a href="/">Back to Home</a>
    </div>
    """

@app.get("/register", response_class=HTMLResponse)
def register_form():
    return STYLE + """
    <div class="centered">
    <h2>Register New Restaurant</h2>
    <form action="/create_restaurant" method="post">
        <label>Restaurant Name:</label>
        <input type="text" name="restaurant_name" required><br>
        
        <hr>
        <h3>Toast POS Integration (Optional)</h3>
        <label>Toast Client ID:</label>
        <input type="text" name="toast_client_id" placeholder="Optional - for automatic data sync"><br>
        
        <label>Toast Client Secret:</label>
        <input type="text" name="toast_client_secret" placeholder="Optional"><br>
        
        <label>Restaurant GUID:</label>
        <input type="text" name="toast_restaurant_guid" placeholder="Optional"><br>
        
        <label>Management Group GUID:</label>
        <input type="text" name="toast_management_group_guid" placeholder="Optional"><br>
        
        <hr>
        <h3>Tipout Settings</h3>
        <label>Bartender Tipout %:</label>
        <input type="number" name="bartender_percent" step="0.01" min="0" max="100" value="0.75" required><br>
        
        <label>Assistant Tipout %:</label>
        <input type="number" name="assistant_percent" step="0.01" min="0" max="100" value="0.75" required><br>
        
        <label>Server Names (comma separated):</label>
        <input type="text" name="server_names" value="Alice,Bob,Charlie,Other" required placeholder="e.g. Alice,Bob,Charlie,Other"><br>
        
        <button type="submit">Register Restaurant</button>
    </form>
    <a href="/">Back to Home</a>
    </div>
    """

@app.post("/create_restaurant", response_class=HTMLResponse)
def create_restaurant(
    restaurant_name: str = Form(...),
    toast_client_id: Optional[str] = Form(""),
    toast_client_secret: Optional[str] = Form(""),
    toast_restaurant_guid: Optional[str] = Form(""),
    toast_management_group_guid: Optional[str] = Form(""),
    bartender_percent: float = Form(...),
    assistant_percent: float = Form(...),
    server_names: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        # Check if restaurant already exists
        existing_restaurant = db.query(Restaurant).filter(Restaurant.name.ilike(restaurant_name.strip())).first()
        if existing_restaurant:
            return STYLE + f"""
            <div class="centered">
            <h3 class="error">Restaurant name "{restaurant_name}" already exists!</h3>
            <p>Please choose a different name.</p>
            <a href="/register">Try Again</a> | <a href="/">Home</a>
            </div>
            """
        
        # Parse server names
        server_list = [name.strip() for name in server_names.split(",") if name.strip()]
        if not server_list:
            return STYLE + """
            <div class="centered">
            <h3 class="error">Please provide at least one server name!</h3>
            <a href="/register">Try Again</a>
            </div>
            """
        
        # Create new restaurant
        new_restaurant = Restaurant(
            name=restaurant_name.strip(),
            toast_client_id=toast_client_id.strip() if toast_client_id.strip() else None,
            toast_client_secret=toast_client_secret.strip() if toast_client_secret.strip() else None,
            toast_restaurant_guid=toast_restaurant_guid.strip() if toast_restaurant_guid.strip() else None,
            toast_management_group_guid=toast_management_group_guid.strip() if toast_management_group_guid.strip() else None,
            bartender_percent=bartender_percent,
            assistant_percent=assistant_percent,
            server_names=json.dumps(server_list)
        )
        
        db.add(new_restaurant)
        db.commit()
        db.refresh(new_restaurant)
        
        toast_status = ""
        if toast_client_id.strip():
            toast_status = '<div class="toast-status">✅ Toast POS Integration Configured</div>'
        else:
            toast_status = '<div class="manual-entry">⚠️ Manual Entry Mode - No Toast Integration</div>'
        
        return STYLE + f"""
        <div class="centered">
        <h2>Restaurant Registered Successfully!</h2>
        {toast_status}
        <p><b>Restaurant:</b> <span class="value-highlight">{restaurant_name}</span></p>
        <p><b>Bartender Tipout:</b> <span class="value-highlight">{bartender_percent}%</span></p>
        <p><b>Assistant Tipout:</b> <span class="value-highlight">{assistant_percent}%</span></p>
        <p><b>Servers:</b> <span class="value-highlight">{', '.join(server_list)}</span></p>
        <hr>
        <form action="/authenticate" method="post">
            <input type="hidden" name="restaurant_name" value="{restaurant_name}">
            <button type="submit">Continue to Dashboard</button>
        </form>
        <a href="/">Back to Home</a>
        </div>
        """
    except Exception as e:
        print(f"Database error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Database Error</h3>
        <p>Error creating restaurant: {str(e)}</p>
        <a href="/register">Try Again</a> | <a href="/">Home</a>
        </div>
        """

@app.post("/authenticate", response_class=HTMLResponse)
def authenticate(restaurant_name: str = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.name.ilike(restaurant_name.strip())).first()
        if not restaurant:
            return STYLE + f"""
            <div class="centered">
            <h3 class="error">Restaurant "{restaurant_name}" not found!</h3>
            <a href="/login">Try Again</a> | <a href="/register">Register New</a> | <a href="/">Home</a>
            </div>
            """
        
        return restaurant_dashboard(restaurant.id, db)
    except Exception as e:
        print(f"Authentication error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Login Error</h3>
        <p>Error during login: {str(e)}</p>
        <a href="/login">Try Again</a>
        </div>
        """

def restaurant_dashboard(restaurant_id: int, db: Session):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + """
            <div class="centered">
            <h3 class="error">Restaurant not found!</h3>
            <a href="/">Home</a>
            </div>
            """
        
        toast_status = ""
        if restaurant.toast_client_id:
            toast_status = '<div class="toast-status">🔗 Toast POS Connected</div>'
        else:
            toast_status = '<div class="manual-entry">📝 Manual Entry Mode</div>'
        
        return STYLE + f"""
        <div class="centered">
        <h2>Welcome, <span class="value-highlight">{restaurant.name.upper()}</span></h2>
        {toast_status}
        
        <form action="/select_server_date" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit">📊 Calculate Tipout</button>
        </form>
        <hr>
        <form action="/totals" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <label for="date">Select Date:</label>
            <input type="date" name="date" required><br>
            <button type="submit">📈 View Total Tipout</button>
        </form>
        <hr>
        <form action="/settings" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit">⚙️ Restaurant Settings</button>
        </form>
        <a href="/">Logout</a>
        </div>
        """
    except Exception as e:
        print(f"Dashboard error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Dashboard Error</h3>
        <p>{str(e)}</p>
        <a href="/">Home</a>
        </div>
        """

@app.post("/select_server_date", response_class=HTMLResponse)
def select_server_date(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return STYLE + "<div class='centered'><h3 class='error'>Restaurant not found!</h3></div>"
    server_names = json.loads(restaurant.server_names)
    options = "".join([f"<option value='{name}'>{name}</option>" for name in server_names])
    return STYLE + f"""
    <div class="centered">
    <h2>Select Server for Tipout</h2>
    <form action="/select_day_for_server" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <label for="server_name">Server Name:</label>
        <select name="server_name" required>{options}</select><br>
        <button type="submit">Next</button>
    </form>
    <form action="/menu" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
    </form>
    </div>
    """

@app.post("/select_day_for_server", response_class=HTMLResponse)
def select_day_for_server(restaurant_id: int = Form(...), server_name: str = Form(...), db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return STYLE + "<div class='centered'><h3 class='error'>Restaurant not found!</h3></div>"
    # Default times
    start_time = "17:00"
    end_time = "23:00"
    return STYLE + f"""
    <div class="centered">
    <h2>Select Date & Shift for {server_name}</h2>
    <form action="/manual_calculate_form" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <input type="hidden" name="server_name" value="{server_name}">
        <label for="date">Date:</label>
        <input type="date" name="date" required><br>
        <label for="start_time">Start Time:</label>
        <input type="time" name="start_time" value="{start_time}" required><br>
        <label for="end_time">End Time:</label>
        <input type="time" name="end_time" value="{end_time}" required><br>
        <label for="num_assistants">Number of Service Assistants:</label>
        <input type="number" name="num_assistants" min="1" value="1" required><br>
        <button type="submit">Get Sales & Tipout Info</button>
    </form>
    <form action="/menu" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
    </form>
    </div>
    """

@app.post("/manual_calculate_form", response_class=HTMLResponse)
async def manual_calculate_form(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    num_assistants: int = Form(...),
    db: Session = Depends(get_db)
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return STYLE + "<div class='centered'><h3 class='error'>Restaurant not found!</h3></div>"

    # Default values
    alc_sales = 0.0
    food_sales_shift = 0.0
    beer_sales = liquor_sales = wine_sales = 0.0
    beer_count = liquor_count = wine_count = 0
    hours_worked = 0.0

    # If Toast integration, fetch sales data
    if restaurant.toast_client_id:
        toast_api = ToastAPI(
            restaurant.toast_client_id,
            restaurant.toast_client_secret,
            restaurant.toast_restaurant_guid,
            restaurant.toast_management_group_guid
        )
        sales_data = await toast_api.get_sales_data(
            date=date,
            start_time=start_time,
            end_time=end_time,
            server_name=server_name
        )
        if sales_data:
            alc_sales = sales_data.get("total_alcohol_sales", 0.0)
            food_sales_shift = sales_data.get("total_food_sales", 0.0)
            beer_sales = sales_data.get("beer_sales", 0.0)
            beer_count = sales_data.get("beer_count", 0)
            liquor_sales = sales_data.get("liquor_sales", 0.0)
            liquor_count = sales_data.get("liquor_count", 0)
            wine_sales = sales_data.get("wine_sales", 0.0)
            wine_count = sales_data.get("wine_count", 0)
            # Autofill times if available
            start_time = sales_data.get("start_time", start_time)
            end_time = sales_data.get("end_time", end_time)
            # Calculate hours worked
            try:
                from datetime import datetime as dt
                fmt = "%H:%M"
                t1 = dt.strptime(start_time, fmt)
                t2 = dt.strptime(end_time, fmt)
                hours_worked = (t2 - t1).seconds / 3600.0
                if hours_worked <= 0:
                    hours_worked += 24  # handle overnight shifts
            except Exception:
                hours_worked = 0.0

    return STYLE + f"""
    <div class="centered">
    <h2>Tipout & Sales Info for {server_name}</h2>
    <p><b>Date:</b> <span class="value-highlight">{date}</span></p>
    <p><b>Shift:</b> <span class="value-highlight">{start_time} - {end_time}</span></p>
    <p><b>Hours Worked:</b> <span class="value-highlight">{hours_worked:.2f}</span></p>
    <p><b>Service Assistants:</b> <span class="value-highlight">{num_assistants}</span></p>
    <hr>
    <h3>Alcohol Sales Breakdown</h3>
    <p>Beer Sales: <span class="value-highlight">${beer_sales:.2f}</span> ({beer_count} sold)</p>
    <p>Liquor Sales: <span class="value-highlight">${liquor_sales:.2f}</span> ({liquor_count} sold)</p>
    <p>Wine Sales: <span class="value-highlight">${wine_sales:.2f}</span> ({wine_count} sold)</p>
    <p><b>Total Alcohol Sales:</b> <span class="value-highlight">${alc_sales:.2f}</span></p>
    <hr>
    <p><b>Food Sales:</b> <span class="value-highlight">${food_sales_shift:.2f}</span></p>
    <form action="/manual_calculate" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <input type="hidden" name="server_name" value="{server_name}">
        <input type="hidden" name="date" value="{date}">
        <input type="hidden" name="start_time" value="{start_time}">
        <input type="hidden" name="end_time" value="{end_time}">
        <input type="hidden" name="num_assistants" value="{num_assistants}">
        <input type="hidden" name="alc_sales" value="{alc_sales:.2f}">
        <input type="hidden" name="food_sales_shift" value="{food_sales_shift:.2f}">
        <label for="server_tips">Total Server Tips ($):</label>
        <input type="number" name="server_tips" step="0.01" min="0" value="0.00" required><br>
        <button type="submit">Calculate Tipout</button>
    </form>
    <form action="/menu" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
    </form>
    </div>
    """
@app.post("/manual_calculate", response_class=HTMLResponse)
def manual_calculate(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    num_assistants: int = Form(...),
    alc_sales: float = Form(...),
    food_sales_shift: float = Form(...),
    server_tips: float = Form(...),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        
        if not restaurant:
            return STYLE + """
            <div class="centered">
            <h3 class="error">Restaurant not found!</h3>
            <a href="/">Home</a>
            </div>
            """
        
        # Calculate tipouts
        bartender_tipout = alc_sales * (restaurant.bartender_percent / 100)
        total_assistant_tipout = food_sales_shift * (restaurant.assistant_percent / 100)
        assistant_per_person = total_assistant_tipout / num_assistants
        
        total_tipout = bartender_tipout + assistant_per_person
        server_keep = server_tips - total_tipout
        
        # Save to database
        tipout = Tipout(
            restaurant_id=restaurant.id,
            server_name=server_name,
            date=date,
            start_time=start_time,
            end_time=end_time,
            num_assistants=num_assistants,
            total_alc_sales=alc_sales,
            total_food_sales=food_sales_shift,
            time_based_food_sales=food_sales_shift,
            server_tips=server_tips,
            bartender_tipout=bartender_tipout,
            assistant_tipout=total_assistant_tipout,
            assistant_per_person=assistant_per_person,
            toast_sync=False
        )
        
        db.add(tipout)
        db.commit()
        
        return STYLE + f"""
        <div class="centered">
        <div class="manual-entry">📝 Manual Entry</div>
        <h3>Tip Distribution for <span class="value-highlight">{server_name}</span></h3>
        <p><b>Date:</b> <span class="value-highlight">{date}</span></p>
        <p><b>Shift:</b> <span class="value-highlight">{start_time} - {end_time}</span></p>
        <p><b>Service Assistants:</b> <span class="value-highlight">{num_assistants}</span></p>
        
        <hr>
        <h3>📊 Sales Data</h3>
        <p><b>Alcohol Sales:</b> <span class="value-highlight">${alc_sales:.2f}</span></p>
        <p><b>Food Sales During Shift:</b> <span class="value-highlight">${food_sales_shift:.2f}</span></p>
        <p><b>Server Tips:</b> <span class="value-highlight">${server_tips:.2f}</span></p>
        
        <hr>
        <h3>💰 Tipout Breakdown</h3>
        <p>Bartender Tipout (<span class="value-highlight">{restaurant.bartender_percent}%</span> of <span class="value-highlight">${alc_sales:.2f}</span>): <span class="value-highlight">${bartender_tipout:.2f}</span></p>
        <p>Total SA Tipout (<span class="value-highlight">{restaurant.assistant_percent}%</span> of <span class="value-highlight">${food_sales_shift:.2f}</span>): <span class="value-highlight">${total_assistant_tipout:.2f}</span></p>
        <p>Per Service Assistant (<span class="value-highlight">{num_assistants}</span> SAs): <span class="value-highlight">${assistant_per_person:.2f}</span> each</p>
        
        <hr>
        <p><b>Total Tipout:</b> <span class="value-highlight">${total_tipout:.2f}</span></p>
        <p><b>Server Keeps:</b> <span class="value-highlight">${server_keep:.2f}</span></p>
        
        <form action="/menu" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit">Back to Main Menu</button>
        </form>
        </div>
        """
    except Exception as e:
        print(f"Calculation error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Calculation Error</h3>
        <p>{str(e)}</p>
        <a href="/">Home</a>
        </div>
        """

@app.post("/totals", response_class=HTMLResponse)
def show_totals(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        
        if not restaurant:
            return STYLE + """
            <div class="centered">
            <h3 class="error">Restaurant not found!</h3>
            <a href="/">Home</a>
            </div>
            """
        
        # Get all tipouts for the selected date
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == date
        ).all()
        
        if not tipouts:
            return STYLE + f"""
            <div class="centered">
            <h2>No Tipout Records Found</h2>
            <p><b>Restaurant:</b> <span class="value-highlight">{restaurant.name}</span></p>
            <p><b>Date:</b> <span class="value-highlight">{date}</span></p>
            <p><i>No tipout calculations found for this date.</i></p>
            <form action="/menu" method="post">
                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                <button type="submit">Back to Main Menu</button>
            </form>
            </div>
            """
        
        # Calculate totals
        total_bartender_tipout = sum(tipout.bartender_tipout for tipout in tipouts)
        total_assistant_tipout = sum(tipout.assistant_tipout for tipout in tipouts)
        
        # Create detailed breakdown
        server_details = []
        for tipout in tipouts:
            toast_badge = "🔗" if tipout.toast_sync else "📝"
            server_details.append(f"""
            <div style="background-color: rgba(67, 198, 172, 0.1); padding: 10px; margin: 5px; border-radius: 8px;">
            <p><b>{toast_badge} {tipout.server_name}</b> ({tipout.start_time} - {tipout.end_time})</p>
            <p>Bartender: <span class="value-highlight">${tipout.bartender_tipout:.2f}</span> | 
            SA Total: <span class="value-highlight">${tipout.assistant_tipout:.2f}</span> | 
            Per SA ({tipout.num_assistants}): <span class="value-highlight">${tipout.assistant_per_person:.2f}</span></p>
            </div>
            """)
        
        details_html = "".join(server_details)
        
        return STYLE + f"""
        <div class="centered">
        <h2>📈 Daily Tipout Summary</h2>
        <p><b>Restaurant:</b> <span class="value-highlight">{restaurant.name}</span></p>
        <p><b>Date:</b> <span class="value-highlight">{date}</span></p>
        
        <hr>
        <h3>💰 Total Payouts</h3>
        <p><b>Total to Bartenders:</b> <span class="value-highlight">${total_bartender_tipout:.2f}</span></p>
        <p><b>Total to Service Assistants:</b> <span class="value-highlight">${total_assistant_tipout:.2f}</span></p>
        <p><b>Grand Total Tipout:</b> <span class="value-highlight">${total_bartender_tipout + total_assistant_tipout:.2f}</span></p>
        
        <hr>
        <h3>🔍 Server Breakdown</h3>
        {details_html}
        
        <p><i>🔗 = Toast synced data | 📝 = Manual entry</i></p>
        
        <form action="/menu" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit">Back to Main Menu</button>
        </form>
        </div>
        """
    except Exception as e:
        print(f"Totals error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Totals Error</h3>
        <p>{str(e)}</p>
        <a href="/">Home</a>
        </div>
        """

@app.post("/settings", response_class=HTMLResponse)
def restaurant_settings(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        
        if not restaurant:
            return STYLE + """
            <div class="centered">
            <h3 class="error">Restaurant not found!</h3>
            <a href="/">Home</a>
            </div>
            """
        
        server_names = json.loads(restaurant.server_names)
        server_names_str = ", ".join(server_names)
        
        toast_status = "Connected ✅" if restaurant.toast_client_id else "Not Connected ❌"
        
        return STYLE + f"""
        <div class="centered">
        <h2>⚙️ Restaurant Settings</h2>
        <p><b>Restaurant:</b> <span class="value-highlight">{restaurant.name}</span></p>
        <p><b>Toast Status:</b> <span class="value-highlight">{toast_status}</span></p>
        
        <form action="/update_settings" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            
            <hr>
            <h3>🔗 Toast POS Integration</h3>
            <label>Toast Client ID:</label>
            <input type="text" name="toast_client_id" value="{restaurant.toast_client_id or ''}" placeholder="Optional"><br>
            
            <label>Toast Client Secret:</label>
            <input type="text" name="toast_client_secret" value="{restaurant.toast_client_secret or ''}" placeholder="Optional"><br>
            
            <label>Restaurant GUID:</label>
            <input type="text" name="toast_restaurant_guid" value="{restaurant.toast_restaurant_guid or ''}" placeholder="Optional"><br>
            
            <label>Management Group GUID:</label>
            <input type="text" name="toast_management_group_guid" value="{restaurant.toast_management_group_guid or ''}" placeholder="Optional"><br>
            
            <hr>
            <h3>💰 Tipout Percentages</h3>
            <label>Bartender Tipout %:</label>
            <input type="number" name="bartender_percent" step="0.01" min="0" max="100" value="{restaurant.bartender_percent}" required><br>
            
            <label>Assistant Tipout %:</label>
            <input type="number" name="assistant_percent" step="0.01" min="0" max="100" value="{restaurant.assistant_percent}" required><br>
            
            <hr>
            <h3>👥 Staff</h3>
            <label>Server Names (comma separated):</label>
            <input type="text" name="server_names" value="{server_names_str}" required style="width: 300px;"><br>
            
            <button type="submit">💾 Update Settings</button>
        </form>
        
        <form action="/menu" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
        </form>
        </div>
        """
    except Exception as e:
        print(f"Settings error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Settings Error</h3>
        <p>{str(e)}</p>
        <a href="/">Home</a>
        </div>
        """

@app.post("/update_settings", response_class=HTMLResponse)
def update_settings(
    restaurant_id: int = Form(...),
    toast_client_id: Optional[str] = Form(""),
    toast_client_secret: Optional[str] = Form(""),
    toast_restaurant_guid: Optional[str] = Form(""),
    toast_management_group_guid: Optional[str] = Form(""),
    bartender_percent: float = Form(...),
    assistant_percent: float = Form(...),
    server_names: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        
        if not restaurant:
            return STYLE + """
            <div class="centered">
            <h3 class="error">Restaurant not found!</h3>
            <a href="/">Home</a>
            </div>
            """
        
        # Parse server names
        server_list = [name.strip() for name in server_names.split(",") if name.strip()]
        if not server_list:
            return STYLE + f"""
            <div class="centered">
            <h3 class="error">Please provide at least one server name!</h3>
            <form action="/settings" method="post">
                <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                <button type="submit">Try Again</button>
            </form>
            </div>
            """
        
        # Update restaurant settings
        restaurant.toast_client_id = toast_client_id.strip() if toast_client_id.strip() else None
        restaurant.toast_client_secret = toast_client_secret.strip() if toast_client_secret.strip() else None
        restaurant.toast_restaurant_guid = toast_restaurant_guid.strip() if toast_restaurant_guid.strip() else None
        restaurant.toast_management_group_guid = toast_management_group_guid.strip() if toast_management_group_guid.strip() else None
        restaurant.bartender_percent = bartender_percent
        restaurant.assistant_percent = assistant_percent
        restaurant.server_names = json.dumps(server_list)
        
        db.commit()
        
        toast_status = ""
        if restaurant.toast_client_id:
            toast_status = '<div class="toast-status">✅ Toast POS Integration Updated</div>'
        else:
            toast_status = '<div class="manual-entry">📝 Manual Entry Mode (Toast not configured)</div>'
        
        return STYLE + f"""
        <div class="centered">
        <h2>✅ Settings Updated Successfully!</h2>
        {toast_status}
        <p><b>Bartender Tipout:</b> <span class="value-highlight">{bartender_percent}%</span></p>
        <p><b>Assistant Tipout:</b> <span class="value-highlight">{assistant_percent}%</span></p>
        <p><b>Servers:</b> <span class="value-highlight">{', '.join(server_list)}</span></p>
        
        <form action="/menu" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit">Back to Main Menu</button>
        </form>
        </div>
        """
    except Exception as e:
        print(f"Update settings error: {e}")
        return STYLE + f"""
        <div class="centered">
        <h3 class="error">Update Error</h3>
        <p>{str(e)}</p>
        <a href="/">Home</a>
        </div>
        """

@app.post("/menu", response_class=HTMLResponse)
def menu(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    return restaurant_dashboard(restaurant_id, db)

@app.post("/select_server_date", response_class=HTMLResponse)
def select_server_date(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return STYLE + "<div class='centered'><h3 class='error'>Restaurant not found!</h3></div>"
    server_names = json.loads(restaurant.server_names)
    options = "".join([f"<option value='{name}'>{name}</option>" for name in server_names])
    return STYLE + f"""
    <div class="centered">
    <h2>Select Server for Tipout</h2>
    <form action="/select_day_for_server" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <label for="server_name">Server Name:</label>
        <select name="server_name" required>{options}</select><br>
        <button type="submit">Next</button>
    </form>
    <form action="/menu" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
    </form>
    </div>
    """

@app.post("/select_day_for_server", response_class=HTMLResponse)
def select_day_for_server(restaurant_id: int = Form(...), server_name: str = Form(...), db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return STYLE + "<div class='centered'><h3 class='error'>Restaurant not found!</h3></div>"
    # Default times
    start_time = "17:00"
    end_time = "23:00"
    return STYLE + f"""
    <div class="centered">
    <h2>Select Date & Shift for {server_name}</h2>
    <form action="/manual_calculate_form" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <input type="hidden" name="server_name" value="{server_name}">
        <label for="date">Date:</label>
        <input type="date" name="date" required><br>
        <label for="start_time">Start Time:</label>
        <input type="time" name="start_time" value="{start_time}" required><br>
        <label for="end_time">End Time:</label>
        <input type="time" name="end_time" value="{end_time}" required><br>
        <label for="num_assistants">Number of Service Assistants:</label>
        <input type="number" name="num_assistants" min="1" value="1" required><br>
        <button type="submit">Get Sales & Tipout Info</button>
    </form>
    <form action="/menu" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
    </form>
    </div>
    """

@app.post("/manual_calculate_form", response_class=HTMLResponse)
async def manual_calculate_form(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    num_assistants: int = Form(...),
    db: Session = Depends(get_db)
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return STYLE + "<div class='centered'><h3 class='error'>Restaurant not found!</h3></div>"

    # Default values
    alc_sales = 0.0
    food_sales_shift = 0.0
    beer_sales = liquor_sales = wine_sales = 0.0
    beer_count = liquor_count = wine_count = 0
    hours_worked = 0.0

    # If Toast integration, fetch sales data
    if restaurant.toast_client_id:
        toast_api = ToastAPI(
            restaurant.toast_client_id,
            restaurant.toast_client_secret,
            restaurant.toast_restaurant_guid,
            restaurant.toast_management_group_guid
        )
        sales_data = await toast_api.get_sales_data(
            date=date,
            start_time=start_time,
            end_time=end_time,
            server_name=server_name
        )
        if sales_data:
            alc_sales = sales_data.get("total_alcohol_sales", 0.0)
            food_sales_shift = sales_data.get("total_food_sales", 0.0)
            beer_sales = sales_data.get("beer_sales", 0.0)
            beer_count = sales_data.get("beer_count", 0)
            liquor_sales = sales_data.get("liquor_sales", 0.0)
            liquor_count = sales_data.get("liquor_count", 0)
            wine_sales = sales_data.get("wine_sales", 0.0)
            wine_count = sales_data.get("wine_count", 0)
            # Autofill times if available
            start_time = sales_data.get("start_time", start_time)
            end_time = sales_data.get("end_time", end_time)
            # Calculate hours worked
            try:
                from datetime import datetime as dt
                fmt = "%H:%M"
                t1 = dt.strptime(start_time, fmt)
                t2 = dt.strptime(end_time, fmt)
                hours_worked = (t2 - t1).seconds / 3600.0
                if hours_worked <= 0:
                    hours_worked += 24  # handle overnight shifts
            except Exception:
                hours_worked = 0.0

    return STYLE + f"""
    <div class="centered">
    <h2>Tipout & Sales Info for {server_name}</h2>
    <p><b>Date:</b> <span class="value-highlight">{date}</span></p>
    <p><b>Shift:</b> <span class="value-highlight">{start_time} - {end_time}</span></p>
    <p><b>Hours Worked:</b> <span class="value-highlight">{hours_worked:.2f}</span></p>
    <p><b>Service Assistants:</b> <span class="value-highlight">{num_assistants}</span></p>
    <hr>
    <h3>Alcohol Sales Breakdown</h3>
    <p>Beer Sales: <span class="value-highlight">${beer_sales:.2f}</span> ({beer_count} sold)</p>
    <p>Liquor Sales: <span class="value-highlight">${liquor_sales:.2f}</span> ({liquor_count} sold)</p>
    <p>Wine Sales: <span class="value-highlight">${wine_sales:.2f}</span> ({wine_count} sold)</p>
    <p><b>Total Alcohol Sales:</b> <span class="value-highlight">${alc_sales:.2f}</span></p>
    <hr>
    <p><b>Food Sales:</b> <span class="value-highlight">${food_sales_shift:.2f}</span></p>
    <form action="/manual_calculate" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <input type="hidden" name="server_name" value="{server_name}">
        <input type="hidden" name="date" value="{date}">
        <input type="hidden" name="start_time" value="{start_time}">
        <input type="hidden" name="end_time" value="{end_time}">
        <input type="hidden" name="num_assistants" value="{num_assistants}">
        <input type="hidden" name="alc_sales" value="{alc_sales:.2f}">
        <input type="hidden" name="food_sales_shift" value="{food_sales_shift:.2f}">
        <label for="server_tips">Total Server Tips ($):</label>
        <input type="number" name="server_tips" step="0.01" min="0" value="0.00" required><br>
        <button type="submit">Calculate Tipout</button>
    </form>
    <form action="/menu" method="post">
        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
        <button type="submit" style="background-color: #95a5a6;">Back to Menu</button>
    </form>
    </div>
    """
# ...existing code...