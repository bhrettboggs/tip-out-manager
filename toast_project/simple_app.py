from fastapi import FastAPI, Form, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime
import json
import uvicorn
import os

app = FastAPI()

# Remove old database to start fresh
if os.path.exists("tipout_simple.db"):
    os.remove("tipout_simple.db")
    print("🗑️ Old database removed")

# Database setup
DATABASE_URL = "sqlite:///./tipout_simple.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Simplified Models
class Restaurant(Base):
    __tablename__ = "restaurants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    bartender_percent = Column(Float, nullable=False)
    assistant_percent = Column(Float, nullable=False)
    server_names = Column(String, nullable=False)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

class Tipout(Base):
    __tablename__ = "tipouts"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer)
    server_name = Column(String, nullable=False)
    date = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    num_assistants = Column(Integer, nullable=False)
    alc_sales = Column(Float, nullable=False)
    food_sales = Column(Float, nullable=False)
    server_tips = Column(Float, nullable=False)
    bartender_tipout = Column(Float, nullable=False)
    assistant_tipout = Column(Float, nullable=False)
    assistant_per_person = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Simple database created successfully")
except Exception as e:
    print(f"❌ Database error: {e}")

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

STYLE = """
<style>
body { background: linear-gradient(135deg, #f8ffae 0%, #43c6ac 100%); font-family: Arial, sans-serif; margin: 0; padding: 20px; }
.container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; text-align: center; }
h1, h2 { color: #2d3e50; }
button { background: #43c6ac; color: white; padding: 12px 24px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; margin: 10px; }
button:hover { background: #2d3e50; }
input, select { padding: 10px; margin: 5px; border: 1px solid #ddd; border-radius: 5px; width: 200px; }
label { display: block; margin: 10px 0 5px 0; font-weight: bold; }
.highlight { color: #e67e22; font-weight: bold; }
.error { color: #e74c3c; font-weight: bold; }
</style>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return STYLE + """
    <div class="container">
        <h1>🧪 Simple Tipout Calculator</h1>
        <p>Minimal working version for testing</p>
        
        <form action="/register" method="get">
            <button type="submit">Register New Restaurant</button>
        </form>
        
        <form action="/login" method="get">
            <button type="submit">Login to Restaurant</button>
        </form>
    </div>
    """

@app.get("/register", response_class=HTMLResponse)
def register_form():
    return STYLE + """
    <div class="container">
        <h2>Register Restaurant</h2>
        <form action="/create_restaurant" method="post">
            <label>Restaurant Name:</label>
            <input type="text" name="restaurant_name" required><br>
            
            <label>Bartender Tipout %:</label>
            <input type="number" name="bartender_percent" step="0.01" value="0.75" required><br>
            
            <label>Assistant Tipout %:</label>
            <input type="number" name="assistant_percent" step="0.01" value="0.75" required><br>
            
            <label>Server Names (comma separated):</label>
            <input type="text" name="server_names" value="Alice,Bob,Charlie" required><br>
            
            <button type="submit">Create Restaurant</button>
        </form>
        <a href="/">Back Home</a>
    </div>
    """

@app.post("/create_restaurant", response_class=HTMLResponse)
def create_restaurant(
    restaurant_name: str = Form(...),
    bartender_percent: float = Form(...),
    assistant_percent: float = Form(...),
    server_names: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        # Check if restaurant exists
        existing = db.query(Restaurant).filter(Restaurant.name.ilike(restaurant_name.strip())).first()
        if existing:
            return STYLE + f"""
            <div class="container">
                <h2 class="error">Restaurant "{restaurant_name}" already exists!</h2>
                <a href="/register">Try Again</a>
            </div>
            """
        
        # Parse server names
        server_list = [name.strip() for name in server_names.split(",") if name.strip()]
        
        # Create restaurant
        restaurant = Restaurant(
            name=restaurant_name.strip(),
            bartender_percent=bartender_percent,
            assistant_percent=assistant_percent,
            server_names=json.dumps(server_list)
        )
        
        db.add(restaurant)
        db.commit()
        db.refresh(restaurant)
        
        return STYLE + f"""
        <div class="container">
            <h2>✅ Restaurant Created!</h2>
            <p><strong>Name:</strong> <span class="highlight">{restaurant_name}</span></p>
            <p><strong>Bartender %:</strong> <span class="highlight">{bartender_percent}%</span></p>
            <p><strong>Assistant %:</strong> <span class="highlight">{assistant_percent}%</span></p>
            <p><strong>Servers:</strong> <span class="highlight">{', '.join(server_list)}</span></p>
            
            <form action="/dashboard" method="post">
                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                <button type="submit">Go to Dashboard</button>
            </form>
            <a href="/">Home</a>
        </div>
        """
        
    except Exception as e:
        return STYLE + f"""
        <div class="container">
            <h2 class="error">Error: {str(e)}</h2>
            <a href="/register">Try Again</a>
        </div>
        """

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return STYLE + """
    <div class="container">
        <h2>Login</h2>
        <form action="/authenticate" method="post">
            <label>Restaurant Name:</label>
            <input type="text" name="restaurant_name" required><br>
            <button type="submit">Login</button>
        </form>
        <a href="/">Back Home</a>
    </div>
    """

@app.post("/authenticate", response_class=HTMLResponse)
def authenticate(restaurant_name: str = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.name.ilike(restaurant_name.strip())).first()
        if not restaurant:
            return STYLE + f"""
            <div class="container">
                <h2 class="error">Restaurant "{restaurant_name}" not found!</h2>
                <a href="/login">Try Again</a> | <a href="/register">Register New</a>
            </div>
            """
        
        return dashboard(restaurant.id, db)
        
    except Exception as e:
        return STYLE + f"""
        <div class="container">
            <h2 class="error">Login Error: {str(e)}</h2>
            <a href="/login">Try Again</a>
        </div>
        """

def dashboard(restaurant_id: int, db: Session):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    
    return STYLE + f"""
    <div class="container">
        <h2>Welcome {restaurant.name}!</h2>
        
        <form action="/calculate_form" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <button type="submit">Calculate Tipout</button>
        </form>
        
        <form action="/view_totals" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            <label>Date:</label>
            <input type="date" name="date" required><br>
            <button type="submit">View Daily Totals</button>
        </form>
        
        <a href="/">Logout</a>
    </div>
    """

@app.post("/dashboard", response_class=HTMLResponse)
def dashboard_post(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    return dashboard(restaurant_id, db)

@app.post("/calculate_form", response_class=HTMLResponse)
def calculate_form(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    server_names = json.loads(restaurant.server_names)
    options = "".join([f"<option value='{name}'>{name}</option>" for name in server_names])
    
    return STYLE + f"""
    <div class="container">
        <h2>Calculate Tipout</h2>
        <form action="/calculate" method="post">
            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
            
            <label>Server:</label>
            <select name="server_name" required>{options}</select><br>
            
            <label>Date:</label>
            <input type="date" name="date" required><br>
            
            <label>Start Time:</label>
            <input type="time" name="start_time" value="10:00" required><br>
            
            <label>End Time:</label>
            <input type="time" name="end_time" value="18:00" required><br>
            
            <label>Number of SAs:</label>
            <input type="number" name="num_assistants" min="1" value="1" required><br>
            
            <label>Alcohol Sales ($):</label>
            <input type="number" name="alc_sales" step="0.01" value="1000" required><br>
            
            <label>Food Sales ($):</label>
            <input type="number" name="food_sales" step="0.01" value="500" required><br>
            
            <label>Server Tips ($):</label>
            <input type="number" name="server_tips" step="0.01" value="200" required><br>
            
            <button type="submit">Calculate</button>
        </form>
        
        <p><i>Bartender: {restaurant.bartender_percent}% of alcohol sales</i></p>
        <p><i>Assistant: {restaurant.assistant_percent}% of food sales ÷ number of SAs</i></p>
    </div>
    """

@app.post("/calculate", response_class=HTMLResponse)
def calculate(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    num_assistants: int = Form(...),
    alc_sales: float = Form(...),
    food_sales: float = Form(...),
    server_tips: float = Form(...),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        
        # Calculate tipouts
        bartender_tipout = alc_sales * (restaurant.bartender_percent / 100)
        total_assistant_tipout = food_sales * (restaurant.assistant_percent / 100)
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
            alc_sales=alc_sales,
            food_sales=food_sales,
            server_tips=server_tips,
            bartender_tipout=bartender_tipout,
            assistant_tipout=total_assistant_tipout,
            assistant_per_person=assistant_per_person
        )
        
        db.add(tipout)
        db.commit()
        
        return STYLE + f"""
        <div class="container">
            <h2>✅ Tipout Calculated</h2>
            <p><strong>Server:</strong> <span class="highlight">{server_name}</span></p>
            <p><strong>Date:</strong> <span class="highlight">{date}</span></p>
            <p><strong>Shift:</strong> <span class="highlight">{start_time} - {end_time}</span></p>
            
            <hr>
            <p><strong>Alcohol Sales:</strong> <span class="highlight">${alc_sales:.2f}</span></p>
            <p><strong>Food Sales:</strong> <span class="highlight">${food_sales:.2f}</span></p>
            <p><strong>Server Tips:</strong> <span class="highlight">${server_tips:.2f}</span></p>
            
            <hr>
            <p>Bartender Tipout: <span class="highlight">${bartender_tipout:.2f}</span></p>
            <p>SA Tipout (÷{num_assistants}): <span class="highlight">${assistant_per_person:.2f}</span> per person</p>
            <p><strong>Server Keeps:</strong> <span class="highlight">${server_keep:.2f}</span></p>
            
            <form action="/dashboard" method="post">
                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                <button type="submit">Back to Dashboard</button>
            </form>
        </div>
        """
        
    except Exception as e:
        return STYLE + f"""
        <div class="container">
            <h2 class="error">Calculation Error: {str(e)}</h2>
            <a href="/">Home</a>
        </div>
        """

@app.get("/debug")
def debug_info(db: Session = Depends(get_db)):
    try:
        restaurants = db.query(Restaurant).all()
        tipouts = db.query(Tipout).all()
        
        return {
            "status": "Working!",
            "restaurants": len(restaurants),
            "tipouts": len(tipouts),
            "database_file": "tipout_simple.db"
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("🚀 Starting SIMPLE Tipout Calculator...")
    print("📱 Open: http://localhost:8080")
    print("🔍 Debug: http://localhost:8080/debug")
    uvicorn.run(app, host="0.0.0.0", port=8080)