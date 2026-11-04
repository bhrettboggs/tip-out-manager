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

# Database setup
DATABASE_URL = "sqlite:///./tipout_management.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
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

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Toast API Integration
class ToastAPI:
    def __init__(self, client_id: str, client_secret: str, restaurant_guid: str, management_group_guid: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.restaurant_guid = restaurant_guid
        self.management_group_guid = management_group_guid
        self.base_url = "http://localhost:8001"  # Mock server for testing
        self.token = None

    async def get_access_token(self):
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
                "restaurant_name": self.restaurant_guid.lower()
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

    async def get_working_servers(self, date: str):
        """Get list of servers who worked on a given date"""
        try:
            if not self.token:
                if not await self.get_access_token():
                    return []

            headers = {
                "Authorization": f"Bearer {self.token}",
                "Toast-Restaurant-External-ID": self.restaurant_guid
            }
            params = {
                "businessDate": date,
                "restaurant_name": self.restaurant_guid.lower()
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self.base_url}/orders/v2/orders",
                    headers=headers,
                    params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("working_servers", [])
                return []
        except Exception as e:
            print(f"Error getting working servers: {e}")
            return []

# Enhanced CSS with modern design
STYLE = """
<style>
:root {
    --primary: #43c6ac;
    --secondary: #2d3e50;
    --accent: #e67e22;
    --success: #2ecc71;
    --warning: #f39c12;
    --danger: #e74c3c;
    --light: #ecf0f1;
    --dark: #34495e;
}

* { box-sizing: border-box; }

body {
    background: linear-gradient(135deg, #f8ffae 0%, #43c6ac 100%);
    font-family: 'Segoe UI', 'Arial', sans-serif;
    margin: 0;
    padding: 0;
    min-height: 100vh;
}

.container {
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

.card {
    background: white;
    border-radius: 15px;
    padding: 30px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
    margin: 10px 0;
    width: 100%;
    max-width: 600px;
}

.header {
    text-align: center;
    margin-bottom: 30px;
}

h1, h2, h3 {
    color: var(--secondary);
    margin-bottom: 10px;
}

h1 { font-size: 2.5em; }
h2 { font-size: 2em; }
h3 { font-size: 1.5em; }

.breadcrumb {
    background: var(--light);
    padding: 10px 15px;
    border-radius: 8px;
    margin-bottom: 20px;
    font-size: 0.9em;
    color: var(--dark);
}

.breadcrumb a {
    color: var(--primary);
    text-decoration: none;
}

.btn {
    display: inline-block;
    padding: 12px 24px;
    margin: 8px 4px;
    border: none;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    text-align: center;
    transition: all 0.3s ease;
    min-width: 120px;
}

.btn-primary { background: var(--primary); color: white; }
.btn-secondary { background: var(--secondary); color: white; }
.btn-success { background: var(--success); color: white; }
.btn-warning { background: var(--warning); color: white; }
.btn-danger { background: var(--danger); color: white; }
.btn-light { background: var(--light); color: var(--dark); }

.btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.2);
}

.form-group {
    margin-bottom: 20px;
}

label {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
    color: var(--secondary);
}

input, select, textarea {
    width: 100%;
    padding: 12px;
    border: 2px solid #ddd;
    border-radius: 8px;
    font-size: 16px;
    transition: border-color 0.3s ease;
}

input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--primary);
}

.form-row {
    display: flex;
    gap: 15px;
    align-items: end;
}

.form-row .form-group {
    flex: 1;
}

.status-card {
    padding: 15px;
    margin: 10px 0;
    border-radius: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.status-completed {
    background: rgba(46, 204, 113, 0.1);
    border-left: 4px solid var(--success);
}

.status-pending {
    background: rgba(243, 156, 18, 0.1);
    border-left: 4px solid var(--warning);
}

.status-not-working {
    background: rgba(149, 165, 166, 0.1);
    border-left: 4px solid #95a5a6;
}

.highlight {
    color: var(--accent);
    font-weight: bold;
}

.error {
    color: var(--danger);
    font-weight: bold;
    background: rgba(231, 76, 60, 0.1);
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
}

.success {
    color: var(--success);
    font-weight: bold;
    background: rgba(46, 204, 113, 0.1);
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
}

.warning {
    color: var(--warning);
    font-weight: bold;
    background: rgba(243, 156, 18, 0.1);
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
}

.toast-status {
    background: var(--success);
    color: white;
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
    text-align: center;
}

.manual-entry {
    background: var(--warning);
    color: white;
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
    text-align: center;
}

.tipout-item {
    background: rgba(67, 198, 172, 0.1);
    padding: 20px;
    margin: 10px 0;
    border-radius: 10px;
    border-left: 4px solid var(--primary);
    position: relative;
}

.delete-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 50%;
    width: 30px;
    height: 30px;
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
}

.delete-btn:hover {
    background: #c0392b;
}

.summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin: 20px 0;
}

.summary-item {
    background: white;
    padding: 20px;
    border-radius: 10px;
    text-align: center;
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
}

.summary-value {
    font-size: 2em;
    font-weight: bold;
    color: var(--primary);
}

.summary-label {
    color: var(--secondary);
    margin-top: 5px;
}

.progress-bar {
    background: #ddd;
    border-radius: 10px;
    overflow: hidden;
    margin: 20px 0;
}

.progress-fill {
    background: var(--success);
    height: 20px;
    transition: width 0.3s ease;
}

@media (max-width: 768px) {
    .container { padding: 10px; }
    .card { padding: 20px; }
    .form-row { flex-direction: column; }
    h1 { font-size: 2em; }
    .summary-grid { grid-template-columns: 1fr; }
}

.toast-notification {
    position: fixed;
    top: 20px;
    right: 20px;
    background: var(--success);
    color: white;
    padding: 15px 20px;
    border-radius: 8px;
    z-index: 1001;
    animation: slideIn 0.3s ease;
}

@keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
}
</style>

<script>
function confirmDelete(tipoutId, restaurantId) {
    if (confirm('Are you sure you want to delete this tipout? This action cannot be undone.')) {
        deleteTipout(tipoutId, restaurantId);
    }
}

function deleteTipout(tipoutId, restaurantId) {
    fetch('/delete_tipout', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `tipout_id=${tipoutId}&restaurant_id=${restaurantId}`
    })
    .then(response => response.text())
    .then(html => {
        document.body.innerHTML = html;
        showToast('Tipout deleted successfully!');
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting tipout');
    });
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function updateHours() {
    const startTime = document.querySelector('input[name="start_time"]');
    const endTime = document.querySelector('input[name="end_time"]');
    const hoursWorked = document.querySelector('input[name="hours_worked"]');
    
    if (startTime && endTime && hoursWorked && startTime.value && endTime.value) {
        const start = new Date('2000-01-01 ' + startTime.value);
        const end = new Date('2000-01-01 ' + endTime.value);
        let hours = (end - start) / (1000 * 60 * 60);
        
        if (hours <= 0) hours += 24;
        
        hoursWorked.value = hours.toFixed(1);
    }
}

window.onload = function() {
    const startTimeInput = document.querySelector('input[name="start_time"]');
    const endTimeInput = document.querySelector('input[name="end_time"]');
    
    if (startTimeInput && endTimeInput) {
        startTimeInput.addEventListener('change', updateHours);
        endTimeInput.addEventListener('change', updateHours);
    }
};
</script>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return STYLE + """
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>🍽️ Restaurant Tipout Management</h1>
                <p>Professional tipout calculations with Toast POS integration</p>
            </div>
            
            <div style="text-align: center;">
                <a href="/login" class="btn btn-primary">🔑 Login to Restaurant</a>
                <a href="/register" class="btn btn-secondary">📝 Register New Restaurant</a>
            </div>
        </div>
    </div>
    """

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return STYLE + """
    <div class="container">
        <div class="card">
            <div class="breadcrumb">
                <a href="/">Home</a> → Login
            </div>
            
            <div class="header">
                <h2>🔑 Restaurant Login</h2>
            </div>
            
            <form action="/authenticate" method="post">
                <div class="form-group">
                    <label>Restaurant Name:</label>
                    <input type="text" name="restaurant_name" required>
                </div>
                
                <div style="text-align: center;">
                    <button type="submit" class="btn btn-primary">Login</button>
                    <a href="/" class="btn btn-light">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    """

@app.get("/register", response_class=HTMLResponse)
def register_form():
    return STYLE + """
    <div class="container">
        <div class="card">
            <div class="breadcrumb">
                <a href="/">Home</a> → Register
            </div>
            
            <div class="header">
                <h2>📝 Register New Restaurant</h2>
            </div>
            
            <form action="/create_restaurant" method="post">
                <div class="form-group">
                    <label>Restaurant Name:</label>
                    <input type="text" name="restaurant_name" required>
                </div>
                
                <h3>🔗 Toast POS Integration (Optional)</h3>
                <div class="form-group">
                    <label>Toast Client ID:</label>
                    <input type="text" name="toast_client_id" placeholder="Leave blank for manual entry only">
                </div>
                
                <div class="form-group">
                    <label>Toast Client Secret:</label>
                    <input type="text" name="toast_client_secret" placeholder="Leave blank for manual entry only">
                </div>
                
                <div class="form-group">
                    <label>Restaurant GUID:</label>
                    <input type="text" name="toast_restaurant_guid" placeholder="Leave blank for manual entry only">
                </div>
                
                <div class="form-group">
                    <label>Management Group GUID:</label>
                    <input type="text" name="toast_management_group_guid" placeholder="Leave blank for manual entry only">
                </div>
                
                <h3>💰 Tipout Settings</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label>Bartender Tipout %:</label>
                        <input type="number" name="bartender_percent" step="0.01" min="0" max="100" value="0.75" required>
                    </div>
                    
                    <div class="form-group">
                        <label>Assistant Tipout %:</label>
                        <input type="number" name="assistant_percent" step="0.01" min="0" max="100" value="0.75" required>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Server Names (comma separated):</label>
                    <input type="text" name="server_names" value="Alice,Bob,Charlie,Other" required>
                </div>
                
                <div style="text-align: center;">
                    <button type="submit" class="btn btn-success">Create Restaurant</button>
                    <button type="button" class="btn btn-light" onclick="window.location.href='/'">Cancel</button>
                </div>
            </form>
        </div>
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
        existing_restaurant = db.query(Restaurant).filter(Restaurant.name.ilike(restaurant_name.strip())).first()
        if existing_restaurant:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>❌ Restaurant Already Exists</h3>
                        <p>Restaurant name "{restaurant_name}" is already registered.</p>
                    </div>
                    <div style="text-align: center;">
                        <a href="/register" class="btn btn-primary">Try Different Name</a>
                        <a href="/" class="btn btn-light">Back to Home</a>
                    </div>
                </div>
            </div>
            """
        
        server_list = [name.strip() for name in server_names.split(",") if name.strip()]
        if not server_list:
            return STYLE + """
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>❌ Invalid Server Names</h3>
                        <p>Please provide at least one server name.</p>
                    </div>
                    <div style="text-align: center;">
                        <a href="/register" class="btn btn-primary">Try Again</a>
                    </div>
                </div>
            </div>
            """
        
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
            toast_status = '<div class="manual-entry">📝 Manual Entry Mode - Toast Integration Available in Settings</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="success">
                    <h2>✅ Restaurant Created Successfully!</h2>
                </div>
                {toast_status}
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{restaurant_name}</div>
                        <div class="summary-label">Restaurant Name</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{bartender_percent}%</div>
                        <div class="summary-label">Bartender Tipout</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{assistant_percent}%</div>
                        <div class="summary-label">Assistant Tipout</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(server_list)}</div>
                        <div class="summary-label">Servers</div>
                    </div>
                </div>
                
                <p><strong>Servers:</strong> {', '.join(server_list)}</p>
                
                <div style="text-align: center;">
                    <form action="/authenticate" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_name" value="{restaurant_name}">
                        <button type="submit" class="btn btn-primary">Continue to Dashboard</button>
                    </form>
                    <a href="/" class="btn btn-light">Back to Home</a>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Database error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Database Error</h3>
                    <p>Error creating restaurant: {str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <a href="/register" class="btn btn-primary">Try Again</a>
                    <a href="/" class="btn btn-light">Back to Home</a>
                </div>
            </div>
        </div>
        """

@app.post("/authenticate", response_class=HTMLResponse)
def authenticate(restaurant_name: str = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.name.ilike(restaurant_name.strip())).first()
        if not restaurant:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>❌ Restaurant Not Found</h3>
                        <p>Restaurant "{restaurant_name}" not found in our system.</p>
                    </div>
                    <div style="text-align: center;">
                        <a href="/login" class="btn btn-primary">Try Again</a>
                        <a href="/register" class="btn btn-secondary">Register New</a>
                        <a href="/" class="btn btn-light">Back to Home</a>
                    </div>
                </div>
            </div>
            """
        
        return restaurant_dashboard(restaurant.id, db)
    except Exception as e:
        print(f"Authentication error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Login Error</h3>
                    <p>Error during login: {str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <a href="/login" class="btn btn-primary">Try Again</a>
                </div>
            </div>
        </div>
        """

def restaurant_dashboard(restaurant_id: int, db: Session):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + """
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>❌ Restaurant Not Found</h3>
                    </div>
                    <div style="text-align: center;">
                        <a href="/" class="btn btn-primary">Back to Home</a>
                    </div>
                </div>
            </div>
            """
        
        toast_status = ""
        if restaurant.toast_client_id:
            toast_status = '<div class="toast-status">🔗 Toast POS Connected</div>'
        else:
            toast_status = '<div class="manual-entry">📝 Manual Entry Mode</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → Dashboard
                </div>
                
                <div class="header">
                    <h1>🏠 {restaurant.name}</h1>
                    {toast_status}
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{restaurant.bartender_percent}%</div>
                        <div class="summary-label">Bartender Tipout</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{restaurant.assistant_percent}%</div>
                        <div class="summary-label">Assistant Tipout</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(json.loads(restaurant.server_names))}</div>
                        <div class="summary-label">Total Servers</div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <form action="/daily_status" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">📊 Daily Status & Tipout</button>
                    </form>
                    
                    <form action="/totals" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <label style="display: block; margin: 10px 0;">Select Date for Totals:</label>
                        <input type="date" name="date" required style="width: 200px; margin: 5px;">
                        <button type="submit" class="btn btn-secondary">📈 View Daily Totals</button>
                    </form>
                    
                    <form action="/settings" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-warning">⚙️ Settings</button>
                    </form>
                </div>
                
                <div style="text-align: center;">
                    <a href="/" class="btn btn-light">🚪 Logout</a>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Dashboard error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Dashboard Error</h3>
                    <p>{str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <a href="/" class="btn btn-primary">Back to Home</a>
                </div>
            </div>
        </div>
        """

@app.post("/daily_status", response_class=HTMLResponse)
async def daily_status(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        # Get today's date
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        
        # Get working servers from Toast if available
        working_servers = []
        if restaurant.toast_client_id:
            toast_api = ToastAPI(
                restaurant.toast_client_id,
                restaurant.toast_client_secret,
                restaurant.toast_restaurant_guid,
                restaurant.toast_management_group_guid
            )
            working_servers = await toast_api.get_working_servers(today)
        
        # If no Toast data, use all servers as potentially working
        all_servers = json.loads(restaurant.server_names)
        if not working_servers:
            working_servers = all_servers
        
        # Get existing tipouts for today
        today_tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == today
        ).all()
        
        tipped_out_servers = {tipout.server_name for tipout in today_tipouts}
        
        # Calculate totals
        total_bartender = sum(tipout.bartender_tipout for tipout in today_tipouts)
        total_assistant = sum(tipout.assistant_tipout for tipout in today_tipouts)
        completed_count = len(tipped_out_servers)
        working_count = len(working_servers)
        progress_percentage = (completed_count / working_count * 100) if working_count > 0 else 0
        
        # Create status cards
        status_cards = []
        for server in all_servers:
            if server in tipped_out_servers:
                tipout = next(t for t in today_tipouts if t.server_name == server)
                status_cards.append(f"""
                <div class="status-card status-completed">
                    <div>
                        <strong>✅ {server}</strong><br>
                        <small>Bartender: ${tipout.bartender_tipout:.2f} | SA: ${tipout.assistant_per_person:.2f}</small>
                    </div>
                    <button class="delete-btn" onclick="confirmDelete({tipout.id}, {restaurant.id})" title="Delete tipout">×</button>
                </div>
                """)
            elif server in working_servers:
                status_cards.append(f"""
                <div class="status-card status-pending">
                    <div>
                        <strong>⏳ {server}</strong><br>
                        <small>Working today - needs tipout</small>
                    </div>
                    <form action="/calculate_tipout" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <input type="hidden" name="server_name" value="{server}">
                        <input type="hidden" name="date" value="{today}">
                        <button type="submit" class="btn btn-primary">Calculate</button>
                    </form>
                </div>
                """)
            else:
                status_cards.append(f"""
                <div class="status-card status-not-working">
                    <div>
                        <strong>💤 {server}</strong><br>
                        <small>Not working today</small>
                    </div>
                </div>
                """)
        
        status_html = "".join(status_cards)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Daily Status
                </div>
                
                <div class="header">
                    <h2>📊 Daily Status - {today}</h2>
                    <p><strong>{restaurant.name}</strong></p>
                </div>
                
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {progress_percentage}%;"></div>
                </div>
                <p style="text-align: center; color: var(--secondary);">
                    Progress: {completed_count}/{working_count} servers completed ({progress_percentage:.0f}%)
                </p>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">${total_bartender:.2f}</div>
                        <div class="summary-label">Total Bartender</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">${total_assistant:.2f}</div>
                        <div class="summary-label">Total Assistant</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{completed_count}</div>
                        <div class="summary-label">Completed</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{working_count - completed_count}</div>
                        <div class="summary-label">Remaining</div>
                    </div>
                </div>
                
                <h3>👥 Server Status</h3>
                {status_html}
                
                <div style="text-align: center; margin-top: 30px;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">← Back to Dashboard</button>
                    </form>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Daily status error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error Loading Daily Status</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

# Add the GET route to fix the 405 error
@app.get("/daily_status", response_class=HTMLResponse)
async def daily_status_get(restaurant_id: int, db: Session = Depends(get_db)):
    # For GET requests, restaurant_id comes from query parameters
    # Call the main logic from the POST function but pass parameters correctly
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        # Get today's date
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        
        # Reuse the same logic as the POST function...
        # (Copy the main logic here or create a shared function)
        
        # For now, redirect to menu as a simple fix
        return restaurant_dashboard(restaurant_id, db)
        
    except Exception as e:
        print(f"Daily status GET error: {e}")
        return restaurant_dashboard(restaurant_id, db)
        
@app.post("/calculate_tipout", response_class=HTMLResponse)
async def calculate_tipout(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        # Check for existing tipout
        existing_tipout = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.server_name == server_name,
            Tipout.date == date
        ).first()
        
        show_override_warning = bool(existing_tipout)
        
        # Default values
        alc_sales = 0.0
        food_sales_shift = 0.0
        start_time = "17:00"
        end_time = "23:00"
        hours_worked = 6.0
        toast_data_available = False
        
        # Try to get Toast data
        if restaurant.toast_client_id:
            toast_api = ToastAPI(
                restaurant.toast_client_id,
                restaurant.toast_client_secret,
                restaurant.toast_restaurant_guid,
                restaurant.toast_management_group_guid
            )
            sales_data = await toast_api.get_sales_data(
                date=date,
                server_name=server_name
            )
            if sales_data:
                alc_sales = sales_data.get("total_alcohol_sales", 0.0)
                food_sales_shift = sales_data.get("total_food_sales", 0.0)
                start_time = sales_data.get("start_time", start_time)
                end_time = sales_data.get("end_time", end_time)
                toast_data_available = True
                
                # Calculate hours
                try:
                    from datetime import datetime as dt
                    fmt = "%H:%M"
                    t1 = dt.strptime(start_time, fmt)
                    t2 = dt.strptime(end_time, fmt)
                    hours_worked = (t2 - t1).seconds / 3600.0
                    if hours_worked <= 0:
                        hours_worked += 24
                except Exception:
                    hours_worked = 6.0
        
        override_warning = ""
        if show_override_warning:
            override_warning = f"""
            <div class="warning">
                <h3>⚠️ Server Already Tipped Out Today</h3>
                <p><strong>{server_name}</strong> already has a tipout for {date}.</p>
                <p>Continuing will replace the existing tipout.</p>
            </div>
            """
        
        data_source_info = ""
        if toast_data_available:
            data_source_info = f"""
            <div class="toast-status">
                <h3>🔗 Toast Data Retrieved</h3>
                <p>Sales data automatically loaded from Toast POS</p>
            </div>
            """
        else:
            data_source_info = f"""
            <div class="manual-entry">
                <h3>📝 Manual Entry Required</h3>
                <p>Toast data unavailable - please enter sales manually</p>
            </div>
            """
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Calculate Tipout
                </div>
                
                <div class="header">
                    <h2>🧮 Calculate Tipout for {server_name}</h2>
                    <p><strong>Date:</strong> {date}</p>
                </div>
                
                {override_warning}
                {data_source_info}
                
                <form action="/process_tipout" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <input type="hidden" name="server_name" value="{server_name}">
                    <input type="hidden" name="date" value="{date}">
                    <input type="hidden" name="is_override" value="{show_override_warning}">
                    
                    <h3>⏰ Shift Information</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Start Time:</label>
                            <input type="time" name="start_time" value="{start_time}" required>
                        </div>
                        <div class="form-group">
                            <label>End Time:</label>
                            <input type="time" name="end_time" value="{end_time}" required>
                        </div>
                        <div class="form-group">
                            <label>Hours Worked:</label>
                            <input type="number" name="hours_worked" step="0.5" value="{hours_worked:.1f}" readonly>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Number of Service Assistants Working:</label>
                        <input type="number" name="num_assistants" min="1" max="10" value="1" required>
                    </div>
                    
                    <h3>💰 Sales Information</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Total Alcohol Sales ($):</label>
                            <input type="number" name="alc_sales" step="0.01" min="0" value="{alc_sales:.2f}" required>
                        </div>
                        <div class="form-group">
                            <label>Food Sales During Shift ($):</label>
                            <input type="number" name="food_sales_shift" step="0.01" min="0" value="{food_sales_shift:.2f}" required>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Total Server Tips Earned ($):</label>
                        <input type="number" name="server_tips" step="0.01" min="0" required>
                    </div>
                    
                    <div style="background: var(--light); padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p><strong>Calculation Preview:</strong></p>
                        <p>• Bartender Tipout: {restaurant.bartender_percent}% of alcohol sales</p>
                        <p>• Assistant Tipout: {restaurant.assistant_percent}% of food sales ÷ number of assistants</p>
                    </div>
                    
                    <div style="text-align: center;">
                        <button type="submit" class="btn btn-success">
                            {'Update Tipout' if show_override_warning else 'Calculate Tipout'}
                        </button>
                        <a href="/menu?restaurant_id={restaurant_id}" class="btn btn-light" style="text-decoration: none; display: inline-block;">Cancel</a>
                    </div>
                </form>
            </div>
        </div>
        """
        
    except Exception as e:
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error</h3>
                    <p>An error occurred: {str(e)}</p>
                    <a href="/" class="btn btn-primary">Go Home</a>
                </div>
            </div>
        </div>
        """
@app.post("/process_tipout", response_class=HTMLResponse)
def process_tipout(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    num_assistants: int = Form(...),
    alc_sales: float = Form(...),
    food_sales_shift: float = Form(...),
    server_tips: float = Form(...),
    is_override: bool = Form(False),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        # Calculate tipouts
        bartender_tipout = alc_sales * (restaurant.bartender_percent / 100)
        total_assistant_tipout = food_sales_shift * (restaurant.assistant_percent / 100)
        assistant_per_person = total_assistant_tipout / num_assistants
        total_tipout = bartender_tipout + assistant_per_person
        server_keep = server_tips - total_tipout
        
        # Handle existing tipout (update or create new)
        existing_tipout = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.server_name == server_name,
            Tipout.date == date
        ).first()
        
        if existing_tipout:
            # Update existing tipout
            existing_tipout.start_time = start_time
            existing_tipout.end_time = end_time
            existing_tipout.num_assistants = num_assistants
            existing_tipout.total_alc_sales = alc_sales
            existing_tipout.total_food_sales = food_sales_shift
            existing_tipout.time_based_food_sales = food_sales_shift
            existing_tipout.server_tips = server_tips
            existing_tipout.bartender_tipout = bartender_tipout
            existing_tipout.assistant_tipout = total_assistant_tipout
            existing_tipout.assistant_per_person = assistant_per_person
            existing_tipout.toast_sync = False
            action_text = "Updated"
        else:
            # Create new tipout
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
            action_text = "Created"
        
        db.commit()
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="success">
                    <h2>✅ Tipout {action_text} Successfully!</h2>
                </div>
                
                <div class="header">
                    <h3>💰 Tip Distribution for {server_name}</h3>
                    <p><strong>Date:</strong> {date} | <strong>Shift:</strong> {start_time} - {end_time}</p>
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">${alc_sales:.2f}</div>
                        <div class="summary-label">Alcohol Sales</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">${food_sales_shift:.2f}</div>
                        <div class="summary-label">Food Sales</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">${server_tips:.2f}</div>
                        <div class="summary-label">Server Tips</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{num_assistants}</div>
                        <div class="summary-label">Service Assistants</div>
                    </div>
                </div>
                
                <h3>🧮 Tipout Breakdown</h3>
                <div class="tipout-item">
                    <h4>🍺 Bartender Tipout</h4>
                    <p>{restaurant.bartender_percent}% of ${alc_sales:.2f} = <span class="highlight">${bartender_tipout:.2f}</span></p>
                </div>
                
                <div class="tipout-item">
                    <h4>🍽️ Service Assistant Tipout</h4>
                    <p>{restaurant.assistant_percent}% of ${food_sales_shift:.2f} = ${total_assistant_tipout:.2f}</p>
                    <p>Per Assistant ({num_assistants} SAs): <span class="highlight">${assistant_per_person:.2f}</span> each</p>
                </div>
                
                <div style="background: var(--success); color: white; padding: 20px; border-radius: 10px; text-align: center; margin: 20px 0;">
                    <h3>📊 Final Summary</h3>
                    <p><strong>Total Tipout:</strong> ${total_tipout:.2f}</p>
                    <p><strong>Server Keeps:</strong> ${server_keep:.2f}</p>
                </div>
                
                <div style="text-align: center;">
                    <form action="/daily_status" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">← Back to Daily Status</button>
                    </form>
                    
                    <form action="/calculate_tipout" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <input type="hidden" name="date" value="{date}">
                        <input type="hidden" name="server_name" value="{server_name}">
                        <button type="submit" class="btn btn-warning">Edit This Tipout</button>
                    </form>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Process tipout error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error Processing Tipout</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/delete_tipout", response_class=HTMLResponse)
async def delete_tipout(tipout_id: int = Form(...), restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        tipout = db.query(Tipout).filter(Tipout.id == tipout_id).first()
        if tipout:
            db.delete(tipout)
            db.commit()
        
        # Redirect back to daily status
        return await daily_status(restaurant_id, db)
    except Exception as e:
        print(f"Delete tipout error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error Deleting Tipout</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/totals", response_class=HTMLResponse)
def show_totals(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == date
        ).all()
        
        if not tipouts:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="breadcrumb">
                        <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Daily Totals
                    </div>
                    
                    <div class="header">
                        <h2>📈 No Records Found</h2>
                        <p><strong>{restaurant.name}</strong> - {date}</p>
                    </div>
                    
                    <div style="text-align: center; padding: 40px;">
                        <h3>🔍 No tipout records found for this date</h3>
                        <p>Try a different date or calculate some tipouts first.</p>
                    </div>
                    
                    <div style="text-align: center;">
                        <form action="/menu" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-primary">← Back to Dashboard</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        total_bartender_tipout = sum(tipout.bartender_tipout for tipout in tipouts)
        total_assistant_tipout = sum(tipout.assistant_tipout for tipout in tipouts)
        total_server_tips = sum(tipout.server_tips for tipout in tipouts)
        total_sales = sum(tipout.total_alc_sales + tipout.time_based_food_sales for tipout in tipouts)
        
        tipout_details = []
        for tipout in tipouts:
            toast_badge = "🔗" if tipout.toast_sync else "📝"
            tipout_details.append(f"""
            <div class="tipout-item">
                <button class="delete-btn" onclick="confirmDelete({tipout.id}, {restaurant.id})" title="Delete tipout">×</button>
                <h4>{toast_badge} {tipout.server_name}</h4>
                <p><strong>Shift:</strong> {tipout.start_time} - {tipout.end_time} | <strong>SAs:</strong> {tipout.num_assistants}</p>
                <div class="form-row">
                    <div>Bartender: <span class="highlight">${tipout.bartender_tipout:.2f}</span></div>
                    <div>SA Total: <span class="highlight">${tipout.assistant_tipout:.2f}</span></div>
                    <div>Per SA: <span class="highlight">${tipout.assistant_per_person:.2f}</span></div>
                    <div>Server Tips: <span class="highlight">${tipout.server_tips:.2f}</span></div>
                </div>
            </div>
            """)
        
        details_html = "".join(tipout_details)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Daily Totals
                </div>
                
                <div class="header">
                    <h2>📈 Daily Totals Summary</h2>
                    <p><strong>{restaurant.name}</strong> - {date}</p>
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">${total_bartender_tipout:.2f}</div>
                        <div class="summary-label">Total Bartender</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">${total_assistant_tipout:.2f}</div>
                        <div class="summary-label">Total Assistant</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">${total_server_tips:.2f}</div>
                        <div class="summary-label">Total Server Tips</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">${total_sales:.2f}</div>
                        <div class="summary-label">Total Sales</div>
                    </div>
                </div>
                
                <div style="background: var(--primary); color: white; padding: 20px; border-radius: 10px; text-align: center; margin: 20px 0;">
                    <h3>💰 Grand Total Tipout: ${total_bartender_tipout + total_assistant_tipout:.2f}</h3>
                </div>
                
                <h3>🔍 Individual Breakdowns</h3>
                <p style="color: var(--secondary); font-style: italic;">Click the × to delete a tipout entry</p>
                {details_html}
                
                <p style="text-align: center; color: var(--secondary); font-size: 0.9em; margin-top: 20px;">
                    🔗 = Toast synced data | 📝 = Manual entry
                </p>
                
                <div style="text-align: center;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">← Back to Dashboard</button>
                    </form>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Totals error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error Loading Totals</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/settings", response_class=HTMLResponse)
def restaurant_settings(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        server_names = json.loads(restaurant.server_names)
        server_names_str = ", ".join(server_names)
        toast_status = "Connected ✅" if restaurant.toast_client_id else "Not Connected ❌"
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Settings
                </div>
                
                <div class="header">
                    <h2>⚙️ Restaurant Settings</h2>
                    <p><strong>{restaurant.name}</strong></p>
                </div>
                
                <div class="toast-status" style="background: {'var(--success)' if restaurant.toast_client_id else 'var(--warning)'};">
                    Toast Status: {toast_status}
                </div>
                
                <form action="/update_settings" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    
                    <h3>🔗 Toast POS Integration</h3>
                    <div class="form-group">
                        <label>Toast Client ID:</label>
                        <input type="text" name="toast_client_id" value="{restaurant.toast_client_id or ''}" placeholder="Enter Toast Client ID">
                    </div>
                    
                    <div class="form-group">
                        <label>Toast Client Secret:</label>
                        <input type="text" name="toast_client_secret" value="{restaurant.toast_client_secret or ''}" placeholder="Enter Toast Client Secret">
                    </div>
                    
                    <div class="form-group">
                        <label>Restaurant GUID:</label>
                        <input type="text" name="toast_restaurant_guid" value="{restaurant.toast_restaurant_guid or ''}" placeholder="Enter Restaurant GUID">
                    </div>
                    
                    <div class="form-group">
                        <label>Management Group GUID:</label>
                        <input type="text" name="toast_management_group_guid" value="{restaurant.toast_management_group_guid or ''}" placeholder="Enter Management Group GUID">
                    </div>
                    
                    <h3>💰 Tipout Percentages</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Bartender Tipout %:</label>
                            <input type="number" name="bartender_percent" step="0.01" min="0" max="100" value="{restaurant.bartender_percent}" required>
                        </div>
                        
                        <div class="form-group">
                            <label>Assistant Tipout %:</label>
                            <input type="number" name="assistant_percent" step="0.01" min="0" max="100" value="{restaurant.assistant_percent}" required>
                        </div>
                    </div>
                    
                    <h3>👥 Staff Management</h3>
                    <div class="form-group">
                        <label>Server Names (comma separated):</label>
                        <input type="text" name="server_names" value="{server_names_str}" required>
                        <small style="color: var(--secondary); display: block; margin-top: 5px;">
                            Current servers: {len(server_names)} total
                        </small>
                    </div>
                    
                    <div style="text-align: center; margin-top: 30px;">
                        <button type="submit" class="btn btn-success">💾 Save Settings</button>
                        <form action="/menu" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-light">Cancel</button>
                        </form>
                    </div>
                </form>
                
                <div style="margin-top: 30px; padding: 20px; background: var(--light); border-radius: 10px;">
                    <h4>💡 Tips for Settings:</h4>
                    <ul style="text-align: left; color: var(--secondary);">
                        <li><strong>Toast Integration:</strong> Contact your Toast rep for API credentials</li>
                        <li><strong>Tipout %:</strong> Enter as decimal (0.75 for 0.75%)</li>
                        <li><strong>Server Names:</strong> Add all potential servers, not just current ones</li>
                        <li><strong>Backup:</strong> Settings are automatically saved to database</li>
                    </ul>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Settings error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error Loading Settings</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
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
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>❌ Restaurant not found!</h3></div></div></div>"
        
        server_list = [name.strip() for name in server_names.split(",") if name.strip()]
        if not server_list:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>❌ Invalid Server Names</h3>
                        <p>Please provide at least one server name.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/settings" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Try Again</button>
                        </form>
                    </div>
                </div>
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
            toast_status = '<div class="toast-status">✅ Toast POS Integration Updated & Active</div>'
        else:
            toast_status = '<div class="manual-entry">📝 Manual Entry Mode - Toast Integration Disabled</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="success">
                    <h2>✅ Settings Updated Successfully!</h2>
                </div>
                {toast_status}
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{bartender_percent}%</div>
                        <div class="summary-label">Bartender Tipout</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{assistant_percent}%</div>
                        <div class="summary-label">Assistant Tipout</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(server_list)}</div>
                        <div class="summary-label">Total Servers</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{'Yes' if restaurant.toast_client_id else 'No'}</div>
                        <div class="summary-label">Toast Connected</div>
                    </div>
                </div>
                
                <div style="background: var(--light); padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Updated Servers:</strong> {', '.join(server_list)}</p>
                </div>
                
                <div style="text-align: center;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">← Back to Dashboard</button>
                    </form>
                    
                    <form action="/settings" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Edit Settings Again</button>
                    </form>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Update settings error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>❌ Error Updating Settings</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/menu", response_class=HTMLResponse)
def menu(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    return restaurant_dashboard(restaurant_id, db)

@app.get("/menu", response_class=HTMLResponse)
def menu_get(restaurant_id: int, db: Session = Depends(get_db)):
    return restaurant_dashboard(restaurant_id, db)

@app.get("/debug")
def debug_info(db: Session = Depends(get_db)):
    try:
        restaurants = db.query(Restaurant).all()
        tipouts = db.query(Tipout).all()
        
        return {
            "status": "Enhanced Tipout System Working!",
            "restaurants_count": len(restaurants),
            "tipouts_count": len(tipouts),
            "features": [
                "✅ Manual sales entry fallback",
                "✅ Duplicate prevention with override",
                "✅ Staff tracking via Toast",
                "✅ Delete confirmation dialogs",
                "✅ Daily status dashboard",
                "✅ Enhanced UI with modern design",
                "✅ Mobile responsive",
                "✅ Toast notifications",
                "✅ Progress indicators"
            ],
            "restaurants": [{"id": r.id, "name": r.name, "toast_connected": bool(r.toast_client_id)} for r in restaurants],
            "database_file": "tipout_management.db"
        }
    except Exception as e:
        return {"error": str(e), "message": "Database connection failed"}

if __name__ == "__main__":
    print("🚀 Starting Enhanced Tipout Management Server...")
    print("📱 Open: http://localhost:8080")
    print("🔍 Debug: http://localhost:8080/debug")
    print("💾 Database: tipout_management.db")
    print("\n🌟 New Features:")
    print("  • Manual sales entry fallback")
    print("  • Duplicate prevention with override")
    print("  • Staff tracking via Toast")
    print("  • Delete confirmations")
    print("  • Daily status dashboard")
    print("  • Enhanced UI & UX")
    uvicorn.run(app, host="0.0.0.0", port=8080)