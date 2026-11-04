from fastapi import FastAPI, Form, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from datetime import datetime
import json
import httpx
from typing import Optional, List
import asyncio
import uvicorn
from datetime import datetime, timedelta, date
import csv
import io
from fastapi.responses import StreamingResponse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from collections import defaultdict
import calendar



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
    server_names = Column(String, nullable=False)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tipouts = relationship("Tipout", back_populates="restaurant", cascade="all, delete-orphan")
    tip_positions = relationship("TipPosition", back_populates="restaurant", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="restaurant", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="restaurant", cascade="all, delete-orphan")

class TipPosition(Base):
    __tablename__ = "tip_positions"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    position_name = Column(String, nullable=False)
    percentage = Column(Float, nullable=False)
    calculation_base = Column(String, nullable=False, default="food_sales")
    employee_names = Column(Text, nullable=False, default="[]")  # JSON array of employee names
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="tip_positions")

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    employee_id = Column(String, unique=True, index=True)  # External ID like "EMP001"
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    hire_date = Column(DateTime, default=datetime.utcnow)
    wage_rate = Column(Float, nullable=True)
    position_title = Column(String, nullable=True)
    is_server = Column(Boolean, default=False)  # Whether they can receive tipouts from servers
    is_tip_recipient = Column(Boolean, default=False)  # Whether they receive tips
    is_manager = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="employees")
    tipouts_as_server = relationship("Tipout", back_populates="server_employee", foreign_keys="Tipout.server_employee_id")
    schedules = relationship("Schedule", back_populates="employee")

class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    schedule_date = Column(String, nullable=False)  # YYYY-MM-DD format
    start_time = Column(String, nullable=False)     # HH:MM format
    end_time = Column(String, nullable=False)       # HH:MM format
    position = Column(String, nullable=True)        # What role they're working
    status = Column(String, default="scheduled")    # scheduled, confirmed, completed, no_show
    notes = Column(Text, nullable=True)
    is_recurring = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="schedules")
    employee = relationship("Employee", back_populates="schedules")

class Tipout(Base):
    __tablename__ = "tipouts"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    server_name = Column(String, nullable=False)  # Keep for backward compatibility
    server_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # New employee reference
    date = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    num_assistants = Column(Integer, nullable=False)
    total_alc_sales = Column(Float, nullable=False, default=0.0)
    total_food_sales = Column(Float, nullable=False, default=0.0)
    time_based_food_sales = Column(Float, nullable=False, default=0.0)
    server_tips = Column(Float, nullable=False)
    tipout_details = Column(Text, nullable=False, default="{}")
    toast_sync = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="tipouts")
    server_employee = relationship("Employee", back_populates="tipouts_as_server", foreign_keys=[server_employee_id])

# Create tables with error handling
try:
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")
except Exception as e:
    print(f"Database creation error: {e}")

# Migration function for existing data
def migrate_existing_data(db: Session):
    """Migration for existing restaurants and data migration"""
    try:
        # First, check if we need to add the server_employee_id column
        try:
            # Try to query the column - if it fails, we need to add it
            db.execute("SELECT server_employee_id FROM tipouts LIMIT 1")
            print("server_employee_id column already exists")
        except Exception:
            # Column doesn't exist, add it
            print("Adding server_employee_id column to tipouts table")
            db.execute("ALTER TABLE tipouts ADD COLUMN server_employee_id INTEGER")
            db.commit()
            print("server_employee_id column added successfully")
        
        # Check if we need to migrate server names to employees
        restaurants_without_employees = db.query(Restaurant).filter(
            ~Restaurant.id.in_(db.query(Employee.restaurant_id).distinct())
        ).all()
        
        for restaurant in restaurants_without_employees:
            try:
                server_names = json.loads(restaurant.server_names) if restaurant.server_names else []
                
                for idx, server_name in enumerate(server_names):
                    if server_name and server_name.strip() and server_name != "Other":
                        # Create employee record
                        employee = Employee(
                            restaurant_id=restaurant.id,
                            employee_id=f"EMP{restaurant.id:03d}{idx+1:03d}",
                            first_name=server_name.split()[0] if server_name.split() else server_name,
                            last_name=" ".join(server_name.split()[1:]) if len(server_name.split()) > 1 else "",
                            position_title="Server",
                            is_server=True,
                            is_tip_recipient=False
                        )
                        db.add(employee)
                
                db.commit()
                print(f"Migrated {len([s for s in server_names if s != 'Other'])} employees for {restaurant.name}")
                
            except Exception as e:
                print(f"Error migrating employees for {restaurant.name}: {e}")
                db.rollback()
        
        # Link existing tipouts to employee records where possible
        try:
            unlinked_tipouts = db.query(Tipout).filter(Tipout.server_employee_id.is_(None)).all()
            linked_count = 0
            
            for tipout in unlinked_tipouts:
                # Find matching employee by name
                employee = db.query(Employee).filter(
                    Employee.restaurant_id == tipout.restaurant_id,
                    Employee.is_server == True,
                    Employee.is_active == True
                ).filter(
                    (Employee.first_name + ' ' + Employee.last_name == tipout.server_name) |
                    (Employee.first_name == tipout.server_name)
                ).first()
                
                if employee:
                    tipout.server_employee_id = employee.id
                    linked_count += 1
            
            if linked_count > 0:
                db.commit()
                print(f"Linked {linked_count} existing tipouts to employee records")
        
        except Exception as e:
            print(f"Error linking tipouts to employees: {e}")
            db.rollback()
        
        print("Employee migration completed")
    except Exception as e:
        print(f"Migration error: {e}")
        db.rollback()

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        migrate_existing_data(db)
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
        self.base_url = "http://localhost:8001"
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

.employee-list {
    background: white;
    padding: 15px;
    border-radius: 8px;
    margin: 10px 0;
    border: 1px solid #ddd;
}

.employee-tag {
    display: inline-block;
    background: var(--primary);
    color: white;
    padding: 5px 10px;
    margin: 3px;
    border-radius: 15px;
    font-size: 0.9em;
    position: relative;
}

.employee-tag .remove-employee {
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 50%;
    width: 20px;
    height: 20px;
    font-size: 12px;
    margin-left: 8px;
    cursor: pointer;
    line-height: 1;
}

.position-item {
    background: rgba(67, 198, 172, 0.1);
    padding: 20px;
    margin: 10px 0;
    border-radius: 10px;
    border-left: 4px solid var(--primary);
    position: relative;
}

.position-item h4 {
    margin: 0 0 10px 0;
    color: var(--secondary);
}

.position-details {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}

.position-info {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
}

.position-info span {
    background: white;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.9em;
    color: var(--dark);
}

.delete-btn {
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

.add-position-form {
    background: var(--light);
    padding: 20px;
    border-radius: 10px;
    margin: 20px 0;
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

/* Enhanced Daily Operations Styles */
.daily-summary-widget {
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    padding: 20px;
    border-radius: 15px;
    margin: 20px 0;
}

.daily-summary-widget h3 {
    color: white;
    margin-bottom: 15px;
    text-align: center;
}

.summary-metric {
    text-align: center;
    padding: 10px;
}

.metric-value {
    font-size: 2em;
    font-weight: bold;
    line-height: 1;
}

.metric-label {
    font-size: 0.9em;
    opacity: 0.9;
    margin-top: 5px;
}

.quick-actions-bar {
    background: var(--light);
    padding: 20px;
    border-radius: 10px;
    margin: 20px 0;
}

.quick-actions-bar h3 {
    margin-bottom: 15px;
    color: var(--secondary);
}

.action-buttons {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    justify-content: center;
}

.action-buttons .btn {
    flex: 1;
    min-width: 150px;
}

.progress-container {
    margin: 20px 0;
}

.server-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 20px;
    margin: 20px 0;
}

.server-card {
    background: white;
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    border-left: 4px solid var(--primary);
    position: relative;
}

.server-card.completed {
    border-left-color: var(--success);
    background: rgba(46, 204, 113, 0.05);
}

.server-card.pending {
    border-left-color: var(--warning);
    background: rgba(243, 156, 18, 0.05);
}

.server-status {
    position: absolute;
    top: 10px;
    right: 15px;
    font-size: 0.8em;
    font-weight: bold;
    padding: 5px 10px;
    border-radius: 15px;
    background: var(--light);
    color: var(--secondary);
}

.completed .server-status {
    background: var(--success);
    color: white;
}

.pending .server-status {
    background: var(--warning);
    color: white;
}

.server-info h4 {
    margin: 0 0 15px 0;
    color: var(--secondary);
    font-size: 1.3em;
}

.shift-details {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-bottom: 15px;
}

.shift-details span {
    font-size: 0.9em;
    color: var(--dark);
    background: rgba(255,255,255,0.8);
    padding: 5px 8px;
    border-radius: 5px;
}

.tipout-breakdown {
    background: rgba(67, 198, 172, 0.1);
    padding: 10px;
    border-radius: 5px;
    font-size: 0.85em;
    line-height: 1.4;
    margin-bottom: 15px;
}

.server-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
}

.btn-sm {
    padding: 6px 12px;
    font-size: 0.85em;
    min-width: auto;
}

.operations-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 30px;
    padding-top: 20px;
    border-top: 1px solid var(--light);
}

@media (max-width: 768px) {
    .server-grid {
        grid-template-columns: 1fr;
    }
    
    .action-buttons {
        flex-direction: column;
    }
    
    .action-buttons .btn {
        min-width: auto;
        margin: 5px 0;
    }
    
    .operations-footer {
        flex-direction: column;
        gap: 15px;
    }
}

.success {
    color: var(--success);
    font-weight: bold;
    background: rgba(46, 204, 113, 0.1);
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
}

.employee-selection {
    background: white;
    padding: 15px;
    border-radius: 8px;
    margin: 10px 0;
    border: 1px solid #ddd;
}

.employee-checkbox {
    display: flex;
    align-items: center;
    margin: 8px 0;
    padding: 8px;
    background: var(--light);
    border-radius: 5px;
}

.employee-checkbox input[type="checkbox"] {
    margin-right: 10px;
    width: auto;
}

.employee-checkbox label {
    margin-bottom: 0;
    cursor: pointer;
    flex: 1;
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
    .position-details { flex-direction: column; align-items: flex-start; }
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
// Add these to your existing script section

function editTipout(serverName, restaurantId, date) {
    // Create a form to edit existing tipout
    const form = document.createElement('form');
    form.method = 'post';
    form.action = '/calculate_tipout';
    
    const inputs = [
        {name: 'restaurant_id', value: restaurantId},
        {name: 'server_name', value: serverName},
        {name: 'date', value: date}
    ];
    
    inputs.forEach(input => {
        const hiddenInput = document.createElement('input');
        hiddenInput.type = 'hidden';
        hiddenInput.name = input.name;
        hiddenInput.value = input.value;
        form.appendChild(hiddenInput);
    });
    
    document.body.appendChild(form);
    form.submit();
}

function markShiftComplete(restaurantId, date) {
    if (confirm('Mark this shift as complete? This will finalize all tipouts for today.')) {
        // You can add additional logic here like sending notifications
        alert('Shift marked as complete! All tipouts have been finalized.');
        
        // Optionally redirect to summary
        const form = document.createElement('form');
        form.method = 'post';
        form.action = '/shift_summary';
        
        const inputs = [
            {name: 'restaurant_id', value: restaurantId},
            {name: 'date', value: date}
        ];
        
        inputs.forEach(input => {
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = input.name;
            hiddenInput.value = input.value;
            form.appendChild(hiddenInput);
        });
        
        document.body.appendChild(form);
        form.submit();
    }
}

function goBackToDaily(restaurantId) {
    const form = document.createElement('form');
    form.method = 'post';
    form.action = '/daily_status';
    
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.name = 'restaurant_id';
    hiddenInput.value = restaurantId;
    form.appendChild(hiddenInput);
    
    document.body.appendChild(form);
    form.submit();
}

// Add to your existing JavaScript functions
</script>
<script>
function removeEmployee(positionId, employeeName, restaurantId) {
    if (confirm(`Remove ${employeeName} from this position?`)) {
        fetch('/remove_employee', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `position_id=${positionId}&employee_name=${encodeURIComponent(employeeName)}&restaurant_id=${restaurantId}`
        })
        .then(response => response.text())
        .then(html => {
            document.body.innerHTML = html;
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error removing employee');
        });
    }
}

function toggleEmployeeForm(positionId) {
    const form = document.getElementById(`employeeForm_${positionId}`);
    const button = document.getElementById(`employeeBtn_${positionId}`);
    
    if (form.style.display === 'none' || form.style.display === '') {
        form.style.display = 'block';
        button.textContent = 'Cancel';
        button.className = 'btn btn-light';
    } else {
        form.style.display = 'none';
        button.textContent = '+ Add Employee';
        button.className = 'btn btn-success';
    }
}
function confirmDeletePosition(positionId, restaurantId) {
    if (confirm('Are you sure you want to delete this tip position? This will affect all future tipout calculations.')) {
        deletePosition(positionId, restaurantId);
    }
}

function deletePosition(positionId, restaurantId) {
    fetch('/delete_position', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `position_id=${positionId}&restaurant_id=${restaurantId}`
    })
    .then(response => response.text())
    .then(html => {
        document.body.innerHTML = html;
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting position');
    });
}

function toggleAddPositionForm() {
    const form = document.getElementById('addPositionForm');
    const button = document.getElementById('addPositionBtn');
    
    if (form.style.display === 'none' || form.style.display === '') {
        form.style.display = 'block';
        button.textContent = 'Cancel';
        button.className = 'btn btn-light';
    } else {
        form.style.display = 'none';
        button.textContent = '+ Add New Position';
        button.className = 'btn btn-success';
    }
}

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
                <h1>Restaurant Tipout Management</h1>
                <p>Professional tipout calculations with custom positions & Toast POS integration</p>
            </div>
            
            <div style="text-align: center;">
                <a href="/login" class="btn btn-primary">Login to Restaurant</a>
                <a href="/register" class="btn btn-secondary">Register New Restaurant</a>
            </div>
        </div>
    </div>
    """
@app.get("/daily_status", response_class=HTMLResponse)
async def daily_status_get(restaurant_id: int, db: Session = Depends(get_db)):
    """GET version of daily status for navigation"""
    return await enhanced_daily_status(restaurant_id, db)

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return STYLE + """
    <div class="container">
        <div class="card">
            <div class="breadcrumb">
                <a href="/">Home</a> → Login
            </div>
            
            <div class="header">
                <h2>Restaurant Login</h2>
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
                <h2>Register New Restaurant</h2>
            </div>
            
            <form action="/create_restaurant" method="post">
                <div class="form-group">
                    <label>Restaurant Name:</label>
                    <input type="text" name="restaurant_name" required>
                </div>
                
                <h3>Toast POS Integration (Optional)</h3>
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
                
                <h3>Staff Management</h3>
                <div class="form-group">
                    <label>Server Names (comma separated):</label>
                    <input type="text" name="server_names" value="Alice,Bob,Charlie,Other" required>
                </div>
                
                <div style="text-align: center;">
                    <button type="submit" class="btn btn-success">Create Restaurant</button>
                    <button type="button" class="btn btn-light" onclick="window.location.href='/'">Cancel</button>
                </div>
            </form>
            
            <div style="margin-top: 20px; padding: 15px; background: var(--light); border-radius: 8px;">
                <p><strong>Note:</strong> You'll be able to set up custom tip positions after creating your restaurant.</p>
            </div>
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
                        <h3>Restaurant Already Exists</h3>
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
                        <h3>Invalid Server Names</h3>
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
            server_names=json.dumps(server_list)
        )
        
        db.add(new_restaurant)
        db.commit()
        db.refresh(new_restaurant)
        
        # Create default tip positions
        
        
        toast_status = ""
        if toast_client_id.strip():
            toast_status = '<div class="toast-status">Toast POS Integration Configured</div>'
        else:
            toast_status = '<div class="manual-entry">Manual Entry Mode - Toast Integration Available in Settings</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="success">
                    <h2>Restaurant Created Successfully!</h2>
                </div>
                {toast_status}
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{restaurant_name}</div>
                        <div class="summary-label">Restaurant Name</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">0</div>
                        <div class="summary-label">Tip Positions</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(server_list)}</div>
                        <div class="summary-label">Servers</div>
                    </div>
                </div>
                
                <p><strong>Servers:</strong> {', '.join(server_list)}</p>
                <div style="background: var(--warning); color: white; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center;">
                    <h3>Next Step: Set Up Tip Positions</h3>
                    <p>You'll need to create tip positions in Settings before you can calculate tipouts.</p>
                </div>
                
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
                    <h3>Database Error</h3>
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
                        <h3>Restaurant Not Found</h3>
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
                    <h3>Login Error</h3>
                    <p>Error during login: {str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <a href="/login" class="btn btn-primary">Try Again</a>
                </div>
            </div>
        </div>
        """

def restaurant_dashboard(restaurant_id: int, db: Session):
    """Enhanced dashboard with payroll exports access"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + """
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>Restaurant Not Found</h3>
                    </div>
                    <div style="text-align: center;">
                        <a href="/" class="btn btn-primary">Back to Home</a>
                    </div>
                </div>
            </div>
            """
        
        tip_positions_count = db.query(TipPosition).filter(TipPosition.restaurant_id == restaurant_id, TipPosition.is_active == True).count()
        
        toast_status = ""
        if restaurant.toast_client_id:
            toast_status = '<div class="toast-status">Toast POS Connected</div>'
        else:
            toast_status = '<div class="manual-entry">Manual Entry Mode</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → Dashboard
                </div>
                
                <div class="header">
                    <h1>{restaurant.name} - FUNCTION 1</h1>
                    {toast_status}
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{tip_positions_count}</div>
                        <div class="summary-label">Active Tip Positions</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(json.loads(restaurant.server_names))}</div>
                        <div class="summary-label">Total Servers</div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <form action="/daily_status" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">Daily Status & Tipout</button>
                    </form>
                    
                    <form action="/weekly_reports" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-success">Weekly Reports & Analytics</button>
                    </form>
                    
                    <form action="/payroll_exports" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-warning">Payroll Exports</button>
                    </form>
                    
                    <form action="/totals" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <label style="display: block; margin: 10px 0;">Select Date for Totals:</label>
                        <input type="date" name="date" required style="width: 200px; margin: 5px;">
                        <button type="submit" class="btn btn-secondary">View Daily Totals</button>
                    </form>
                    
                    <form action="/settings" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-light">Settings & Positions</button>
                    </form>

                    <form action="/payroll_exports" method="get" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-warning">Payroll Exports</button>
                    </form>
                </div>
                
                <div style="text-align: center;">
                    <a href="/" class="btn btn-light">Logout</a>
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
                    <h3>Dashboard Error</h3>
                    <p>{str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <a href="/" class="btn btn-primary">Back to Home</a>
                </div>
            </div>
        </div>
        """

@app.post("/daily_status", response_class=HTMLResponse)
async def enhanced_daily_status(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Check if tip positions exist
        tip_positions_count = db.query(TipPosition).filter(TipPosition.restaurant_id == restaurant_id, TipPosition.is_active == True).count()
        if tip_positions_count == 0:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>No Tip Positions Configured</h3>
                        <p>You need to set up tip positions before you can calculate tipouts.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/settings" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Set Up Positions</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        today_display = date.today().strftime("%A, %B %d, %Y")
        
        # Get servers and tipout status
        all_servers = json.loads(restaurant.server_names)
        today_tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == today
        ).all()
        
        tipped_out_servers = {tipout.server_name for tipout in today_tipouts}
        
        # Calculate daily totals
        total_revenue = sum(tipout.total_alc_sales + tipout.total_food_sales for tipout in today_tipouts)
        total_server_tips = sum(tipout.server_tips for tipout in today_tipouts)
        total_tipout_amount = 0.0
        
        for tipout in today_tipouts:
            try:
                details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
                for position_data in details.values():
                    total_tipout_amount += position_data.get('amount', 0.0)
            except:
                pass
        
        # Progress calculations
        completed_count = len(tipped_out_servers)
        working_count = len([s for s in all_servers if s != "Other"])  # Exclude "Other" from working count
        progress_percentage = (completed_count / working_count * 100) if working_count > 0 else 0
        
        # Generate enhanced server cards with quick actions
        server_cards = generate_enhanced_server_cards(all_servers, today_tipouts, tipped_out_servers, restaurant.id, today)
        
        # Generate daily summary widget
        summary_widget = generate_daily_summary_widget(total_revenue, total_server_tips, total_tipout_amount, completed_count, working_count)
        
        # Generate quick actions bar
        quick_actions = generate_quick_actions_bar(restaurant.id, today, working_count, completed_count)
        
        return STYLE + f"""
        <div class="container">
            <div class="card" style="max-width: 1000px;">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Daily Operations
                </div>
                
                <div class="header">
                    <h2>Daily Operations Center</h2>
                    <p><strong>{restaurant.name}</strong> | {today_display}</p>
                </div>
                
                {quick_actions}
                {summary_widget}
                
                <div class="progress-container">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h3>Tipout Progress</h3>
                        <span style="font-size: 1.2em; font-weight: bold; color: var(--primary);">
                            {completed_count}/{working_count} Complete ({progress_percentage:.0f}%)
                        </span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {progress_percentage}%;"></div>
                    </div>
                </div>
                
                <div class="server-grid">
                    {server_cards}
                </div>
                
                <div class="operations-footer">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Dashboard</button>
                    </form>
                    
                    <form action="/shift_summary" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <input type="hidden" name="date" value="{today}">
                        <button type="submit" class="btn btn-primary">End of Shift Summary</button>
                    </form>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Enhanced daily status error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Daily Operations</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

def generate_enhanced_server_cards(all_servers, today_tipouts, tipped_out_servers, restaurant_id, today):
    """Generate enhanced server cards with quick actions and status"""
    cards = []
    
    for server in all_servers:
        if server == "Other":
            continue  # Skip "Other" in main display
            
        if server in tipped_out_servers:
            tipout = next(t for t in today_tipouts if t.server_name == server)
            try:
                details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
                detail_items = []
                total_tipout = 0
                
                for pos_name, pos_data in details.items():
                    amount = pos_data.get('amount', 0)
                    employees = pos_data.get('employees', [])
                    employee_list = ', '.join(employees) if employees else f"{pos_data.get('num_staff', 0)} staff"
                    detail_items.append(f"{pos_name}: ${amount:.2f} → {employee_list}")
                    total_tipout += amount
                
                detail_text = "<br>".join(detail_items)
                net_tips = tipout.server_tips - total_tipout
                
            except:
                detail_text = "Details unavailable"
                net_tips = tipout.server_tips
            
            cards.append(f"""
            <div class="server-card completed">
                <div class="server-status">✓ COMPLETE</div>
                <div class="server-info">
                    <h4>{server}</h4>
                    <div class="shift-details">
                        <span>Shift: {tipout.start_time} - {tipout.end_time}</span>
                        <span>Tips Earned: ${tipout.server_tips:.2f}</span>
                        <span>Net Tips: ${net_tips:.2f}</span>
                    </div>
                    <div class="tipout-breakdown">
                        {detail_text}
                    </div>
                </div>
                <div class="server-actions">
                    <button class="btn btn-warning btn-sm" onclick="editTipout('{server}', {restaurant_id}, '{today}')">Edit</button>
                    <button class="btn btn-danger btn-sm" onclick="confirmDelete({tipout.id}, {restaurant_id})">Delete</button>
                </div>
            </div>
            """)
        else:
            cards.append(f"""
            <div class="server-card pending">
                <div class="server-status">⏳ PENDING</div>
                <div class="server-info">
                    <h4>{server}</h4>
                    <div class="shift-details">
                        <span>Ready for tipout calculation</span>
                    </div>
                </div>
                <div class="server-actions">
                    <form action="/quick_tipout" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                        <input type="hidden" name="server_name" value="{server}">
                        <input type="hidden" name="date" value="{today}">
                        <button type="submit" class="btn btn-primary btn-sm">Quick Entry</button>
                    </form>
                    <form action="/calculate_tipout" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                        <input type="hidden" name="server_name" value="{server}">
                        <input type="hidden" name="date" value="{today}">
                        <button type="submit" class="btn btn-secondary btn-sm">Full Entry</button>
                    </form>
                </div>
            </div>
            """)
    
    return "".join(cards)

def generate_daily_summary_widget(total_revenue, total_server_tips, total_tipout_amount, completed_count, working_count):
    """Generate the daily summary widget"""
    efficiency_rate = (total_tipout_amount / total_revenue * 100) if total_revenue > 0 else 0
    avg_tips_per_server = total_server_tips / completed_count if completed_count > 0 else 0
    
    efficiency_color = "var(--success)" if 3 <= efficiency_rate <= 8 else "var(--warning)"
    
    return f"""
    <div class="daily-summary-widget">
        <h3>Today's Summary</h3>
        <div class="summary-grid">
            <div class="summary-metric">
                <div class="metric-value">${total_revenue:.0f}</div>
                <div class="metric-label">Total Sales</div>
            </div>
            <div class="summary-metric">
                <div class="metric-value">${total_server_tips:.0f}</div>
                <div class="metric-label">Server Tips</div>
            </div>
            <div class="summary-metric">
                <div class="metric-value">${total_tipout_amount:.0f}</div>
                <div class="metric-label">Total Tipouts</div>
            </div>
            <div class="summary-metric">
                <div class="metric-value" style="color: {efficiency_color};">{efficiency_rate:.1f}%</div>
                <div class="metric-label">Tipout Rate</div>
            </div>
            <div class="summary-metric">
                <div class="metric-value">${avg_tips_per_server:.0f}</div>
                <div class="metric-label">Avg Tips/Server</div>
            </div>
            <div class="summary-metric">
                <div class="metric-value">{completed_count}/{working_count}</div>
                <div class="metric-label">Completed</div>
            </div>
        </div>
    </div>
    """

def generate_quick_actions_bar(restaurant_id, today, working_count, completed_count):
    """Generate quick actions toolbar"""
    all_complete = completed_count >= working_count
    complete_color = "var(--success)" if all_complete else "var(--primary)"
    
    return f"""
    <div class="quick-actions-bar">
        <h3>Quick Actions</h3>
        <div class="action-buttons">
            <form action="/quick_tipout_all" method="post" style="display: inline;" onsubmit="console.log('Form submitting to /quick_tipout_all');">
                <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                <input type="hidden" name="date" value="{today}">
                <button type="submit" class="btn btn-primary" {'disabled' if all_complete else ''} onclick="console.log('Calculate all button clicked');">
                    Calculate All Remaining
                </button>
            </form>
            
            <form action="/shift_summary" method="post" style="display: inline;">
                <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                <input type="hidden" name="date" value="{today}">
                <button type="submit" class="btn btn-warning">
                    View Daily Totals
                </button>
            </form>
            
            <form action="/export_daily" method="post" style="display: inline;">
                <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                <input type="hidden" name="date" value="{today}">
                <button type="submit" class="btn btn-secondary">
                    Export Today's Data
                </button>
            </form>
            
            <button class="btn" style="background: {complete_color}; color: white;" onclick="markShiftComplete({restaurant_id}, '{today}')" {'disabled' if not all_complete else ''}>
                {'✓ Shift Complete' if all_complete else f'Mark Complete ({completed_count}/{working_count})'}
            </button>
        </div>
    </div>
    """


@app.post("/quick_tipout_all", response_class=HTMLResponse)
async def quick_tipout_all(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    """Calculate tipouts for all remaining servers"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get servers who haven't been tipped out yet
        all_servers = json.loads(restaurant.server_names)
        today_tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == date
        ).all()
        tipped_out_servers = {tipout.server_name for tipout in today_tipouts}
        remaining_servers = [s for s in all_servers if s not in tipped_out_servers and s != "Other"]
        
        if not remaining_servers:
            # Redirect back to daily status
            return await enhanced_daily_status(restaurant_id, db)
        
        # Show form to calculate all remaining
        server_options = []
        for server in remaining_servers:
            server_options.append(f"""
            <div class="server-bulk-item">
                <label>
                    <input type="checkbox" name="bulk_servers" value="{server}" checked>
                    <strong>{server}</strong>
                </label>
                <div class="bulk-server-inputs">
                    <input type="time" name="start_time_{server}" value="17:00" placeholder="Start">
                    <input type="time" name="end_time_{server}" value="23:00" placeholder="End">
                    <input type="number" name="total_sales_{server}" step="0.01" placeholder="Total Sales" required>
                    <input type="number" name="server_tips_{server}" step="0.01" placeholder="Tips" required>
                </div>
            </div>
            """)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="header">
                    <h2>Calculate All Remaining Tipouts</h2>
                    <p>{len(remaining_servers)} servers pending</p>
                </div>
                
                <form action="/process_bulk_tipouts" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                    <input type="hidden" name="date" value="{date}">
                    
                    <div class="bulk-entry-container">
                        {"".join(server_options)}
                    </div>
                    
                    <div style="text-align: center; margin-top: 20px;">
                        <button type="submit" class="btn btn-success">Calculate Selected Tipouts</button>
                        <form action="/daily_status" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-light">Cancel</button>
                        </form>
                    </div>
                </form>
            </div>
        </div>
        
        <style>
        .bulk-entry-container {{
            display: grid;
            gap: 15px;
            margin: 20px 0;
        }}
        
        .server-bulk-item {{
            background: var(--light);
            padding: 15px;
            border-radius: 8px;
            border-left: 3px solid var(--primary);
        }}
        
        .bulk-server-inputs {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }}
        
        .bulk-server-inputs input {{
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        </style>
        """
    except Exception as e:
        print(f"Quick tipout all error: {e}")
        return await enhanced_daily_status(restaurant_id, db)

@app.post("/shift_summary", response_class=HTMLResponse)
def shift_summary(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    """Generate end of shift summary"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get today's data
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == date
        ).all()
        
        if not tipouts:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>No Data for Shift Summary</h3>
                        <p>No tipouts calculated for {date} yet.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/daily_status" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Daily Operations</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        # Use your existing totals calculation logic
        return show_totals(restaurant_id, date, db)
        
    except Exception as e:
        print(f"Shift summary error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Shift Summary</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/export_daily", response_class=HTMLResponse)
def export_daily_data(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    """Export today's data"""
    try:
        # Redirect to payroll exports with today's date pre-filled
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="header">
                    <h2>Export Daily Data</h2>
                    <p>Exporting data for {date}</p>
                </div>
                
                <form action="/generate_payroll_export" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                    <input type="hidden" name="payroll_provider" value="generic">
                    <input type="hidden" name="export_format" value="excel">
                    <input type="hidden" name="pay_period" value="custom">
                    <input type="hidden" name="week_option" value="custom">
                    <input type="hidden" name="start_date" value="{date}">
                    <input type="hidden" name="end_date" value="{date}">
                    <input type="hidden" name="include_summary" value="true">
                    <input type="hidden" name="separate_positions" value="true">
                    
                    <div style="text-align: center;">
                        <button type="submit" class="btn btn-primary">Download Excel Export</button>
                        <form action="/daily_status" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-light">Cancel</button>
                        </form>
                    </div>
                </form>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Export daily error: {e}")
        return STYLE + f"<div class='container'><div class='card'><div class='error'>Export error: {str(e)}</div></div></div>"

@app.post("/process_quick_tipout", response_class=HTMLResponse)
async def process_quick_tipout(
    request: Request,
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    total_sales: float = Form(...),
    server_tips: float = Form(...),
    is_quick_entry: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Process the quick tipout entry"""
    try:
        # Split total sales between food and alcohol (80/20 split as default)
        food_sales_shift = total_sales * 0.8
        alc_sales = total_sales * 0.2
        
        # Use the existing process_tipout logic but with simplified inputs
        return await process_tipout(
            request=request,
            restaurant_id=restaurant_id,
            server_name=server_name,
            date=date,
            start_time=start_time,
            end_time=end_time,
            alc_sales=alc_sales,
            food_sales_shift=food_sales_shift,
            server_tips=server_tips,
            is_override=False,
            db=db
        )
        
    except Exception as e:
        print(f"Process quick tipout error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Processing Quick Tipout</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """


@app.post("/quick_tipout", response_class=HTMLResponse)
async def quick_tipout_entry(
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    db: Session = Depends(get_db)
):
    """Quick tipout entry with minimal form fields"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        tip_positions = db.query(TipPosition).filter(
            TipPosition.restaurant_id == restaurant_id,
            TipPosition.is_active == True
        ).all()
        
        # Check for existing tipout
        existing_tipout = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.server_name == server_name,
            Tipout.date == date
        ).first()
        
        override_warning = ""
        if existing_tipout:
            override_warning = f"""
            <div class="warning">
                <h3>Updating Existing Tipout</h3>
                <p>{server_name} already has a tipout for {date}. This will replace it.</p>
            </div>
            """
        
        # Generate simplified position selection
        position_widgets = []
        for position in tip_positions:
            try:
                position_employee_names = json.loads(position.employee_names) if position.employee_names else []
            except:
                position_employee_names = []
            
            base_label = {
                "food_sales": "Food Sales",
                "alcohol_sales": "Alcohol Sales",
                "total_sales": "Total Sales"
            }.get(position.calculation_base, position.calculation_base)
            
            # Find employees scheduled for this date who are also assigned to this position
            scheduled_employees = db.query(Employee).join(Schedule).filter(
                Employee.restaurant_id == restaurant_id,
                Employee.is_active == True,
                Schedule.schedule_date == date,
                Schedule.restaurant_id == restaurant_id
            ).all()
            
            # Filter to only employees assigned to this position
            available_employees = []
            for emp in scheduled_employees:
                full_name = f"{emp.first_name} {emp.last_name}".strip()
                if full_name in position_employee_names:
                    available_employees.append(full_name)
            
            if available_employees:
                employee_checkboxes = []
                for emp_name in available_employees:
                    employee_checkboxes.append(f"""
                    <label class="quick-checkbox">
                        <input type="checkbox" name="employee_{position.id}" value="{emp_name}">
                        <span>{emp_name}</span>
                    </label>
                    """)
                
                position_widgets.append(f"""
                <div class="quick-position-widget">
                    <h4>{position.position_name}</h4>
                    <p>{position.percentage}% of {base_label}</p>
                    <div class="employee-grid">
                        {"".join(employee_checkboxes)}
                    </div>
                </div>
                """)
            elif position_employee_names:
                # Position has assigned employees but none are scheduled
                position_widgets.append(f"""
                <div class="quick-position-widget">
                    <h4>{position.position_name}</h4>
                    <p>{position.percentage}% of {base_label}</p>
                    <div style="color: var(--warning); font-size: 0.9em; margin-bottom: 10px;">
                        No scheduled employees for this position today
                    </div>
                    <div class="form-group">
                        <label>Number working:</label>
                        <input type="number" name="num_{position.id}" min="0" max="10" value="0" style="width: 80px;">
                    </div>
                </div>
                """)
            else:
                position_widgets.append(f"""
                <div class="quick-position-widget">
                    <h4>{position.position_name}</h4>
                    <p>{position.percentage}% of {base_label}</p>
                    <div class="form-group">
                        <label>Number working:</label>
                        <input type="number" name="num_{position.id}" min="0" max="10" value="1" style="width: 80px;">
                    </div>
                </div>
                """)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → 
                    <form action="/daily_status" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" style="background: none; border: none; color: var(--primary); text-decoration: underline; cursor: pointer;">Daily Operations</button>
                    </form> → Quick Entry
                </div>
                
                <div class="header">
                    <h2>Quick Tipout Entry</h2>
                    <p><strong>{server_name}</strong> | {date}</p>
                </div>
                
                {override_warning}
                
                <form action="/process_quick_tipout" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <input type="hidden" name="server_name" value="{server_name}">
                    <input type="hidden" name="date" value="{date}">
                    <input type="hidden" name="is_quick_entry" value="true">
                    
                    <div class="quick-entry-grid">
                        <div class="essential-info">
                            <h3>Essential Info</h3>
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Start Time:</label>
                                    <input type="time" name="start_time" value="17:00" required>
                                </div>
                                <div class="form-group">
                                    <label>End Time:</label>
                                    <input type="time" name="end_time" value="23:00" required>
                                </div>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Total Sales ($):</label>
                                    <input type="number" name="total_sales" step="0.01" min="0" placeholder="1500.00" required>
                                </div>
                                <div class="form-group">
                                    <label>Server Tips ($):</label>
                                    <input type="number" name="server_tips" step="0.01" min="0" placeholder="200.00" required>
                                </div>
                            </div>
                        </div>
                        
                        <div class="staff-selection">
                            <h3>Staff Working Today</h3>
                            <div class="position-grid">
                                {"".join(position_widgets)}
                            </div>
                        </div>
                    </div>
                    
                    <div style="text-align: center; margin-top: 30px;">
                        <button type="submit" class="btn btn-success">Calculate Tipout</button>
                        <button type="button" class="btn btn-light" onclick="goBackToDaily({restaurant.id})">Cancel</button>
                    </div>
                </form>
            </div>
        </div>
        
        <style>
        .quick-entry-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin: 20px 0;
        }}
        
        .essential-info, .staff-selection {{
            background: var(--light);
            padding: 20px;
            border-radius: 10px;
        }}
        
        .position-grid {{
            display: grid;
            gap: 15px;
        }}
        
        .quick-position-widget {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            border-left: 3px solid var(--primary);
        }}
        
        .employee-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
            margin-top: 10px;
        }}
        
        .quick-checkbox {{
            display: flex;
            align-items: center;
            background: var(--light);
            padding: 8px;
            border-radius: 5px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        
        .quick-checkbox:hover {{
            background: var(--primary);
            color: white;
        }}
        
        .quick-checkbox input {{
            margin-right: 8px;
            width: auto;
        }}
        
        @media (max-width: 768px) {{
            .quick-entry-grid {{
                grid-template-columns: 1fr;
                gap: 20px;
            }}
            
            .employee-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        </style>
        """
    except Exception as e:
        print(f"Quick tipout entry error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Quick Entry</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

def get_scheduled_info_for_date(restaurant_id: int, date: str, db: Session):
    """Get information about who's scheduled for a specific date"""
    try:
        scheduled_employees = db.query(Employee).join(Schedule).filter(
            Employee.restaurant_id == restaurant_id,
            Employee.is_active == True,
            Schedule.schedule_date == date,
            Schedule.restaurant_id == restaurant_id
        ).all()
        
        if not scheduled_employees:
            return {
                "count": 0,
                "message": f"No employees scheduled for {date}. Tipout calculations will use manual entry.",
                "employees": []
            }
        
        employee_names = [f"{emp.first_name} {emp.last_name}".strip() for emp in scheduled_employees]
        
        return {
            "count": len(scheduled_employees),
            "message": f"{len(scheduled_employees)} employees scheduled for {date}",
            "employees": employee_names
        }
    except Exception as e:
        return {
            "count": 0,
            "message": f"Error checking schedule: {str(e)}",
            "employees": []
        }
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
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        tip_positions = db.query(TipPosition).filter(
            TipPosition.restaurant_id == restaurant_id,
            TipPosition.is_active == True
        ).all()
        
        if not tip_positions:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>No Tip Positions Configured</h3>
                        <p>Please set up tip positions in Settings before calculating tipouts.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/settings" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Go to Settings</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        existing_tipout = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.server_name == server_name,
            Tipout.date == date
        ).first()
        
        show_override_warning = bool(existing_tipout)
        
        alc_sales = 0.0
        food_sales_shift = 0.0
        start_time = "17:00"
        end_time = "23:00"
        hours_worked = 6.0
        toast_data_available = False
        
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
                <h3>Server Already Tipped Out Today</h3>
                <p><strong>{server_name}</strong> already has a tipout for {date}.</p>
                <p>Continuing will replace the existing tipout.</p>
            </div>
            """
        
        data_source_info = ""
        if toast_data_available:
            data_source_info = f"""
            <div class="toast-status">
                <h3>Toast Data Retrieved</h3>
                <p>Sales data automatically loaded from Toast POS</p>
            </div>
            """
        else:
            data_source_info = f"""
            <div class="manual-entry">
                <h3>Manual Entry Required</h3>
                <p>Toast data unavailable - please enter sales manually</p>
            </div>
            """
        # Add scheduling info
        schedule_info = get_scheduled_info_for_date(restaurant_id, date, db)
        schedule_info_html = f"""
        <div style="background: var(--{'success' if schedule_info['count'] > 0 else 'warning'}); color: white; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h4>📅 Scheduled Staff for {date}</h4>
            <p>{schedule_info['message']}</p>
            {f"<p><strong>Scheduled:</strong> {', '.join(schedule_info['employees'])}</p>" if schedule_info['employees'] else ""}
        </div>
        """
        
        position_fields = []
        for position in tip_positions:
            base_label = {
                "food_sales": "Food Sales",
                "alcohol_sales": "Alcohol Sales", 
                "total_sales": "Total Sales"
            }.get(position.calculation_base, position.calculation_base)
            
            # Get employees for this position who are scheduled for this date
            try:
                position_employee_names = json.loads(position.employee_names) if position.employee_names else []
            except:
                position_employee_names = []
            
            # Find employees scheduled for this date who are also assigned to this position
            scheduled_employees = db.query(Employee).join(Schedule).filter(
                Employee.restaurant_id == restaurant_id,
                Employee.is_active == True,
                Schedule.schedule_date == date,
                Schedule.restaurant_id == restaurant_id
            ).all()
            
            # Filter to only employees assigned to this position
            available_employees = []
            for emp in scheduled_employees:
                full_name = f"{emp.first_name} {emp.last_name}".strip()
                if full_name in position_employee_names:
                    available_employees.append(full_name)
            
            # Create employee checkboxes
            employee_checkboxes = []
            if available_employees:
                for emp_name in available_employees:
                    employee_checkboxes.append(f"""
                    <div class="employee-checkbox">
                        <input type="checkbox" name="employee_{position.id}" value="{emp_name}" id="emp_{position.id}_{emp_name.replace(' ', '_')}">
                        <label for="emp_{position.id}_{emp_name.replace(' ', '_')}">{emp_name}</label>
                    </div>
                    """)
                employee_selection_html = "".join(employee_checkboxes)
            elif position_employee_names:
                # Position has assigned employees but none are scheduled
                employee_selection_html = f"""
                <div style="color: var(--warning); background: rgba(243, 156, 18, 0.1); padding: 10px; border-radius: 5px;">
                    <p><strong>No scheduled employees for this position on {date}</strong></p>
                    <p>Assigned employees: {', '.join(position_employee_names)}</p>
                    <p>You can still manually enter the number working:</p>
                    <div class="form-group">
                        <label>Number of {position.position_name}s Working:</label>
                        <input type="number" name="num_{position.id}" min="0" max="20" value="0">
                    </div>
                </div>
                """
            else:
                # No employees configured for this position
                employee_selection_html = f"""
                <p style="color: var(--warning);">No employees configured for this position.</p>
                <div class="form-group">
                    <label>Number of {position.position_name}s Working:</label>
                    <input type="number" name="num_{position.id}" min="0" max="20" value="1" required>
                </div>
                """
            
            position_fields.append(f"""
            <div class="position-item">
                <h4>{position.position_name}</h4>
                <p>Calculation: {position.percentage}% of {base_label}</p>
                
                <div class="employee-selection">
                    <label><strong>Select employees working today:</strong></label>
                    {employee_selection_html}
                </div>
            </div>
            """)
        
        positions_html = "".join(position_fields)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Calculate Tipout
                </div>
                
                <div class="header">
                    <h2>Calculate Tipout for {server_name}</h2>
                    <p><strong>Date:</strong> {date}</p>
                </div>
                
                {override_warning}
                {data_source_info}
                {schedule_info_html}
                
                <form action="/process_tipout" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <input type="hidden" name="server_name" value="{server_name}">
                    <input type="hidden" name="date" value="{date}">
                    <input type="hidden" name="is_override" value="{show_override_warning}">
                    
                    <h3>Shift Information</h3>
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
                    
                    <h3>Sales Information</h3>
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
                    
                    <h3>Staff Working Today</h3>
                    {positions_html}
                    
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
                    <h3>Error</h3>
                    <p>An error occurred: {str(e)}</p>
                    <a href="/" class="btn btn-primary">Go Home</a>
                </div>
            </div>
        </div>
        """


@app.post("/quick_tipout_all", response_class=HTMLResponse)
def quick_tipout_all_simple(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    """Simplified version to test if route works"""
    try:
        print(f"DEBUG: quick_tipout_all called with restaurant_id={restaurant_id}, date={date}")
        
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get servers who haven't been tipped out yet
        all_servers = json.loads(restaurant.server_names)
        today_tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date == date
        ).all()
        tipped_out_servers = {tipout.server_name for tipout in today_tipouts}
        remaining_servers = [s for s in all_servers if s not in tipped_out_servers and s != "Other"]
        
        print(f"DEBUG: Found {len(remaining_servers)} remaining servers: {remaining_servers}")
        
        if not remaining_servers:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="success">
                        <h3>All Servers Complete!</h3>
                        <p>All servers have been tipped out for {date}.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/daily_status" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Daily Operations</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        # For now, just show which servers need tipouts
        server_list = "<br>".join([f"• {server}" for server in remaining_servers])
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="header">
                    <h2>Servers Needing Tipouts</h2>
                    <p>{date}</p>
                </div>
                
                <div class="warning">
                    <h3>Found {len(remaining_servers)} servers without tipouts:</h3>
                    <p>{server_list}</p>
                </div>
                
                <div style="text-align: center;">
                    <p>This feature is working! Now we can build the bulk entry form.</p>
                    <form action="/daily_status" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                        <button type="submit" class="btn btn-primary">Back to Daily Operations</button>
                    </form>
                </div>
            </div>
        </div>
        """
        
    except Exception as e:
        print(f"DEBUG: Error in quick_tipout_all: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Debug Error</h3>
                    <p>Error: {str(e)}</p>
                </div>
            </div>
        </div>
        """
@app.post("/process_tipout", response_class=HTMLResponse)
async def process_tipout(
    request: Request,
    restaurant_id: int = Form(...),
    server_name: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    alc_sales: float = Form(...),
    food_sales_shift: float = Form(...),
    server_tips: float = Form(...),
    is_override: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Enhanced tipout processing with proper staff number handling"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get tip positions
        tip_positions = db.query(TipPosition).filter(
            TipPosition.restaurant_id == restaurant_id,
            TipPosition.is_active == True
        ).all()
        
        # Get all form data to extract staff numbers
        # Get all form data to extract selected employees
        form_data = await request.form()
        
        # Extract selected employees for each position
        selected_employees = {}
        staff_numbers = {}
        
        for position in tip_positions:
            # Get selected employees
            employee_field_name = f"employee_{position.id}"
            selected_emp_names = form_data.getlist(employee_field_name)
            selected_employees[position.id] = selected_emp_names
            
            # If no employees selected, check for manual count (for positions without configured employees)
            if not selected_emp_names:
                field_name = f"num_{position.id}"
                try:
                    staff_count = int(form_data.get(field_name, 0))
                    staff_numbers[position.id] = max(0, staff_count)
                except (ValueError, TypeError):
                    staff_numbers[position.id] = 0
            else:
                staff_numbers[position.id] = len(selected_emp_names)
        
        # Calculate tipouts for each position with actual staff numbers
        tipout_details = {}
        total_tipout = 0.0
        calculation_breakdown = []
        
        for position in tip_positions:
            num_staff = staff_numbers.get(position.id, 1)
            
            # Skip positions with 0 staff
            if num_staff == 0:
                continue
                
            # Calculate base amount based on position settings
            if position.calculation_base == "alcohol_sales":
                base_amount = alc_sales
            elif position.calculation_base == "food_sales":
                base_amount = food_sales_shift
            else:  # total_sales
                base_amount = alc_sales + food_sales_shift
            
            # Calculate tip amount
            position_total = base_amount * (position.percentage / 100)
            per_person = position_total / num_staff if num_staff > 0 else 0
            
            # Get employee info for this position
            employees_working = selected_employees.get(position.id, [])
            
            tipout_details[position.position_name] = {
                "total": position_total,
                "per_person": per_person,
                "num_staff": num_staff,
                "percentage": position.percentage,
                "base": position.calculation_base,
                "base_amount": base_amount,
                "amount": position_total,
                "employees": employees_working  # Store who specifically is getting tipped
            }
            
            # Track calculation for display
            employees_working = selected_employees.get(position.id, [])
            employee_list = ", ".join(employees_working) if employees_working else f"{num_staff} staff"
            
            calculation_breakdown.append({
                "position": position.position_name,
                "calculation": f"{position.percentage}% of ${base_amount:.2f} ({position.calculation_base.replace('_', ' ').title()})",
                "total": position_total,
                "staff_count": num_staff,
                "per_person": per_person,
                "employees": employee_list
            })
            
            total_tipout += position_total
        
        # Validate that at least one position has staff
        if total_tipout == 0:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>No Staff Assigned</h3>
                        <p>You must assign at least one staff member to a position to calculate tipouts.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/calculate_tipout" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <input type="hidden" name="server_name" value="{server_name}">
                            <input type="hidden" name="date" value="{date}">
                            <button type="submit" class="btn btn-primary">Try Again</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        server_keep = server_tips - total_tipout
        
        # Handle existing tipout (update or create new)
        existing_tipout = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.server_name == server_name,
            Tipout.date == date
        ).first()
        
        if existing_tipout:
            existing_tipout.start_time = start_time
            existing_tipout.end_time = end_time
            existing_tipout.total_alc_sales = alc_sales
            existing_tipout.total_food_sales = food_sales_shift
            existing_tipout.time_based_food_sales = food_sales_shift
            existing_tipout.server_tips = server_tips
            existing_tipout.tipout_details = json.dumps(tipout_details)
            existing_tipout.num_assistants = sum(details["num_staff"] for details in tipout_details.values())
            existing_tipout.toast_sync = False
            action_text = "Updated"
        else:
            tipout = Tipout(
                restaurant_id=restaurant.id,
                server_name=server_name,
                date=date,
                start_time=start_time,
                end_time=end_time,
                num_assistants=sum(details["num_staff"] for details in tipout_details.values()),
                total_alc_sales=alc_sales,
                total_food_sales=food_sales_shift,
                time_based_food_sales=food_sales_shift,
                server_tips=server_tips,
                tipout_details=json.dumps(tipout_details),
                toast_sync=False
            )
            db.add(tipout)
            action_text = "Created"
        
        db.commit()
        
        # Generate enhanced breakdown HTML with detailed calculations
        breakdown_items = []
        for calc in calculation_breakdown:
            breakdown_items.append(f"""
            <div class="tipout-item">
                <h4>{calc['position']}</h4>
                <div style="background: white; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>Calculation:</strong> {calc['calculation']}</p>
                    <p><strong>Employees Working:</strong> {calc['employees']}</p>
                    <p><strong>Total Amount:</strong> <span class="highlight">${calc['total']:.2f}</span></p>
                    <p><strong>Per Person:</strong> <span class="highlight">${calc['per_person']:.2f}</span></p>
                </div>
            </div>
            """)
        breakdown_html = "".join(breakdown_items)
        
        # Calculate efficiency metrics
        total_staff = sum(details["num_staff"] for details in tipout_details.values())
        tipout_percentage = (total_tipout / server_tips * 100) if server_tips > 0 else 0
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="success">
                    <h2>Tipout {action_text} Successfully!</h2>
                </div>
                
                <div class="header">
                    <h3>Enhanced Tip Distribution for {server_name}</h3>
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
                        <div class="summary-value">{total_staff}</div>
                        <div class="summary-label">Total Staff</div>
                    </div>
                </div>
                
                <h3>Detailed Tipout Breakdown</h3>
                {breakdown_html}
                
                <div style="background: var(--success); color: white; padding: 20px; border-radius: 10px; text-align: center; margin: 20px 0;">
                    <h3>Final Summary</h3>
                    <p><strong>Total Tipout:</strong> ${total_tipout:.2f} ({tipout_percentage:.1f}% of server tips)</p>
                    <p><strong>Server Keeps:</strong> ${server_keep:.2f}</p>
                    <p><strong>Staff Receiving Tips:</strong> {total_staff} people across {len(calculation_breakdown)} positions</p>
                </div>
                
                <div style="text-align: center;">
                    <form action="/daily_status" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">Back to Daily Status</button>
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
        print(f"Enhanced process tipout error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Processing Tipout</h3>
                    <p>{str(e)}</p>
                    <p><strong>Debug Info:</strong> Check that all staff numbers are valid integers.</p>
                </div>
                <div style="text-align: center;">
                    <form action="/calculate_tipout" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                        <input type="hidden" name="server_name" value="{server_name}">
                        <input type="hidden" name="date" value="{date}">
                        <button type="submit" class="btn btn-primary">Try Again</button>
                    </form>
                </div>
            </div>
        </div>
        """
@app.post("/totals", response_class=HTMLResponse)
def show_totals(restaurant_id: int = Form(...), date: str = Form(...), db: Session = Depends(get_db)):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
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
                        <h2>No Records Found</h2>
                        <p><strong>{restaurant.name}</strong> - {date}</p>
                    </div>
                    
                    <div style="text-align: center; padding: 40px;">
                        <h3>No tipout records found for this date</h3>
                        <p>Try a different date or calculate some tipouts first.</p>
                    </div>
                    
                    <div style="text-align: center;">
                        <form action="/menu" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-primary">Back to Dashboard</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        total_by_position = {}
        total_server_tips = sum(tipout.server_tips for tipout in tipouts)
        total_sales = sum(tipout.total_alc_sales + tipout.time_based_food_sales for tipout in tipouts)
        grand_total_tipout = 0.0
        
        for tipout in tipouts:
            try:
                details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
                for position_name, position_data in details.items():
                    amount = position_data.get('amount', 0.0)
                    if position_name not in total_by_position:
                        total_by_position[position_name] = 0.0
                    total_by_position[position_name] += amount
                    grand_total_tipout += amount
            except:
                pass
        
        tipout_details = []
        for tipout in tipouts:
            toast_badge = "TOAST" if tipout.toast_sync else "MANUAL"
            try:
                details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
                detail_text = ", ".join([f"{name}: ${data.get('amount', 0):.2f}" for name, data in details.items()])
            except:
                detail_text = "Details unavailable"
            
            tipout_details.append(f"""
            <div class="tipout-item">
                <button class="delete-btn" onclick="confirmDelete({tipout.id}, {restaurant.id})" title="Delete tipout">×</button>
                <h4>{toast_badge} {tipout.server_name}</h4>
                <p><strong>Shift:</strong> {tipout.start_time} - {tipout.end_time}</p>
                <p><strong>Tipouts:</strong> {detail_text}</p>
                <p><strong>Server Tips:</strong> ${tipout.server_tips:.2f}</p>
            </div>
            """)
        
        details_html = "".join(tipout_details)
        
        position_summary = []
        for position_name, total_amount in total_by_position.items():
            position_summary.append(f"""
            <div class="summary-item">
                <div class="summary-value">${total_amount:.2f}</div>
                <div class="summary-label">{position_name}</div>
            </div>
            """)
        
        position_summary_html = "".join(position_summary)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Daily Totals
                </div>
                
                <div class="header">
                    <h2>Daily Totals Summary</h2>
                    <p><strong>{restaurant.name}</strong> - {date}</p>
                </div>
                
                <div class="summary-grid">
                    {position_summary_html}
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
                    <h3>Grand Total Tipout: ${grand_total_tipout:.2f}</h3>
                </div>
                
                <h3>Individual Breakdowns</h3>
                <p style="color: var(--secondary); font-style: italic;">Click the × to delete a tipout entry</p>
                {details_html}
                
                <p style="text-align: center; color: var(--secondary); font-size: 0.9em; margin-top: 20px;">
                    TOAST = Toast synced data | MANUAL = Manual entry
                </p>
                
                <div style="text-align: center;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">Back to Dashboard</button>
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
                    <h3>Error Loading Totals</h3>
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
        
        return await enhanced_daily_status(restaurant_id, db)
    except Exception as e:
        print(f"Delete tipout error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Deleting Tipout</h3>
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
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        tip_positions = db.query(TipPosition).filter(TipPosition.restaurant_id == restaurant_id, TipPosition.is_active == True).all()
        
        server_names = json.loads(restaurant.server_names)
        server_names_str = ", ".join(server_names)
        toast_status = "Connected" if restaurant.toast_client_id else "Not Connected"
        
        position_items = []
        for position in tip_positions:
            base_display = {
                "food_sales": "Food Sales",
                "alcohol_sales": "Alcohol Sales",
                "total_sales": "Total Sales"
            }.get(position.calculation_base, position.calculation_base)
            
            # Get employee names for this position
            try:
                employee_names = json.loads(position.employee_names) if position.employee_names else []
            except:
                employee_names = []
            
            # Create employee tags
            employee_tags = []
            for emp_name in employee_names:
                employee_tags.append(f"""
                <span class="employee-tag">
                    {emp_name}
                    <button class="remove-employee" onclick="removeEmployee({position.id}, '{emp_name}', {restaurant.id})" title="Remove employee">×</button>
                </span>
                """)
            
            employee_html = "".join(employee_tags) if employee_tags else "<p style='color: var(--secondary); margin: 5px 0;'>No employees assigned</p>"
            
            position_items.append(f"""
            <div class="position-item">
                <button class="delete-btn" onclick="confirmDeletePosition({position.id}, {restaurant.id})" title="Delete position">×</button>
                <h4>{position.position_name}</h4>
                <div class="position-info">
                    <span>Percentage: {position.percentage}%</span>
                    <span>Based on: {base_display}</span>
                    <span>Employees: {len(employee_names)}</span>
                </div>
                
                <div class="employee-list">
                    <strong>Employees:</strong>
                    {employee_html}
                    
                    <div style="margin-top: 10px;">
                        <button id="employeeBtn_{position.id}" class="btn btn-success" onclick="toggleEmployeeForm({position.id})">+ Add Employee</button>
                    </div>
                    
                    <div id="employeeForm_{position.id}" style="display: none; margin-top: 15px; padding: 15px; background: var(--light); border-radius: 8px;">
                        <form action="/add_employee" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="position_id" value="{position.id}">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Employee Name:</label>
                                    <input type="text" name="employee_name" placeholder="e.g., John Doe" required>
                                </div>
                                <div class="form-group">
                                    <button type="submit" class="btn btn-primary">Add</button>
                                </div>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
            """)
        
        positions_html = "".join(position_items) if position_items else "<p style='text-align: center; color: var(--secondary);'>No tip positions configured. Add your first position below.</p>"
        # Generate employee checkboxes for tip position assignment
        try:
            tip_recipients = db.query(Employee).filter(
                Employee.restaurant_id == restaurant_id,
                Employee.is_tip_recipient == True,
                Employee.is_active == True
            ).order_by(Employee.first_name, Employee.last_name).all()
            
            if not tip_recipients:
                employee_checkboxes_html = """
                <div style="text-align: center; color: var(--secondary); padding: 20px;">
                    <p>No tip recipients found.</p>
                    <p><strong>To assign employees:</strong></p>
                    <ol style="text-align: left; margin: 10px 0;">
                        <li>Go to Employee Management</li>
                        <li>Edit existing employees or add new ones</li>
                        <li>Check "Tip Recipient" role</li>
                    </ol>
                    <p>You can add employees to this position later if needed.</p>
                </div>
                """
            else:
                checkboxes = []
                for emp in tip_recipients:
                    full_name = f"{emp.first_name} {emp.last_name}".strip()
                    position_title = f" ({emp.position_title})" if emp.position_title else ""
                    
                    checkboxes.append(f"""
                    <div class="employee-checkbox">
                        <input type="checkbox" name="selected_employees" value="{emp.id}" id="emp_select_{emp.id}">
                        <label for="emp_select_{emp.id}">{full_name}{position_title}</label>
                    </div>
                    """)
                
                employee_checkboxes_html = "".join(checkboxes)
                
        except Exception as e:
            employee_checkboxes_html = f"<p style='color: var(--danger);'>Error loading employees: {str(e)}</p>"
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Settings
                </div>
                
                <div class="header">
                    <h2>Restaurant Settings</h2>
                    <p><strong>{restaurant.name}</strong></p>
                </div>
                
                <div class="toast-status" style="background: {'var(--success)' if restaurant.toast_client_id else 'var(--warning)'};">
                    Toast Status: {toast_status}
                </div>
                
                <h3>Tip Positions Management</h3>
                <p style="color: var(--secondary); margin-bottom: 20px;">
                    Configure which positions receive tips and how much. These will be used for all tipout calculations.
                </p>
                
                {positions_html}
                
                <div style="text-align: center; margin: 20px 0;">
                    <button id="addPositionBtn" class="btn btn-success" onclick="toggleAddPositionForm()">+ Add New Position</button>
                </div>
                
                <div id="addPositionForm" class="add-position-form" style="display: none;">
                    <h4>Add New Tip Position</h4>
                    <form action="/add_position" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Position Name:</label>
                                <input type="text" name="position_name" placeholder="e.g., Food Runner, Host, Kitchen" required>
                            </div>
                            <div class="form-group">
                                <label>Percentage (%):</label>
                                <input type="number" name="percentage" step="0.01" min="0" max="100" placeholder="0.75" required>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Calculate Based On:</label>
                            <select name="calculation_base" required>
                                <option value="food_sales">Food Sales</option>
                                <option value="alcohol_sales">Alcohol Sales</option>
                                <option value="total_sales">Total Sales (Food + Alcohol)</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label>Assign Employees to this Position:</label>
                            <div style="background: white; padding: 15px; border-radius: 8px; margin: 10px 0; border: 1px solid #ddd; max-height: 200px; overflow-y: auto;">
                                {employee_checkboxes_html}
                            </div>
                            <small style="color: var(--secondary); display: block; margin-top: 5px;">
                                Select employees who will receive tips from this position. Only employees marked as "Tip Recipients" are shown.
                            </small>
                        </div>
                        
                        <div style="text-align: center;">
                            <button type="submit" class="btn btn-primary">Add Position</button>
                        </div>
                    </form>
                </div>
                
                <h3>Toast POS Integration</h3>
                <form action="/update_settings" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    
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
                    
                    
                    <div style="text-align: center; margin-top: 30px;">
                        <button type="submit" class="btn btn-success">Save Toast Settings</button>
                        <form action="/menu" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-light">Cancel</button>
                        </form>
                    </div>
                    </form>

                    <div style="text-align: center; margin: 30px 0; padding: 20px; background: var(--light); border-radius: 10px;">
                        <h3>Employee Management</h3>
                        <p style="color: var(--secondary); margin-bottom: 15px;">Manage your restaurant staff and employee records</p>
                        <form action="/employee_management" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-primary">Manage Employees</button>
                        </form>
                    </div>
                </form>
                
                <div style="margin-top: 30px; padding: 20px; background: var(--light); border-radius: 10px;">
                    <h4>Tips for Position Setup:</h4>
                    <ul style="text-align: left; color: var(--secondary);">
                        <li><strong>Position Names:</strong> Use clear, recognizable names (Bartender, Food Runner, etc.)</li>
                        <li><strong>Percentages:</strong> Enter as decimal (0.75 for 0.75% of sales)</li>
                        <li><strong>Calculation Base:</strong> Choose what sales type to calculate tips from</li>
                        <li><strong>Multiple Positions:</strong> You can have as many positions as needed</li>
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
                    <h3>Error Loading Settings</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/add_position", response_class=HTMLResponse)
def add_position(
    restaurant_id: int = Form(...),
    position_name: str = Form(...),
    percentage: float = Form(...),
    calculation_base: str = Form(...),
    selected_employees: list = Form([]),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        existing_position = db.query(TipPosition).filter(
            TipPosition.restaurant_id == restaurant_id,
            TipPosition.position_name.ilike(position_name.strip()),
            TipPosition.is_active == True
        ).first()
        
        if existing_position:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>Position Already Exists</h3>
                        <p>A position named "{position_name}" already exists for this restaurant.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/settings" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Settings</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        # Get selected employee names
        employee_list = []
        if selected_employees:
            try:
                # Handle both single values and lists
                if isinstance(selected_employees, list):
                    employee_ids = [int(emp_id) for emp_id in selected_employees if str(emp_id).isdigit()]
                else:
                    employee_ids = [int(selected_employees)] if str(selected_employees).isdigit() else []
                
                if employee_ids:
                    selected_emp_objects = db.query(Employee).filter(
                        Employee.id.in_(employee_ids),
                        Employee.restaurant_id == restaurant_id,
                        Employee.is_active == True
                    ).all()
                    
                    for emp in selected_emp_objects:
                        full_name = f"{emp.first_name} {emp.last_name}".strip()
                        employee_list.append(full_name)
            except (ValueError, TypeError) as e:
                print(f"Error processing selected employees: {e}")
        
        new_position = TipPosition(
            restaurant_id=restaurant_id,
            position_name=position_name.strip(),
            percentage=percentage,
            calculation_base=calculation_base,
            employee_names=json.dumps(employee_list)
        )
        
        db.add(new_position)
        db.commit()
        
        return restaurant_settings(restaurant_id, db)
        
    except Exception as e:
        print(f"Add position error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Adding Position</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
        
        new_position = TipPosition(
            restaurant_id=restaurant_id,
            position_name=position_name.strip(),
            percentage=percentage,
            calculation_base=calculation_base,
            employee_names=json.dumps(employee_list)
        )
        
        db.add(new_position)
        db.commit()
        
        return restaurant_settings(restaurant_id, db)
        
    except Exception as e:
        print(f"Add position error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Adding Position</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
@app.post("/delete_position", response_class=HTMLResponse)
def delete_position(position_id: int = Form(...), restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        position = db.query(TipPosition).filter(TipPosition.id == position_id).first()
        if position:
            position.is_active = False
            db.commit()
        
        return restaurant_settings(restaurant_id, db)
        
    except Exception as e:
        print(f"Delete position error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Deleting Position</h3>
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
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Update Toast settings
        restaurant.toast_client_id = toast_client_id.strip() if toast_client_id.strip() else None
        restaurant.toast_client_secret = toast_client_secret.strip() if toast_client_secret.strip() else None
        restaurant.toast_restaurant_guid = toast_restaurant_guid.strip() if toast_restaurant_guid.strip() else None
        restaurant.toast_management_group_guid = toast_management_group_guid.strip() if toast_management_group_guid.strip() else None
        
        db.commit()
        
        tip_positions_count = db.query(TipPosition).filter(TipPosition.restaurant_id == restaurant_id, TipPosition.is_active == True).count()
        employees_count = db.query(Employee).filter(Employee.restaurant_id == restaurant_id, Employee.is_active == True).count()
        
        toast_status = ""
        if restaurant.toast_client_id:
            toast_status = '<div class="toast-status">Toast POS Integration Updated & Active</div>'
        else:
            toast_status = '<div class="manual-entry">Manual Entry Mode - Toast Integration Disabled</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="success">
                    <h2>Toast Settings Updated Successfully!</h2>
                </div>
                {toast_status}
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{tip_positions_count}</div>
                        <div class="summary-label">Active Positions</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{employees_count}</div>
                        <div class="summary-label">Active Employees</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{'Yes' if restaurant.toast_client_id else 'No'}</div>
                        <div class="summary-label">Toast Connected</div>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">Back to Dashboard</button>
                    </form>
                    
                    <form action="/settings" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Settings</button>
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
                    <h3>Error Updating Settings</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
@app.post("/scheduling", response_class=HTMLResponse)
def scheduling_dashboard(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Main scheduling interface"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get current week dates
        from datetime import date, timedelta
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        week_dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        week_display = [(start_of_week + timedelta(days=i)).strftime("%a %m/%d") for i in range(7)]
        
        # Get employees
        employees = db.query(Employee).filter(
            Employee.restaurant_id == restaurant_id,
            Employee.is_active == True
        ).order_by(Employee.first_name, Employee.last_name).all()
        
        # Get this week's schedules
        schedules = db.query(Schedule).filter(
            Schedule.restaurant_id == restaurant_id,
            Schedule.schedule_date.in_(week_dates)
        ).all()
        
        # Organize schedules by date and employee
        schedule_grid = {}
        for date_str in week_dates:
            schedule_grid[date_str] = {}
            for emp in employees:
                schedule_grid[date_str][emp.id] = None
        
        for schedule in schedules:
            if schedule.schedule_date in schedule_grid and schedule.employee_id in schedule_grid[schedule.schedule_date]:
                schedule_grid[schedule.schedule_date][schedule.employee_id] = schedule
        
        # Generate schedule grid HTML
        schedule_html = generate_schedule_grid_html(employees, week_dates, week_display, schedule_grid, restaurant_id)
        
        return STYLE + f"""
        <div class="container">
            <div class="card" style="max-width: 1200px;">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Scheduling
                </div>
                
                <div class="header">
                    <h2>Employee Scheduling</h2>
                    <p><strong>{restaurant.name}</strong> | Week of {start_of_week.strftime('%B %d, %Y')}</p>
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{len(employees)}</div>
                        <div class="summary-label">Active Employees</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(schedules)}</div>
                        <div class="summary-label">Shifts This Week</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([s for s in schedules if s.status == 'scheduled'])}</div>
                        <div class="summary-label">Pending</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([s for s in schedules if s.status == 'confirmed'])}</div>
                        <div class="summary-label">Confirmed</div>
                    </div>
                </div>
                
                <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <div>
                        <form action="/scheduling_week" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="week_start" value="{(start_of_week - timedelta(days=7)).strftime('%Y-%m-%d')}">
                            <button type="submit" class="btn btn-secondary">← Previous Week</button>
                        </form>
                        
                        <button class="btn btn-primary" disabled>Current Week</button>
                        
                        <form action="/scheduling_week" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="week_start" value="{(start_of_week + timedelta(days=7)).strftime('%Y-%m-%d')}">
                            <button type="submit" class="btn btn-secondary">Next Week →</button>
                        </form>
                    </div>
                    
                    <div>
                        <button class="btn btn-success" onclick="toggleQuickSchedule()">Quick Add Shift</button>
                        <form action="/bulk_schedule" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-warning">Bulk Schedule</button>
                        </form>
                    </div>
                </div>
                    
                    {schedule_html}
                </div>
                
                <div id="quickScheduleForm" style="display: none; background: white; padding: 20px; border-radius: 10px; margin: 20px 0; border: 2px solid var(--primary);">
                    <h4>Quick Add Shift</h4>
                    
                    <div style="background: var(--light); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                        <h5>Quick Templates:</h5>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <button type="button" class="btn btn-light" onclick="applyShiftTemplate('morning')" style="padding: 8px 12px; font-size: 0.9em;">
                                Morning (9-5)
                            </button>
                            <button type="button" class="btn btn-light" onclick="applyShiftTemplate('evening')" style="padding: 8px 12px; font-size: 0.9em;">
                                Evening (5-11)
                            </button>
                            <button type="button" class="btn btn-light" onclick="applyShiftTemplate('opening')" style="padding: 8px 12px; font-size: 0.9em;">
                                Opening (8-4)
                            </button>
                            <button type="button" class="btn btn-light" onclick="applyShiftTemplate('closing')" style="padding: 8px 12px; font-size: 0.9em;">
                                Closing (4-12)
                            </button>
                            <button type="button" class="btn btn-light" onclick="applyShiftTemplate('double')" style="padding: 8px 12px; font-size: 0.9em;">
                                Double (9-9)
                            </button>
                        </div>
                    </div>
                    
                    <form action="/add_shift" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Employee:</label>
                                <select name="employee_id" required>
                                    <option value="">Select Employee</option>
                                    {generate_employee_options(employees)}
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Date:</label>
                                <input type="date" name="schedule_date" value="{today}" required>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Start Time:</label>
                                <input type="time" name="start_time" value="09:00" required>
                            </div>
                            <div class="form-group">
                                <label>End Time:</label>
                                <input type="time" name="end_time" value="17:00" required>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Position:</label>
                                <input type="text" name="position" placeholder="e.g., Server, Host, Kitchen" value="Day Shift">
                            </div>
                            <div class="form-group">
                                <label>Notes:</label>
                                <input type="text" name="notes" placeholder="Optional notes">
                            </div>
                        </div>
                        
                        <div style="text-align: center;">
                            <button type="submit" class="btn btn-success">Add Shift</button>
                            <button type="button" class="btn btn-light" onclick="toggleQuickSchedule()">Cancel</button>
                        </div>
                    </form>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Dashboard</button>
                    </form>
                </div>
            </div>
        </div>
        
        <script>
        function toggleQuickSchedule() {{
            const form = document.getElementById('quickScheduleForm');
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
        }}

        function quickAddShift(employeeId, date) {{
            // Pre-fill the quick form
            document.querySelector('select[name="employee_id"]').value = employeeId;
            document.querySelector('input[name="schedule_date"]').value = date;
            
            // Show the form
            const form = document.getElementById('quickScheduleForm');
            form.style.display = 'block';
            form.scrollIntoView({{ behavior: 'smooth' }});
        }}

        function applyShiftTemplate(templateName) {{
            const templates = {{
                'morning': {{ start: '09:00', end: '17:00', position: 'Day Shift' }},
                'evening': {{ start: '17:00', end: '23:00', position: 'Evening Shift' }},
                'opening': {{ start: '08:00', end: '16:00', position: 'Opening' }},
                'closing': {{ start: '16:00', end: '00:00', position: 'Closing' }},
                'double': {{ start: '09:00', end: '21:00', position: 'Double Shift' }}
            }};
            
            const template = templates[templateName];
            if (template) {{
                document.querySelector('input[name="start_time"]').value = template.start;
                document.querySelector('input[name="end_time"]').value = template.end;
                document.querySelector('input[name="position"]').value = template.position;
            }}
        }}
        
        function editShift(scheduleId) {{
            alert('Edit shift functionality coming next!');
        }}
        
        function deleteShift(scheduleId, restaurantId) {{
            if (confirm('Delete this shift?')) {{
                fetch('/delete_shift', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                    body: `schedule_id=${{scheduleId}}&restaurant_id=${{restaurantId}}`
                }})
                .then(response => response.text())
                .then(html => {{ document.body.innerHTML = html; }});
            }}
        }}
        
        function viewNextWeek(restaurantId) {{
            // This function is now handled by the form buttons above
            console.log('Week navigation handled by form buttons');
        }}
        </script>
        """
        
    except Exception as e:
        print(f"Scheduling dashboard error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Scheduling</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
def generate_schedule_grid_html(employees, week_dates, week_display, schedule_grid, restaurant_id):
    """Generate the weekly schedule grid"""
    
    # Header row with days
    header_cells = ["<th style='padding: 10px; background: var(--secondary); color: white;'>Employee</th>"]
    for day_display in week_display:
        header_cells.append(f"<th style='padding: 10px; background: var(--secondary); color: white; text-align: center;'>{day_display}</th>")
    
    header_row = f"<tr>{''.join(header_cells)}</tr>"
    
    # Employee rows
    employee_rows = []
    for emp in employees:
        full_name = f"{emp.first_name} {emp.last_name}".strip()
        
        cells = [f"<td style='padding: 10px; background: var(--light); font-weight: bold;'>{full_name}</td>"]
        
        for date_str in week_dates:
            schedule = schedule_grid[date_str][emp.id]
            
            if schedule:
                status_color = {
                    'scheduled': 'var(--warning)',
                    'confirmed': 'var(--success)', 
                    'completed': 'var(--primary)',
                    'no_show': 'var(--danger)'
                }.get(schedule.status, 'var(--secondary)')
                
                cell_content = f"""
                <div style="background: {status_color}; color: white; padding: 8px; border-radius: 5px; font-size: 0.85em; cursor: pointer;" 
                     onclick="editShift({schedule.id})" title="Click to edit">
                    <div><strong>{schedule.start_time} - {schedule.end_time}</strong></div>
                    <div>{schedule.position or 'Staff'}</div>
                    <button onclick="event.stopPropagation(); deleteShift({schedule.id}, {restaurant_id})" 
                            style="background: none; border: none; color: white; float: right; font-size: 0.8em;">×</button>
                </div>
                """
            else:
                cell_content = f"""
                <div style="height: 50px; display: flex; align-items: center; justify-content: center;">
                    <button onclick="quickAddShift({emp.id}, '{date_str}')" 
                            style="background: var(--light); border: 1px dashed var(--secondary); padding: 5px 10px; border-radius: 5px; font-size: 0.8em;">
                        + Add
                    </button>
                </div>
                """
            
            cells.append(f"<td style='padding: 5px; text-align: center; vertical-align: top;'>{cell_content}</td>")
        
        employee_rows.append(f"<tr>{''.join(cells)}</tr>")
    
    return f"""
    <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden;">
            <thead>{header_row}</thead>
            <tbody>{''.join(employee_rows)}</tbody>
        </table>
    </div>
    """

def generate_employee_options(employees):
    """Generate option tags for employee select"""
    options = []
    for emp in employees:
        full_name = f"{emp.first_name} {emp.last_name}".strip()
        options.append(f'<option value="{emp.id}">{full_name}</option>')
    return "".join(options)

@app.post("/add_shift", response_class=HTMLResponse)
def add_shift(
    restaurant_id: int = Form(...),
    employee_id: int = Form(...),
    schedule_date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    position: Optional[str] = Form(""),
    notes: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    try:
        # Check for conflicts
        existing_shift = db.query(Schedule).filter(
            Schedule.restaurant_id == restaurant_id,
            Schedule.employee_id == employee_id,
            Schedule.schedule_date == schedule_date
        ).first()
        
        if existing_shift:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>Shift Conflict</h3>
                        <p>This employee already has a shift scheduled for {schedule_date}.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/scheduling" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Schedule</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        new_schedule = Schedule(
            restaurant_id=restaurant_id,
            employee_id=employee_id,
            schedule_date=schedule_date,
            start_time=start_time,
            end_time=end_time,
            position=position.strip() if position.strip() else None,
            notes=notes.strip() if notes.strip() else None
        )
        
        db.add(new_schedule)
        db.commit()
        
        return scheduling_dashboard(restaurant_id, db)
        
    except Exception as e:
        print(f"Add shift error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Adding Shift</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/delete_shift", response_class=HTMLResponse)
def delete_shift(
    schedule_id: int = Form(...),
    restaurant_id: int = Form(...),
    db: Session = Depends(get_db)
):
    try:
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
        if schedule:
            db.delete(schedule)
            db.commit()
        
        return scheduling_dashboard(restaurant_id, db)
        
    except Exception as e:
        print(f"Delete shift error: {e}")
        return scheduling_dashboard(restaurant_id, db)
@app.post("/menu", response_class=HTMLResponse)
def menu(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    return restaurant_dashboard(restaurant_id, db)

@app.get("/menu", response_class=HTMLResponse)
def menu_get(restaurant_id: int, db: Session = Depends(get_db)):
    return restaurant_dashboard(restaurant_id, db)
# Add these new imports to the existing main.py file
from datetime import datetime, timedelta, date
from collections import defaultdict
import calendar

# Add these new routes after the existing routes but before the debug route
@app.post("/bulk_schedule", response_class=HTMLResponse)
async def bulk_schedule_form(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Bulk scheduling interface for multiple employees/days"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        employees = db.query(Employee).filter(
            Employee.restaurant_id == restaurant_id,
            Employee.is_active == True
        ).order_by(Employee.first_name, Employee.last_name).all()
        
        from datetime import date, timedelta
        today = date.today()
        
        # Generate next 14 days
        dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]
        date_displays = [(today + timedelta(days=i)).strftime("%a %m/%d") for i in range(14)]
        
        employee_checkboxes = []
        for emp in employees:
            full_name = f"{emp.first_name} {emp.last_name}".strip()
            employee_checkboxes.append(f"""
            <div class="employee-checkbox">
                <input type="checkbox" name="selected_employees" value="{emp.id}" id="bulk_emp_{emp.id}">
                <label for="bulk_emp_{emp.id}">{full_name}</label>
            </div>
            """)
        
        date_checkboxes = []
        for i, (date_val, date_display) in enumerate(zip(dates, date_displays)):
            date_checkboxes.append(f"""
            <div class="employee-checkbox">
                <input type="checkbox" name="selected_dates" value="{date_val}" id="bulk_date_{i}">
                <label for="bulk_date_{i}">{date_display}</label>
            </div>
            """)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → <a href="/scheduling?restaurant_id={restaurant.id}">Scheduling</a> → Bulk Schedule
                </div>
                
                <div class="header">
                    <h2>Bulk Scheduling</h2>
                    <p><strong>{restaurant.name}</strong> | Schedule multiple employees across multiple days</p>
                </div>
                
                <form action="/process_bulk_schedule" method="post">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    
                    <div class="form-row">
                        <div class="form-group" style="flex: 1;">
                            <label>Select Employees:</label>
                            <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #ddd; max-height: 200px; overflow-y: auto;">
                                {"".join(employee_checkboxes)}
                            </div>
                        </div>
                        
                        <div class="form-group" style="flex: 1;">
                            <label>Select Dates:</label>
                            <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #ddd; max-height: 200px; overflow-y: auto;">
                                {"".join(date_checkboxes)}
                            </div>
                        </div>
                    </div>
                    
                    <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h4>Shift Template</h4>
                        <div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
                            <button type="button" class="btn btn-light" onclick="applyBulkTemplate('morning')">Morning (9-5)</button>
                            <button type="button" class="btn btn-light" onclick="applyBulkTemplate('evening')">Evening (5-11)</button>
                            <button type="button" class="btn btn-light" onclick="applyBulkTemplate('opening')">Opening (8-4)</button>
                            <button type="button" class="btn btn-light" onclick="applyBulkTemplate('closing')">Closing (4-12)</button>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Start Time:</label>
                                <input type="time" name="bulk_start_time" value="09:00" required>
                            </div>
                            <div class="form-group">
                                <label>End Time:</label>
                                <input type="time" name="bulk_end_time" value="17:00" required>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Position:</label>
                                <input type="text" name="bulk_position" value="Staff" required>
                            </div>
                            <div class="form-group">
                                <label>Notes:</label>
                                <input type="text" name="bulk_notes" placeholder="Optional notes">
                            </div>
                        </div>
                    </div>
                    
                    <div style="text-align: center;">
                        <button type="submit" class="btn btn-success">Create All Shifts</button>
                        <form action="/scheduling" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-light">Cancel</button>
                        </form>
                    </div>
                </form>
            </div>
        </div>
        
        <script>
        function applyBulkTemplate(templateName) {{
            const templates = {{
                'morning': {{ start: '09:00', end: '17:00', position: 'Day Shift' }},
                'evening': {{ start: '17:00', end: '23:00', position: 'Evening Shift' }},
                'opening': {{ start: '08:00', end: '16:00', position: 'Opening' }},
                'closing': {{ start: '16:00', end: '00:00', position: 'Closing' }}
            }};
            
            const template = templates[templateName];
            if (template) {{
                document.querySelector('input[name="bulk_start_time"]').value = template.start;
                document.querySelector('input[name="bulk_end_time"]').value = template.end;
                document.querySelector('input[name="bulk_position"]').value = template.position;
            }}
        }}
        </script>
        """
        
    except Exception as e:
        print(f"Bulk schedule form error: {e}")
        return STYLE + f"<div class='container'><div class='card'><div class='error'><h3>Error: {str(e)}</h3></div></div></div>"

@app.post("/process_bulk_schedule", response_class=HTMLResponse)
async def process_bulk_schedule(
    request: Request,
    restaurant_id: int = Form(...),
    bulk_start_time: str = Form(...),
    bulk_end_time: str = Form(...),
    bulk_position: str = Form(...),
    bulk_notes: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    """Process bulk schedule creation"""
    try:
        form_data = await request.form()
        selected_employees = form_data.getlist('selected_employees')
        selected_dates = form_data.getlist('selected_dates')
        
        if not selected_employees or not selected_dates:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>Missing Selections</h3>
                        <p>Please select at least one employee and one date.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/bulk_schedule" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Try Again</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        created_count = 0
        conflicts = []
        
        for emp_id in selected_employees:
            for date_str in selected_dates:
                # Check for existing shift
                existing = db.query(Schedule).filter(
                    Schedule.restaurant_id == restaurant_id,
                    Schedule.employee_id == int(emp_id),
                    Schedule.schedule_date == date_str
                ).first()
                
                if existing:
                    emp = db.query(Employee).filter(Employee.id == int(emp_id)).first()
                    emp_name = f"{emp.first_name} {emp.last_name}" if emp else f"Employee {emp_id}"
                    conflicts.append(f"{emp_name} on {date_str}")
                else:
                    new_schedule = Schedule(
                        restaurant_id=restaurant_id,
                        employee_id=int(emp_id),
                        schedule_date=date_str,
                        start_time=bulk_start_time,
                        end_time=bulk_end_time,
                        position=bulk_position.strip(),
                        notes=bulk_notes.strip() if bulk_notes.strip() else None
                    )
                    db.add(new_schedule)
                    created_count += 1
        
        db.commit()
        
        # Find the week that contains the most newly created shifts
        if created_count > 0:
            from collections import Counter
            from datetime import datetime, timedelta
            
            date_counts = Counter(selected_dates)
            most_common_date = date_counts.most_common(1)[0][0]
            
            # Parse the date and find its week
            target_date = datetime.strptime(most_common_date, "%Y-%m-%d").date()
            target_week_start = target_date - timedelta(days=target_date.weekday())
            target_week_param = target_week_start.strftime("%Y-%m-%d")
            
            conflict_text = ""
            if conflicts:
                conflict_text = f"""
                <div class="warning">
                    <h4>Conflicts Skipped ({len(conflicts)}):</h4>
                    <p>{"<br>".join(conflicts[:10])}</p>
                    {f"<p>...and {len(conflicts) - 10} more</p>" if len(conflicts) > 10 else ""}
                </div>
                """
            
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="success">
                        <h2>Bulk Scheduling Complete!</h2>
                        <p>Created {created_count} new shifts successfully.</p>
                    </div>
                    
                    {conflict_text}
                    
                    <div style="text-align: center;">
                        <form action="/scheduling_week" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <input type="hidden" name="week_start" value="{target_week_param}">
                            <button type="submit" class="btn btn-primary">View Schedule (Week of {target_week_start.strftime('%m/%d')})</button>
                        </form>
                        
                        <form action="/scheduling" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-secondary">Current Week</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        else:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h2>No Shifts Created</h2>
                        <p>All selected combinations already had existing shifts.</p>
                    </div>
                    
                    <div style="text-align: center;">
                        <form action="/scheduling" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Schedule</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
    except Exception as e:
        print(f"Process bulk schedule error: {e}")
        return STYLE + f"<div class='container'><div class='card'><div class='error'><h3>Error: {str(e)}</h3></div></div></div>"

@app.post("/scheduling_week", response_class=HTMLResponse)
def scheduling_dashboard_week(
    restaurant_id: int = Form(...), 
    week_start: str = Form(...), 
    db: Session = Depends(get_db)
):
    """Scheduling interface for a specific week"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Parse the week start date
        from datetime import datetime, timedelta
        start_of_week = datetime.strptime(week_start, "%Y-%m-%d").date()
        week_dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        week_display = [(start_of_week + timedelta(days=i)).strftime("%a %m/%d") for i in range(7)]
        
        # Get employees
        employees = db.query(Employee).filter(
            Employee.restaurant_id == restaurant_id,
            Employee.is_active == True
        ).order_by(Employee.first_name, Employee.last_name).all()
        
        # Get this week's schedules
        schedules = db.query(Schedule).filter(
            Schedule.restaurant_id == restaurant_id,
            Schedule.schedule_date.in_(week_dates)
        ).all()
        
        # Organize schedules by date and employee
        schedule_grid = {}
        for date_str in week_dates:
            schedule_grid[date_str] = {}
            for emp in employees:
                schedule_grid[date_str][emp.id] = None
        
        for schedule in schedules:
            if schedule.schedule_date in schedule_grid and schedule.employee_id in schedule_grid[schedule.schedule_date]:
                schedule_grid[schedule.schedule_date][schedule.employee_id] = schedule
        
        # Generate schedule grid HTML
        schedule_html = generate_schedule_grid_html(employees, week_dates, week_display, schedule_grid, restaurant_id)
        
        # Calculate previous and next week
        prev_week = start_of_week - timedelta(days=7)
        next_week = start_of_week + timedelta(days=7)
        today = datetime.now().date()
        
        return STYLE + f"""
        <div class="container">
            <div class="card" style="max-width: 1200px;">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Scheduling
                </div>
                
                <div class="header">
                    <h2>Employee Scheduling</h2>
                    <p><strong>{restaurant.name}</strong> | Week of {start_of_week.strftime('%B %d, %Y')}</p>
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{len(employees)}</div>
                        <div class="summary-label">Active Employees</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(schedules)}</div>
                        <div class="summary-label">Shifts This Week</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([s for s in schedules if s.status == 'scheduled'])}</div>
                        <div class="summary-label">Pending</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([s for s in schedules if s.status == 'confirmed'])}</div>
                        <div class="summary-label">Confirmed</div>
                    </div>
                </div>
                
                <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <div>
                            <form action="/scheduling_week" method="post" style="display: inline;">
                                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                                <input type="hidden" name="week_start" value="{prev_week.strftime('%Y-%m-%d')}">
                                <button type="submit" class="btn btn-secondary">← Previous Week</button>
                            </form>
                            
                            <form action="/scheduling" method="post" style="display: inline;">
                                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                                <button type="submit" class="btn {'btn-primary' if start_of_week <= today <= start_of_week + timedelta(days=6) else 'btn-light'}">Current Week</button>
                            </form>
                            
                            <form action="/scheduling_week" method="post" style="display: inline;">
                                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                                <input type="hidden" name="week_start" value="{next_week.strftime('%Y-%m-%d')}">
                                <button type="submit" class="btn btn-secondary">Next Week →</button>
                            </form>
                        </div>
                        
                        <div>
                            <form action="/bulk_schedule" method="post" style="display: inline;">
                                <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                                <button type="submit" class="btn btn-warning">Bulk Schedule</button>
                            </form>
                        </div>
                    </div>
                    
                    {schedule_html}
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Dashboard</button>
                    </form>
                </div>
            </div>
        </div>
        """
        
    except Exception as e:
        print(f"Scheduling week dashboard error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Scheduling</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
@app.post("/weekly_reports", response_class=HTMLResponse)
def weekly_reports_form(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Enhanced weekly reports interface with charts and analytics"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get current week dates for default selection
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        
        # Get recent weeks for quick selection
        weeks_data = []
        for i in range(4):  # Last 4 weeks
            week_start = start_of_week - timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            weeks_data.append({
                "start": week_start.strftime("%Y-%m-%d"),
                "end": week_end.strftime("%Y-%m-%d"),
                "label": f"Week of {week_start.strftime('%m/%d')}" if i > 0 else "This Week"
            })
        
        week_options = []
        for week in weeks_data:
            week_options.append(f"""
            <option value="{week['start']}|{week['end']}">{week['label']}</option>
            """)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Weekly Reports
                </div>
                
                <div class="header">
                    <h2>Weekly Reports & Analytics</h2>
                    <p><strong>{restaurant.name}</strong></p>
                </div>
                
                <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Generate Advanced Report</h3>
                    <form action="/generate_advanced_report" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Report Period:</label>
                                <select name="week_selection" onchange="toggleCustomDates(this)" required>
                                    {"".join(week_options)}
                                    <option value="custom">Custom Date Range</option>
                                </select>
                            </div>
                        </div>
                        
                        <div class="form-row" id="customDates" style="display: none;">
                            <div class="form-group">
                                <label>Start Date:</label>
                                <input type="date" name="custom_start" value="{start_of_week}">
                            </div>
                            <div class="form-group">
                                <label>End Date:</label>
                                <input type="date" name="custom_end" value="{end_of_week}">
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Report Features:</label>
                            <div style="margin-top: 10px;">
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="include_charts" value="true" checked style="margin-right: 10px;">
                                    Interactive charts and visualizations
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="include_trends" value="true" checked style="margin-right: 10px;">
                                    Trend analysis and insights
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="include_comparisons" value="true" checked style="margin-right: 10px;">
                                    Performance comparisons
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="generate_email" value="true" checked style="margin-right: 10px;">
                                    Email summary for management
                                </label>
                            </div>
                        </div>
                        
                        <div style="text-align: center;">
                            <button type="submit" class="btn btn-primary">Generate Advanced Report</button>
                        </div>
                    </form>
                </div>
                
                <div style="background: var(--primary); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Quick Reports</h3>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; margin-top: 15px;">
                        <form action="/generate_advanced_report" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="week_selection" value="{weeks_data[0]['start']}|{weeks_data[0]['end']}">
                            <input type="hidden" name="include_charts" value="true">
                            <input type="hidden" name="include_trends" value="true">
                            <input type="hidden" name="include_comparisons" value="true">
                            <button type="submit" class="btn btn-light">This Week's Analytics</button>
                        </form>
                        
                        <form action="/generate_trend_analysis" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-light">30-Day Trends</button>
                        </form>
                        
                        <form action="/generate_performance_report" method="post" style="display: inline;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <button type="submit" class="btn btn-light">Staff Performance</button>
                        </form>
                    </div>
                </div>
                
                <div style="text-align: center;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Dashboard</button>
                    </form>
                </div>
            </div>
        </div>
        
        <script>
        function toggleCustomDates(select) {{
            const customDates = document.getElementById('customDates');
            if (select.value === 'custom') {{
                customDates.style.display = 'flex';
            }} else {{
                customDates.style.display = 'none';
            }}
        }}
        </script>
        """
    except Exception as e:
        print(f"Weekly reports form error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Weekly Reports</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Weekly reports form error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Weekly Reports</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/generate_weekly_report", response_class=HTMLResponse)
def generate_weekly_report(
    restaurant_id: int = Form(...),
    report_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    include_comparison: Optional[str] = Form(None),
    generate_email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Generate the weekly report with analytics and email summary"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Parse dates
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        # Get tipouts for the selected period
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date >= start_date,
            Tipout.date <= end_date
        ).all()
        
        # Calculate comparison period if requested
        comparison_data = None
        if include_comparison == "true":
            period_length = (end_dt - start_dt).days + 1
            comp_start = start_dt - timedelta(days=period_length)
            comp_end = end_dt - timedelta(days=period_length)
            
            comparison_tipouts = db.query(Tipout).filter(
                Tipout.restaurant_id == restaurant_id,
                Tipout.date >= comp_start.strftime("%Y-%m-%d"),
                Tipout.date <= comp_end.strftime("%Y-%m-%d")
            ).all()
            
            comparison_data = calculate_period_analytics(comparison_tipouts)
        
        # Calculate analytics for main period
        analytics = calculate_period_analytics(tipouts)
        
        # Generate report HTML
        report_html = generate_report_html(
            restaurant, 
            analytics, 
            comparison_data, 
            start_dt, 
            end_dt, 
            report_type
        )
        
        # Generate email summary if requested
        email_summary = ""
        if generate_email == "true":
            email_summary = generate_email_summary(
                restaurant, 
                analytics, 
                comparison_data, 
                start_dt, 
                end_dt, 
                report_type
            )
        
        return report_html + email_summary
        
    except Exception as e:
        print(f"Generate weekly report error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Generating Report</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/generate_trend_analysis", response_class=HTMLResponse)
def generate_trend_analysis(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Generate 30-day trend analysis with advanced charts"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get last 30 days of data
        today = date.today()
        start_date = today - timedelta(days=30)
        
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date >= start_date.strftime("%Y-%m-%d"),
            Tipout.date <= today.strftime("%Y-%m-%d")
        ).all()
        
        if not tipouts:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>No Data Available</h3>
                        <p>No tipout data found for the last 30 days.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/weekly_reports" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Reports</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        # Calculate trend data
        trend_data = calculate_trend_analytics(tipouts)
        
        return generate_trend_report_html(restaurant, trend_data, start_date, today)
        
    except Exception as e:
        print(f"Trend analysis error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Generating Trend Analysis</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

def calculate_trend_analytics(tipouts):
    """Calculate 30-day trend analytics"""
    daily_data = defaultdict(lambda: {"revenue": 0, "tipouts": 0, "server_tips": 0, "shifts": 0})
    weekly_data = defaultdict(lambda: {"revenue": 0, "tipouts": 0, "server_tips": 0, "shifts": 0})
    server_trends = defaultdict(lambda: defaultdict(lambda: {"tips": 0, "shifts": 0}))
    
    for tipout in tipouts:
        date_obj = datetime.strptime(tipout.date, "%Y-%m-%d").date()
        week_start = date_obj - timedelta(days=date_obj.weekday())
        week_key = week_start.strftime("%Y-%m-%d")
        
        revenue = tipout.total_alc_sales + tipout.total_food_sales
        
        # Daily aggregation
        daily_data[tipout.date]["revenue"] += revenue
        daily_data[tipout.date]["server_tips"] += tipout.server_tips
        daily_data[tipout.date]["shifts"] += 1
        
        # Weekly aggregation
        weekly_data[week_key]["revenue"] += revenue
        weekly_data[week_key]["server_tips"] += tipout.server_tips
        weekly_data[week_key]["shifts"] += 1
        
        # Server trends
        server_trends[tipout.server_name][week_key]["tips"] += tipout.server_tips
        server_trends[tipout.server_name][week_key]["shifts"] += 1
        
        # Calculate tipouts
        try:
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            shift_tipout = sum(pos_data.get('amount', 0) for pos_data in details.values())
            daily_data[tipout.date]["tipouts"] += shift_tipout
            weekly_data[week_key]["tipouts"] += shift_tipout
        except:
            pass
    
    # Calculate growth rates
    sorted_weeks = sorted(weekly_data.keys())
    growth_trends = {}
    
    if len(sorted_weeks) >= 2:
        recent_week = weekly_data[sorted_weeks[-1]]
        previous_week = weekly_data[sorted_weeks[-2]]
        
        revenue_growth = ((recent_week["revenue"] - previous_week["revenue"]) / previous_week["revenue"] * 100) if previous_week["revenue"] > 0 else 0
        tips_growth = ((recent_week["server_tips"] - previous_week["server_tips"]) / previous_week["server_tips"] * 100) if previous_week["server_tips"] > 0 else 0
        
        growth_trends = {
            "revenue_growth": revenue_growth,
            "tips_growth": tips_growth,
            "trend_direction": "up" if revenue_growth > 0 else "down"
        }
    
    return {
        "daily_data": dict(daily_data),
        "weekly_data": dict(weekly_data),
        "server_trends": dict(server_trends),
        "growth_trends": growth_trends,
        "total_days": len(daily_data),
        "total_weeks": len(weekly_data)
    }

def generate_trend_report_html(restaurant, trend_data, start_date, end_date):
    """Generate trend analysis HTML with advanced charts"""
    
    # Prepare chart data
    daily_data = trend_data["daily_data"]
    weekly_data = trend_data["weekly_data"]
    
    # Daily trend chart data
    sorted_days = sorted(daily_data.keys())
    daily_labels = [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d") for d in sorted_days]
    daily_revenue = [daily_data[d]["revenue"] for d in sorted_days]
    daily_tips = [daily_data[d]["server_tips"] for d in sorted_days]
    
    # Weekly comparison data
    sorted_weeks = sorted(weekly_data.keys())
    weekly_labels = [f"Week of {datetime.strptime(w, '%Y-%m-%d').strftime('%m/%d')}" for w in sorted_weeks]
    weekly_revenue = [weekly_data[w]["revenue"] for w in sorted_weeks]
    weekly_shifts = [weekly_data[w]["shifts"] for w in sorted_weeks]
    
    # Growth indicators
    growth = trend_data["growth_trends"]
    growth_html = ""
    if growth:
        trend_color = "var(--success)" if growth["revenue_growth"] > 0 else "var(--danger)"
        arrow = "↑" if growth["revenue_growth"] > 0 else "↓"
        
        growth_html = f"""
        <div style="background: {trend_color}; color: white; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center;">
            <h3>Trend Analysis</h3>
            <p style="font-size: 1.2em;">Revenue: {arrow} {abs(growth["revenue_growth"]):.1f}% vs last week</p>
            <p style="font-size: 1.2em;">Tips: {arrow if growth["tips_growth"] > 0 else "↓"} {abs(growth["tips_growth"]):.1f}% vs last week</p>
        </div>
        """
    
    return STYLE + f"""
    <div class="container">
        <div class="card" style="max-width: 1200px;">
            <div class="breadcrumb">
                <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → <a href="/weekly_reports?restaurant_id={restaurant.id}">Weekly Reports</a> → 30-Day Trends
            </div>
            
            <div class="header">
                <h2>30-Day Trend Analysis</h2>
                <p><strong>{restaurant.name}</strong> | {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')}</p>
            </div>
            
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="summary-value">{trend_data["total_days"]}</div>
                    <div class="summary-label">Days with Data</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{trend_data["total_weeks"]}</div>
                    <div class="summary-label">Weeks Analyzed</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${sum(daily_data[d]["revenue"] for d in daily_data):.0f}</div>
                    <div class="summary-label">Total Revenue</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{sum(daily_data[d]["shifts"] for d in daily_data)}</div>
                    <div class="summary-label">Total Shifts</div>
                </div>
            </div>
            
            {growth_html}
            
            <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
            
            <h3>Trend Visualizations</h3>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; margin: 20px 0;">
                <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                    <h4>Daily Revenue Trend (30 Days)</h4>
                    <canvas id="dailyTrendChart" width="500" height="250"></canvas>
                </div>
                
                <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                    <h4>Weekly Performance Comparison</h4>
                    <canvas id="weeklyTrendChart" width="500" height="250"></canvas>
                </div>
            </div>
            
            <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); margin: 20px 0;">
                <h4>Revenue vs Tips Correlation</h4>
                <canvas id="correlationChart" width="800" height="300"></canvas>
            </div>
            
            <script>
            // Daily Trend Chart
            const dailyTrendCtx = document.getElementById('dailyTrendChart').getContext('2d');
            new Chart(dailyTrendCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(daily_labels)},
                    datasets: [{{
                        label: 'Daily Revenue',
                        data: {json.dumps(daily_revenue)},
                        borderColor: '#43c6ac',
                        backgroundColor: 'rgba(67, 198, 172, 0.1)',
                        tension: 0.4,
                        fill: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            display: false
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            ticks: {{
                                callback: function(value) {{
                                    return '$' + value.toFixed(0);
                                }}
                            }}
                        }}
                    }}
                }}
            }});
            
            // Weekly Comparison Chart
            const weeklyTrendCtx = document.getElementById('weeklyTrendChart').getContext('2d');
            new Chart(weeklyTrendCtx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(weekly_labels)},
                    datasets: [{{
                        label: 'Weekly Revenue',
                        data: {json.dumps(weekly_revenue)},
                        backgroundColor: '#43c6ac'
                    }}, {{
                        label: 'Weekly Shifts',
                        data: {json.dumps(weekly_shifts)},
                        backgroundColor: '#2ecc71',
                        yAxisID: 'y1'
                    }}]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            position: 'left',
                            ticks: {{
                                callback: function(value) {{
                                    return '$' + value.toFixed(0);
                                }}
                            }}
                        }},
                        y1: {{
                            type: 'linear',
                            position: 'right',
                            beginAtZero: true,
                            grid: {{
                                drawOnChartArea: false
                            }}
                        }}
                    }}
                }}
            }});
            
            // Correlation Chart
            const correlationCtx = document.getElementById('correlationChart').getContext('2d');
            new Chart(correlationCtx, {{
                type: 'scatter',
                data: {{
                    datasets: [{{
                        label: 'Revenue vs Tips',
                        data: {json.dumps([{"x": daily_revenue[i], "y": daily_tips[i]} for i in range(len(daily_revenue))])},
                        backgroundColor: 'rgba(67, 198, 172, 0.6)',
                        borderColor: '#43c6ac'
                    }}]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: 'Daily Revenue ($)'
                            }}
                        }},
                        y: {{
                            title: {{
                                display: true,
                                text: 'Daily Tips ($)'
                            }}
                        }}
                    }}
                }}
            }});
            </script>
            
            <div style="text-align: center; margin-top: 30px;">
                <button onclick="window.print()" class="btn btn-secondary">Print Trends</button>
                <form action="/weekly_reports" method="post" style="display: inline;">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <button type="submit" class="btn btn-primary">Back to Reports</button>
                </form>
            </div>
        </div>
    </div>
    """
@app.post("/generate_performance_report", response_class=HTMLResponse)
def generate_performance_report(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Generate detailed staff performance report"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get last 30 days for performance analysis
        today = date.today()
        start_date = today - timedelta(days=30)
        
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date >= start_date.strftime("%Y-%m-%d")
        ).all()
        
        if not tipouts:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>No Performance Data</h3>
                        <p>No tipout data found for performance analysis.</p>
                    </div>
                </div>
            </div>
            """
        
        # Calculate performance metrics
        performance_data = calculate_staff_performance(tipouts, restaurant, db)
        
        return generate_performance_html(restaurant, performance_data, start_date, today)
        
    except Exception as e:
        print(f"Performance report error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Generating Performance Report</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

def calculate_staff_performance(tipouts, restaurant, db):
    """Calculate detailed staff performance metrics"""
    server_metrics = defaultdict(lambda: {
        "total_tips": 0, "total_revenue": 0, "shifts": 0, "avg_shift_length": 0,
        "best_day": None, "best_day_tips": 0, "consistency_score": 0, "daily_tips": []
    })
    
    tip_recipient_metrics = defaultdict(lambda: {
        "total_received": 0, "shifts_worked": 0, "avg_per_shift": 0,
        "position": "", "sources": set()
    })
    
    # Get all tip positions to understand structure
    tip_positions = db.query(TipPosition).filter(
        TipPosition.restaurant_id == restaurant.id,
        TipPosition.is_active == True
    ).all()
    
    position_employees = {}
    for position in tip_positions:
        try:
            employees = json.loads(position.employee_names) if position.employee_names else []
            for emp in employees:
                position_employees[emp] = position.position_name
        except:
            pass
    
    for tipout in tipouts:
        # Server metrics
        revenue = tipout.total_alc_sales + tipout.total_food_sales
        server_metrics[tipout.server_name]["total_tips"] += tipout.server_tips
        server_metrics[tipout.server_name]["total_revenue"] += revenue
        server_metrics[tipout.server_name]["shifts"] += 1
        server_metrics[tipout.server_name]["daily_tips"].append(tipout.server_tips)
        
        # Track best day
        if tipout.server_tips > server_metrics[tipout.server_name]["best_day_tips"]:
            server_metrics[tipout.server_name]["best_day"] = tipout.date
            server_metrics[tipout.server_name]["best_day_tips"] = tipout.server_tips
        
        # Calculate shift length
        try:
            start_time = datetime.strptime(tipout.start_time, "%H:%M")
            end_time = datetime.strptime(tipout.end_time, "%H:%M")
            hours = (end_time - start_time).seconds / 3600
            if hours <= 0:
                hours += 24
            server_metrics[tipout.server_name]["avg_shift_length"] += hours
        except:
            pass
        
        # Tip recipient metrics
        try:
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            for position_name, position_data in details.items():
                employees_working = position_data.get('employees', [])
                per_person = position_data.get('per_person', 0)
                
                for emp_name in employees_working:
                    tip_recipient_metrics[emp_name]["total_received"] += per_person
                    tip_recipient_metrics[emp_name]["shifts_worked"] += 1
                    tip_recipient_metrics[emp_name]["position"] = position_name
                    tip_recipient_metrics[emp_name]["sources"].add(tipout.server_name)
        except:
            pass
    
    # Calculate final metrics
    for server_name, metrics in server_metrics.items():
        if metrics["shifts"] > 0:
            metrics["avg_tips_per_shift"] = metrics["total_tips"] / metrics["shifts"]
            metrics["avg_revenue_per_shift"] = metrics["total_revenue"] / metrics["shifts"]
            metrics["avg_shift_length"] = metrics["avg_shift_length"] / metrics["shifts"]
            metrics["efficiency"] = (metrics["total_tips"] / metrics["total_revenue"] * 100) if metrics["total_revenue"] > 0 else 0
            
            # Consistency score (lower standard deviation = higher consistency)
            if len(metrics["daily_tips"]) > 1:
                import statistics
                std_dev = statistics.stdev(metrics["daily_tips"])
                avg_tips = metrics["avg_tips_per_shift"]
                metrics["consistency_score"] = max(0, 100 - (std_dev / avg_tips * 100)) if avg_tips > 0 else 0
    
    for emp_name, metrics in tip_recipient_metrics.items():
        if metrics["shifts_worked"] > 0:
            metrics["avg_per_shift"] = metrics["total_received"] / metrics["shifts_worked"]
    
    return {
        "servers": dict(server_metrics),
        "tip_recipients": dict(tip_recipient_metrics),
        "position_mapping": position_employees
    }

def generate_performance_html(restaurant, performance_data, start_date, end_date):
    """Generate staff performance report HTML"""
    
    # Server performance table
    server_rows = []
    servers = performance_data["servers"]
    for server_name, metrics in sorted(servers.items(), key=lambda x: x[1]["total_tips"], reverse=True):
        consistency_color = "var(--success)" if metrics["consistency_score"] > 80 else "var(--warning)" if metrics["consistency_score"] > 60 else "var(--danger)"
        
        server_rows.append(f"""
        <tr>
            <td style="padding: 12px;"><strong>{server_name}</strong></td>
            <td style="padding: 12px; text-align: center;">{metrics["shifts"]}</td>
            <td style="padding: 12px; text-align: right;">${metrics["total_tips"]:.2f}</td>
            <td style="padding: 12px; text-align: right;">${metrics["avg_tips_per_shift"]:.2f}</td>
            <td style="padding: 12px; text-align: right;">{metrics["efficiency"]:.1f}%</td>
            <td style="padding: 12px; text-align: right;">{metrics["avg_shift_length"]:.1f}h</td>
            <td style="padding: 12px; text-align: center; color: {consistency_color};">
                {metrics["consistency_score"]:.0f}%
            </td>
            <td style="padding: 12px; text-align: right;">${metrics["best_day_tips"]:.2f}</td>
        </tr>
        """)
    
    # Tip recipients table
    recipient_rows = []
    recipients = performance_data["tip_recipients"]
    for emp_name, metrics in sorted(recipients.items(), key=lambda x: x[1]["total_received"], reverse=True):
        source_count = len(metrics["sources"])
        
        recipient_rows.append(f"""
        <tr>
            <td style="padding: 12px;"><strong>{emp_name}</strong></td>
            <td style="padding: 12px; text-align: center;">{metrics["position"]}</td>
            <td style="padding: 12px; text-align: center;">{metrics["shifts_worked"]}</td>
            <td style="padding: 12px; text-align: right;">${metrics["total_received"]:.2f}</td>
            <td style="padding: 12px; text-align: right;">${metrics["avg_per_shift"]:.2f}</td>
            <td style="padding: 12px; text-align: center;">{source_count}</td>
        </tr>
        """)
    
    return STYLE + f"""
    <div class="container">
        <div class="card" style="max-width: 1200px;">
            <div class="breadcrumb">
                <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → <a href="/weekly_reports?restaurant_id={restaurant.id}">Weekly Reports</a> → Staff Performance
            </div>
            
            <div class="header">
                <h2>Staff Performance Analysis</h2>
                <p><strong>{restaurant.name}</strong> | {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')}</p>
            </div>
            
            <h3>Server Performance (Last 30 Days)</h3>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <thead style="background: var(--primary); color: white;">
                    <tr>
                        <th style="padding: 15px;">Server</th>
                        <th style="padding: 15px;">Shifts</th>
                        <th style="padding: 15px;">Total Tips</th>
                        <th style="padding: 15px;">Avg/Shift</th>
                        <th style="padding: 15px;">Efficiency</th>
                        <th style="padding: 15px;">Avg Hours</th>
                        <th style="padding: 15px;">Consistency</th>
                        <th style="padding: 15px;">Best Day</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(server_rows)}
                </tbody>
            </table>
            
            <h3>Tip Recipients Performance</h3>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <thead style="background: var(--secondary); color: white;">
                    <tr>
                        <th style="padding: 15px;">Employee</th>
                        <th style="padding: 15px;">Position</th>
                        <th style="padding: 15px;">Shifts</th>
                        <th style="padding: 15px;">Total Received</th>
                        <th style="padding: 15px;">Avg/Shift</th>
                        <th style="padding: 15px;">Sources</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(recipient_rows)}
                </tbody>
            </table>
            
            <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3>Performance Metrics Explained</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
                    <div><strong>Efficiency:</strong> Tips earned per dollar of sales generated</div>
                    <div><strong>Consistency:</strong> How stable daily tip earnings are (100% = very consistent)</div>
                    <div><strong>Sources:</strong> Number of different servers who tipped out to this employee</div>
                    <div><strong>Best Day:</strong> Highest single-day tip earnings</div>
                </div>
            </div>
            
            <div style="text-align: center;">
                <button onclick="window.print()" class="btn btn-secondary">Print Performance Report</button>
                <form action="/weekly_reports" method="post" style="display: inline;">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <button type="submit" class="btn btn-primary">Back to Reports</button>
                </form>
            </div>
        </div>
    </div>
    """

@app.post("/generate_advanced_report", response_class=HTMLResponse)
def generate_advanced_report(
    restaurant_id: int = Form(...),
    week_selection: str = Form(...),
    custom_start: Optional[str] = Form(""),
    custom_end: Optional[str] = Form(""),
    include_charts: Optional[str] = Form(None),
    include_trends: Optional[str] = Form(None),
    include_comparisons: Optional[str] = Form(None),
    generate_email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Generate advanced weekly report with charts and analytics"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Parse date range
        if week_selection == "custom":
            start_date = custom_start
            end_date = custom_end
        else:
            start_date, end_date = week_selection.split("|")
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        # Get tipouts for the selected period
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date >= start_date,
            Tipout.date <= end_date
        ).all()
        
        # Get comparison data (previous period)
        comparison_tipouts = None
        if include_comparisons == "true":
            period_length = (end_dt - start_dt).days + 1
            comp_start = start_dt - timedelta(days=period_length)
            comp_end = end_dt - timedelta(days=period_length)
            
            comparison_tipouts = db.query(Tipout).filter(
                Tipout.restaurant_id == restaurant_id,
                Tipout.date >= comp_start.strftime("%Y-%m-%d"),
                Tipout.date <= comp_end.strftime("%Y-%m-%d")
            ).all()
        
        # Calculate analytics
        analytics = calculate_advanced_analytics(tipouts, comparison_tipouts)
        chart_data = generate_chart_data(analytics) if include_charts == "true" else None
        
        # Generate report HTML
        report_html = generate_advanced_report_html(
            restaurant, analytics, chart_data, start_dt, end_dt,
            include_charts == "true", include_trends == "true", include_comparisons == "true"
        )
        
        # Generate email summary if requested
        if generate_email == "true":
            email_summary = generate_advanced_email_summary(restaurant, analytics, start_dt, end_dt)
            return report_html + email_summary
        
        return report_html
        
    except Exception as e:
        print(f"Generate advanced report error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Generating Advanced Report</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

def generate_advanced_report_html(restaurant, analytics, chart_data, start_dt, end_dt, include_charts=True, include_trends=True, include_comparisons=True):
    """Generate the advanced report HTML with charts and analytics"""
    
    # Format dates
    period_title = f"Advanced Analytics: {start_dt.strftime('%m/%d')} - {end_dt.strftime('%m/%d/%Y')}"
    
    # Generate insights section
    insights_html = ""
    if include_trends and analytics["insights"]:
        insights_items = []
        for insight in analytics["insights"]:
            insights_items.append(f"<li>{insight}</li>")
        
        insights_html = f"""
        <div style="background: var(--accent); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h3>Key Insights</h3>
            <ul style="margin: 10px 0; padding-left: 20px;">
                {"".join(insights_items)}
            </ul>
        </div>
        """
    
    # Generate charts section
    charts_html = ""
    if include_charts and chart_data:
        chart_js_cdn = '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>'
        
        charts_html = f"""
        {chart_js_cdn}
        
        <h3>Visual Analytics</h3>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin: 20px 0;">
            <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <h4>Daily Revenue & Tips</h4>
                <canvas id="dailyChart" width="400" height="200"></canvas>
            </div>
            
            <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <h4>Tipouts by Position</h4>
                <canvas id="positionChart" width="400" height="200"></canvas>
            </div>
            
            <div style="background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <h4>Top Server Performance</h4>
                <canvas id="serverChart" width="400" height="200"></canvas>
            </div>
        </div>
        
        <script>
        // Daily Revenue Chart
        const dailyCtx = document.getElementById('dailyChart').getContext('2d');
        new Chart(dailyCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(chart_data["daily"]["labels"])},
                datasets: [{{
                    label: 'Revenue',
                    data: {json.dumps(chart_data["daily"]["revenue"])},
                    borderColor: '#43c6ac',
                    backgroundColor: 'rgba(67, 198, 172, 0.1)',
                    tension: 0.4
                }}, {{
                    label: 'Server Tips',
                    data: {json.dumps(chart_data["daily"]["server_tips"])},
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    tension: 0.4
                }}, {{
                    label: 'Tipouts',
                    data: {json.dumps(chart_data["daily"]["tipouts"])},
                    borderColor: '#e67e22',
                    backgroundColor: 'rgba(230, 126, 34, 0.1)',
                    tension: 0.4
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            callback: function(value) {{
                                return '$' + value.toFixed(0);
                            }}
                        }}
                    }}
                }}
            }}
        }});
        
        // Position Chart
        const positionCtx = document.getElementById('positionChart').getContext('2d');
        new Chart(positionCtx, {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(chart_data["positions"]["labels"])},
                datasets: [{{
                    data: {json.dumps(chart_data["positions"]["data"])},
                    backgroundColor: [
                        '#43c6ac',
                        '#2ecc71', 
                        '#e67e22',
                        '#f39c12',
                        '#e74c3c'
                    ]
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});
        
        // Server Performance Chart
        const serverCtx = document.getElementById('serverChart').getContext('2d');
        new Chart(serverCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(chart_data["servers"]["labels"])},
                datasets: [{{
                    label: 'Tips Earned',
                    data: {json.dumps(chart_data["servers"]["tips"])},
                    backgroundColor: '#43c6ac'
                }}, {{
                    label: 'Efficiency %',
                    data: {json.dumps(chart_data["servers"]["efficiency"])},
                    backgroundColor: '#2ecc71',
                    yAxisID: 'y1'
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        position: 'left',
                        ticks: {{
                            callback: function(value) {{
                                return '$' + value.toFixed(0);
                            }}
                        }}
                    }},
                    y1: {{
                        type: 'linear',
                        position: 'right',
                        beginAtZero: true,
                        max: 10,
                        ticks: {{
                            callback: function(value) {{
                                return value.toFixed(1) + '%';
                            }}
                        }}
                    }}
                }}
            }}
        }});
        </script>
        """
    
    # Generate server performance table
    server_performance_html = ""
    if analytics["server_rankings"]:
        server_rows = []
        for i, (server_name, perf) in enumerate(analytics["server_rankings"], 1):
            avg_tips = perf["tips"] / perf["shifts"] if perf["shifts"] > 0 else 0
            server_rows.append(f"""
            <tr style="background: {'rgba(67, 198, 172, 0.1)' if i <= 3 else 'white'};">
                <td style="padding: 10px; text-align: center;">{i}</td>
                <td style="padding: 10px;"><strong>{server_name}</strong></td>
                <td style="padding: 10px; text-align: center;">{perf["shifts"]}</td>
                <td style="padding: 10px; text-align: right;">${perf["tips"]:.2f}</td>
                <td style="padding: 10px; text-align: right;">${avg_tips:.2f}</td>
                <td style="padding: 10px; text-align: right;">{perf["efficiency"]:.1f}%</td>
            </tr>
            """)
        
        server_performance_html = f"""
        <h3>Server Performance Rankings</h3>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            <thead style="background: var(--primary); color: white;">
                <tr>
                    <th style="padding: 15px; text-align: center;">Rank</th>
                    <th style="padding: 15px;">Server</th>
                    <th style="padding: 15px; text-align: center;">Shifts</th>
                    <th style="padding: 15px; text-align: right;">Total Tips</th>
                    <th style="padding: 15px; text-align: right;">Avg per Shift</th>
                    <th style="padding: 15px; text-align: right;">Efficiency</th>
                </tr>
            </thead>
            <tbody>
                {"".join(server_rows)}
            </tbody>
        </table>
        """
    
    return STYLE + f"""
    <div class="container">
        <div class="card" style="max-width: 1000px;">
            <div class="breadcrumb">
                <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → <a href="/weekly_reports?restaurant_id={restaurant.id}">Weekly Reports</a> → Advanced Report
            </div>
            
            <div class="header">
                <h2>{period_title}</h2>
                <p><strong>{restaurant.name}</strong></p>
            </div>
            
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="summary-value">${analytics["total_revenue"]:.2f}</div>
                    <div class="summary-label">Total Revenue</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${analytics["total_tipouts"]:.2f}</div>
                    <div class="summary-label">Total Tipouts</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${analytics["avg_daily_revenue"]:.2f}</div>
                    <div class="summary-label">Avg Daily Revenue</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{analytics["tipout_rate"]:.1f}%</div>
                    <div class="summary-label">Tipout Rate</div>
                </div>
            </div>
            
            {insights_html}
            {charts_html}
            {server_performance_html}
            
            <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3>Period Summary</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div><strong>Busiest Day:</strong> {analytics["busiest_day"]}</div>
                    <div><strong>Peak Hour:</strong> {analytics["peak_hour"]}</div>
                    <div><strong>Days with Data:</strong> {len(analytics["daily_data"])}</div>
                    <div><strong>Active Positions:</strong> {len(analytics["position_totals"])}</div>
                </div>
            </div>
            
            <div style="text-align: center;">
                <button onclick="window.print()" class="btn btn-secondary">Print Report</button>
                <form action="/weekly_reports" method="post" style="display: inline;">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <button type="submit" class="btn btn-primary">Generate New Report</button>
                </form>
            </div>
        </div>
    </div>
    """

def generate_advanced_email_summary(restaurant, analytics, start_dt, end_dt):
    """Generate enhanced email summary for management"""
    
    date_range = f"{start_dt.strftime('%B %d')} - {end_dt.strftime('%B %d, %Y')}"
    
    # Top insights
    insights_text = "\n".join([f"• {insight}" for insight in analytics["insights"][:5]])
    
    # Top performers
    top_performers = ""
    for i, (server_name, perf) in enumerate(analytics["server_rankings"][:3], 1):
        top_performers += f"{i}. {server_name}: ${perf['tips']:.2f} ({perf['shifts']} shifts)\n"
    
    email_content = f"""
Subject: {restaurant.name} - Advanced Weekly Analytics ({date_range})

Dear Management Team,

EXECUTIVE DASHBOARD - {date_range}
================================================

KEY METRICS
-----------
💰 Total Revenue: ${analytics["total_revenue"]:.2f}
💸 Total Tipouts: ${analytics["total_tipouts"]:.2f} ({analytics["tipout_rate"]:.1f}% of revenue)
📊 Average Daily Revenue: ${analytics["avg_daily_revenue"]:.2f}
📈 Busiest Day: {analytics["busiest_day"]}
⏰ Peak Hour: {analytics["peak_hour"]}

PERFORMANCE INSIGHTS
--------------------
{insights_text}

TOP PERFORMERS
--------------
{top_performers}

OPERATIONAL SUMMARY
===================
- Revenue Efficiency: {"Excellent" if analytics["tipout_rate"] < 6 else "Good" if analytics["tipout_rate"] < 8 else "Needs Review"}
- Staff Utilization: {len(analytics["server_rankings"])} active servers
- Position Coverage: {len(analytics["position_totals"])} tip positions active
- Data Quality: {len(analytics["daily_data"])} days with complete data

This advanced report was generated automatically with trend analysis and performance insights.
Access the full interactive dashboard for detailed charts and comparisons.

Best regards,
Advanced Tipout Analytics System
    """
    
    return STYLE + f"""
    <div class="container">
        <div class="card">
            <div class="header">
                <h2>📧 Enhanced Email Summary</h2>
                <p>Copy and send this advanced summary to ownership/management</p>
            </div>
            
            <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h3>Email Content</h3>
                    <button onclick="copyAdvancedEmail()" class="btn btn-primary">Copy to Clipboard</button>
                </div>
                
                <div id="advancedEmailContent" style="background: white; padding: 15px; border: 1px solid #ddd; border-radius: 5px; font-family: monospace; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">
{email_content}
                </div>
            </div>
            
            <div style="text-align: center;">
                <form action="/weekly_reports" method="post" style="display: inline;">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <button type="submit" class="btn btn-secondary">Generate New Report</button>
                </form>
            </div>
        </div>
    </div>
    
    <script>
    function copyAdvancedEmail() {{
        const content = document.getElementById('advancedEmailContent').textContent;
        navigator.clipboard.writeText(content).then(function() {{
            alert('Advanced email summary copied to clipboard!');
        }}, function(err) {{
            console.error('Could not copy text: ', err);
            const textArea = document.createElement('textarea');
            textArea.value = content;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            alert('Advanced email summary copied to clipboard!');
        }});
    }}
    </script>
    """

def calculate_advanced_analytics(tipouts, comparison_tipouts=None):
    """Calculate advanced analytics with trends and insights"""
    if not tipouts:
        return {
            "total_revenue": 0, "total_tipouts": 0, "total_server_tips": 0,
            "daily_averages": {}, "position_performance": {}, "server_rankings": [],
            "trends": {}, "insights": [], "busiest_day": "N/A", "peak_hours": "N/A"
        }
    
    # Basic calculations
    daily_data = defaultdict(lambda: {"revenue": 0, "tipouts": 0, "server_tips": 0, "shifts": 0})
    position_totals = defaultdict(float)
    server_performance = defaultdict(lambda: {"tips": 0, "tipouts": 0, "shifts": 0, "revenue": 0, "efficiency": 0})
    hourly_data = defaultdict(lambda: {"count": 0, "revenue": 0})
    
    total_revenue = 0
    total_server_tips = 0
    total_tipouts = 0
    
    for tipout in tipouts:
        # Daily aggregation
        revenue = tipout.total_alc_sales + tipout.total_food_sales
        total_revenue += revenue
        total_server_tips += tipout.server_tips
        
        daily_data[tipout.date]["revenue"] += revenue
        daily_data[tipout.date]["server_tips"] += tipout.server_tips
        daily_data[tipout.date]["shifts"] += 1
        
        # Parse tipout details
        try:
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            shift_tipout = sum(pos_data.get('amount', 0) for pos_data in details.values())
            total_tipouts += shift_tipout
            daily_data[tipout.date]["tipouts"] += shift_tipout
            
            for position_name, position_data in details.items():
                position_totals[position_name] += position_data.get('amount', 0)
        except:
            pass
        
        # Server performance
        server_performance[tipout.server_name]["tips"] += tipout.server_tips
        server_performance[tipout.server_name]["revenue"] += revenue
        server_performance[tipout.server_name]["shifts"] += 1
        
        # Hour analysis
        try:
            hour = int(tipout.start_time.split(':')[0])
            hourly_data[hour]["count"] += 1
            hourly_data[hour]["revenue"] += revenue
        except:
            pass
    
    # Calculate server efficiency (tips per dollar of sales)
    for server_name, perf in server_performance.items():
        if perf["revenue"] > 0:
            perf["efficiency"] = (perf["tips"] / perf["revenue"]) * 100
    
    # Server rankings
    server_rankings = sorted(
        [(name, data) for name, data in server_performance.items()],
        key=lambda x: x[1]["tips"],
        reverse=True
    )
    
    # Find patterns
    busiest_day = max(daily_data.keys(), key=lambda d: daily_data[d]["revenue"]) if daily_data else "N/A"
    peak_hour = max(hourly_data.keys(), key=lambda h: hourly_data[h]["revenue"]) if hourly_data else "N/A"
    
    # Generate insights
    insights = []
    if daily_data:
        avg_daily_revenue = total_revenue / len(daily_data)
        best_day_revenue = daily_data[busiest_day]["revenue"]
        if best_day_revenue > avg_daily_revenue * 1.2:
            insights.append(f"Peak performance: {busiest_day} generated ${best_day_revenue:.2f} (20% above average)")
    
    if server_rankings:
        top_server = server_rankings[0]
        insights.append(f"Top performer: {top_server[0]} earned ${top_server[1]['tips']:.2f} in tips")
    
    tipout_rate = (total_tipouts / total_revenue * 100) if total_revenue > 0 else 0
    if tipout_rate > 8:
        insights.append(f"High tipout rate: {tipout_rate:.1f}% of revenue (consider review)")
    elif tipout_rate < 3:
        insights.append(f"Low tipout rate: {tipout_rate:.1f}% of revenue (staff may be under-compensated)")
    
    return {
        "total_revenue": total_revenue,
        "total_tipouts": total_tipouts, 
        "total_server_tips": total_server_tips,
        "daily_data": dict(daily_data),
        "position_totals": dict(position_totals),
        "server_performance": dict(server_performance),
        "server_rankings": server_rankings[:5],  # Top 5
        "busiest_day": busiest_day,
        "peak_hour": f"{peak_hour}:00" if peak_hour != "N/A" else "N/A",
        "insights": insights,
        "tipout_rate": tipout_rate,
        "avg_daily_revenue": total_revenue / len(daily_data) if daily_data else 0
    }

def generate_chart_data(analytics):
    """Generate data for Chart.js charts"""
    daily_data = analytics["daily_data"]
    
    # Daily revenue chart
    sorted_days = sorted(daily_data.keys())
    daily_chart = {
        "labels": [datetime.strptime(d, "%Y-%m-%d").strftime("%a %m/%d") for d in sorted_days],
        "revenue": [daily_data[d]["revenue"] for d in sorted_days],
        "tipouts": [daily_data[d]["tipouts"] for d in sorted_days],
        "server_tips": [daily_data[d]["server_tips"] for d in sorted_days]
    }
    
    # Position breakdown chart
    position_data = analytics["position_totals"]
    position_chart = {
        "labels": list(position_data.keys()),
        "data": list(position_data.values())
    }
    
    # Server performance chart
    server_rankings = analytics["server_rankings"][:5]  # Top 5
    server_chart = {
        "labels": [ranking[0] for ranking in server_rankings],
        "tips": [ranking[1]["tips"] for ranking in server_rankings],
        "efficiency": [ranking[1]["efficiency"] for ranking in server_rankings]
    }
    
    return {
        "daily": daily_chart,
        "positions": position_chart,
        "servers": server_chart
    }
def calculate_period_analytics(tipouts):
    """Calculate comprehensive analytics for a period"""
    if not tipouts:
        return {
            "total_revenue": 0,
            "total_tipouts": 0,
            "total_server_tips": 0,
            "days_with_data": 0,
            "position_totals": {},
            "server_performance": {},
            "daily_breakdown": {},
            "busiest_day": "N/A",
            "avg_daily_revenue": 0,
            "avg_daily_tipouts": 0
        }
    
    total_revenue = 0
    total_server_tips = 0
    position_totals = defaultdict(float)
    server_performance = defaultdict(lambda: {"tips": 0, "tipouts": 0, "shifts": 0, "revenue": 0})
    daily_breakdown = defaultdict(lambda: {"revenue": 0, "tipouts": 0, "shifts": 0})
    
    for tipout in tipouts:
        # Calculate revenue
        revenue = tipout.total_alc_sales + tipout.total_food_sales
        total_revenue += revenue
        total_server_tips += tipout.server_tips
        
        # Parse tipout details
        try:
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            for position_name, position_data in details.items():
                amount = position_data.get('amount', 0.0)
                position_totals[position_name] += amount
        except:
            pass
        
        # Server performance
        server_performance[tipout.server_name]["tips"] += tipout.server_tips
        server_performance[tipout.server_name]["shifts"] += 1
        server_performance[tipout.server_name]["revenue"] += revenue
        
        # Calculate total tipouts for this server
        try:
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            server_tipout_total = sum(pos_data.get('amount', 0) for pos_data in details.values())
            server_performance[tipout.server_name]["tipouts"] += server_tipout_total
        except:
            pass
        
        # Daily breakdown
        daily_breakdown[tipout.date]["revenue"] += revenue
        daily_breakdown[tipout.date]["shifts"] += 1
        try:
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            daily_tipout_total = sum(pos_data.get('amount', 0) for pos_data in details.values())
            daily_breakdown[tipout.date]["tipouts"] += daily_tipout_total
        except:
            pass
    
    # Find busiest day
    busiest_day = max(daily_breakdown.keys(), key=lambda d: daily_breakdown[d]["revenue"]) if daily_breakdown else "N/A"
    
    # Calculate totals
    total_tipouts = sum(position_totals.values())
    days_with_data = len(daily_breakdown)
    avg_daily_revenue = total_revenue / days_with_data if days_with_data > 0 else 0
    avg_daily_tipouts = total_tipouts / days_with_data if days_with_data > 0 else 0
    
    return {
        "total_revenue": total_revenue,
        "total_tipouts": total_tipouts,
        "total_server_tips": total_server_tips,
        "days_with_data": days_with_data,
        "position_totals": dict(position_totals),
        "server_performance": dict(server_performance),
        "daily_breakdown": dict(daily_breakdown),
        "busiest_day": busiest_day,
        "avg_daily_revenue": avg_daily_revenue,
        "avg_daily_tipouts": avg_daily_tipouts
    }

def generate_report_html(restaurant, analytics, comparison_data, start_dt, end_dt, report_type):
    """Generate the main report HTML"""
    
    # Calculate comparison metrics
    comparison_html = ""
    if comparison_data:
        revenue_change = analytics["total_revenue"] - comparison_data["total_revenue"]
        revenue_pct = (revenue_change / comparison_data["total_revenue"] * 100) if comparison_data["total_revenue"] > 0 else 0
        
        tipout_change = analytics["total_tipouts"] - comparison_data["total_tipouts"]
        tipout_pct = (tipout_change / comparison_data["total_tipouts"] * 100) if comparison_data["total_tipouts"] > 0 else 0
        
        revenue_arrow = "↑" if revenue_change >= 0 else "↓"
        tipout_arrow = "↑" if tipout_change >= 0 else "↓"
        
        comparison_html = f"""
        <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h3>Period Comparison</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="summary-value" style="color: {'var(--success)' if revenue_change >= 0 else 'var(--danger)'};">
                        {revenue_arrow} ${revenue_change:.2f}
                    </div>
                    <div class="summary-label">Revenue Change ({revenue_pct:+.1f}%)</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value" style="color: {'var(--success)' if tipout_change >= 0 else 'var(--danger)'};">
                        {tipout_arrow} ${tipout_change:.2f}
                    </div>
                    <div class="summary-label">Tipout Change ({tipout_pct:+.1f}%)</div>
                </div>
            </div>
        </div>
        """
    
    # Generate position breakdown
    position_items = []
    for position_name, total_amount in analytics["position_totals"].items():
        avg_per_day = total_amount / analytics["days_with_data"] if analytics["days_with_data"] > 0 else 0
        position_items.append(f"""
        <div class="summary-item">
            <div class="summary-value">${total_amount:.2f}</div>
            <div class="summary-label">{position_name}</div>
            <div style="font-size: 0.8em; color: var(--secondary);">${avg_per_day:.2f}/day avg</div>
        </div>
        """)
    
    position_html = "".join(position_items) if position_items else "<p>No position data available</p>"
    
    # Generate server performance
    server_items = []
    for server_name, performance in analytics["server_performance"].items():
        avg_tips = performance["tips"] / performance["shifts"] if performance["shifts"] > 0 else 0
        avg_revenue = performance["revenue"] / performance["shifts"] if performance["shifts"] > 0 else 0
        
        server_items.append(f"""
        <div class="tipout-item">
            <h4>{server_name}</h4>
            <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                <span>Shifts: {performance["shifts"]}</span>
                <span>Total Tips: ${performance["tips"]:.2f}</span>
                <span>Avg Tips/Shift: ${avg_tips:.2f}</span>
                <span>Avg Revenue/Shift: ${avg_revenue:.2f}</span>
            </div>
        </div>
        """)
    
    server_html = "".join(server_items) if server_items else "<p>No server data available</p>"
    
    # Format report type title
    if report_type == "weekly":
        period_title = f"Weekly Report: {start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        period_title = f"Monthly Report: {start_dt.strftime('%B %Y')}"
    else:
        period_title = f"Custom Report: {start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')}"
    
    return STYLE + f"""
    <div class="container">
        <div class="card">
            <div class="breadcrumb">
                <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → <a href="/weekly_reports?restaurant_id={restaurant.id}">Weekly Reports</a> → Report
            </div>
            
            <div class="header">
                <h2>{period_title}</h2>
                <p><strong>{restaurant.name}</strong></p>
            </div>
            
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="summary-value">${analytics["total_revenue"]:.2f}</div>
                    <div class="summary-label">Total Revenue</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${analytics["total_tipouts"]:.2f}</div>
                    <div class="summary-label">Total Tipouts</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${analytics["avg_daily_revenue"]:.2f}</div>
                    <div class="summary-label">Avg Daily Revenue</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{analytics["days_with_data"]}</div>
                    <div class="summary-label">Days with Data</div>
                </div>
            </div>
            
            {comparison_html}
            
            <h3>Tipouts by Position</h3>
            <div class="summary-grid">
                {position_html}
            </div>
            
            <h3>Server Performance</h3>
            {server_html}
            
            <div style="background: var(--primary); color: white; padding: 20px; border-radius: 10px; text-align: center; margin: 20px 0;">
                <h3>Key Insights</h3>
                <p><strong>Busiest Day:</strong> {analytics["busiest_day"]}</p>
                <p><strong>Average Daily Tipouts:</strong> ${analytics["avg_daily_tipouts"]:.2f}</p>
                <p><strong>Total Shifts:</strong> {sum(p["shifts"] for p in analytics["server_performance"].values())}</p>
            </div>
            
            <div style="text-align: center;">
                <button onclick="window.print()" class="btn btn-secondary">Print Report</button>
                <form action="/weekly_reports" method="post" style="display: inline;">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <button type="submit" class="btn btn-primary">Generate New Report</button>
                </form>
            </div>
        </div>
    </div>
    """

def generate_email_summary(restaurant, analytics, comparison_data, start_dt, end_dt, report_type):
    """Generate email summary for management"""
    
    # Format dates
    date_range = f"{start_dt.strftime('%B %d')} - {end_dt.strftime('%B %d, %Y')}"
    
    # Calculate key metrics
    total_shifts = sum(p["shifts"] for p in analytics["server_performance"].values())
    tipout_percentage = (analytics["total_tipouts"] / analytics["total_revenue"] * 100) if analytics["total_revenue"] > 0 else 0
    avg_revenue_per_shift = (analytics["total_revenue"] / total_shifts) if total_shifts > 0 else 0  # ADD THIS LINE HERE
    
    # Comparison text
    comparison_text = ""
    if comparison_data:
        revenue_change = analytics["total_revenue"] - comparison_data["total_revenue"]
        revenue_pct = (revenue_change / comparison_data["total_revenue"] * 100) if comparison_data["total_revenue"] > 0 else 0
        
        if revenue_change >= 0:
            comparison_text = f"Revenue increased by ${revenue_change:.2f} ({revenue_pct:+.1f}%) compared to the previous period."
        else:
            comparison_text = f"Revenue decreased by ${abs(revenue_change):.2f} ({revenue_pct:.1f}%) compared to the previous period."
    
    # Top positions
    top_positions = sorted(analytics["position_totals"].items(), key=lambda x: x[1], reverse=True)[:3]
    top_positions_text = ", ".join([f"{name}: ${amount:.2f}" for name, amount in top_positions])
    
    # Top server
    top_server = max(analytics["server_performance"].items(), key=lambda x: x[1]["tips"]) if analytics["server_performance"] else ("N/A", {"tips": 0})
    
    email_content = f"""
Subject: {restaurant.name} - {report_type.title()} Report ({date_range})

Dear Management Team,

Please find below the {report_type} performance summary for {restaurant.name}:

EXECUTIVE SUMMARY
=================
• Period: {date_range}
• Total Revenue: ${analytics["total_revenue"]:.2f}
• Total Tipouts: ${analytics["total_tipouts"]:.2f} ({tipout_percentage:.1f}% of revenue)
• Total Shifts: {total_shifts}
• Days with Data: {analytics["days_with_data"]}

{comparison_text}

KEY METRICS
===========
• Average Daily Revenue: ${analytics["avg_daily_revenue"]:.2f}
• Average Daily Tipouts: ${analytics["avg_daily_tipouts"]:.2f}
• Busiest Day: {analytics["busiest_day"]}
• Top Performing Server: {top_server[0]} (${top_server[1]["tips"]:.2f} in tips)

TIPOUT BREAKDOWN
================
{top_positions_text}

OPERATIONAL INSIGHTS
====================
- Tipout efficiency is {"within normal range" if 3 <= tipout_percentage <= 8 else "outside normal range (3-8%)"}
- Average revenue per shift: ${avg_revenue_per_shift:.2f}  # USE THE VARIABLE HERE
- Server utilization: {len(analytics["server_performance"])} active servers

This report was generated automatically by the Tipout Management System.
For detailed analytics, please access the full dashboard.

Best regards,
Tipout Management System
    """
    
    return STYLE + f"""
    <div class="container">
        <div class="card">
            <div class="header">
                <h2>Email Summary for Management</h2>
                <p>Copy and paste the content below to send to ownership/management</p>
            </div>
            
            <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h3>Email Content</h3>
                    <button onclick="copyEmailContent()" class="btn btn-primary">Copy to Clipboard</button>
                </div>
                
                <div id="emailContent" style="background: white; padding: 15px; border: 1px solid #ddd; border-radius: 5px; font-family: monospace; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">
{email_content}
                </div>
            </div>
            
            <div style="text-align: center;">
                <form action="/weekly_reports" method="post" style="display: inline;">
                    <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                    <button type="submit" class="btn btn-secondary">Generate New Report</button>
                </form>
            </div>
        </div>
    </div>
    
    <script>
    function copyEmailContent() {{
        const content = document.getElementById('emailContent').textContent;
        navigator.clipboard.writeText(content).then(function() {{
            alert('Email content copied to clipboard!');
        }}, function(err) {{
            console.error('Could not copy text: ', err);
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = content;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            alert('Email content copied to clipboard!');
        }});
    }}
    </script>
    """

# Add this route to the main dashboard to include weekly reports access
def restaurant_dashboard_with_reports(restaurant_id: int, db: Session):
    """Enhanced dashboard with weekly reports access"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + """
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>Restaurant Not Found</h3>
                    </div>
                    <div style="text-align: center;">
                        <a href="/" class="btn btn-primary">Back to Home</a>
                    </div>
                </div>
            </div>
            """
        
        tip_positions_count = db.query(TipPosition).filter(TipPosition.restaurant_id == restaurant_id, TipPosition.is_active == True).count()
        
        toast_status = ""
        if restaurant.toast_client_id:
            toast_status = '<div class="toast-status">Toast POS Connected</div>'
        else:
            toast_status = '<div class="manual-entry">Manual Entry Mode</div>'
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → Dashboard
                </div>
                
                <div class="header">
                    <h1>{restaurant.name}</h1>
                    {toast_status}
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{tip_positions_count}</div>
                        <div class="summary-label">Active Tip Positions</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len(json.loads(restaurant.server_names))}</div>
                        <div class="summary-label">Total Servers</div>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <form action="/daily_status" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-primary">Daily Status & Tipout</button>
                    </form>
                    
                    <form action="/weekly_reports" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-success">Weekly Reports & Analytics</button>
                    </form>
                    <form action="/scheduling" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-warning">Employee Scheduling</button>
                    </form>
                    
                    <form action="/totals" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <label style="display: block; margin: 10px 0;">Select Date for Totals:</label>
                        <input type="date" name="date" required style="width: 200px; margin: 5px;">
                        <button type="submit" class="btn btn-secondary">View Daily Totals</button>
                    </form>
                    
                    <form action="/settings" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-warning">Settings & Positions</button>
                    </form>

                    <form action="/payroll_exports" method="get" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-warning">Payroll Exports</button>
                    </form>
                </div>
                
                <div style="text-align: center;">
                    <a href="/" class="btn btn-light">Logout</a>
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
                    <h3>Dashboard Error</h3>
                    <p>{str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <a href="/" class="btn btn-primary">Back to Home</a>
                </div>
            </div>
        </div>
        """

# Update the existing restaurant_dashboard function to use the new one
def restaurant_dashboard(restaurant_id: int, db: Session):
    return restaurant_dashboard_with_reports(restaurant_id, db)

@app.get("/payroll_exports", response_class=HTMLResponse)
def payroll_exports_get(restaurant_id: int, db: Session = Depends(get_db)):
    """GET version for direct URL access"""
    return payroll_exports_form_get(restaurant_id, db)

def payroll_exports_form_get(restaurant_id: int, db: Session):
    """Show the payroll exports interface via GET"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get current pay period dates
        today = date.today()
        
        # Default to current week
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        # Bi-weekly period (last 14 days)
        biweekly_start = today - timedelta(days=13)
        biweekly_end = today
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Payroll Exports
                </div>
                
                <div class="header">
                    <h2>Payroll Export Center</h2>
                    <p><strong>{restaurant.name}</strong></p>
                    <p style="color: var(--secondary);">Export tip data for seamless payroll processing</p>
                </div>
                
                <div style="background: var(--primary); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Quick Exports</h3>
                    <p style="margin-bottom: 15px;">Common payroll scenarios for immediate download</p>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <form action="/generate_payroll_export" method="post" style="display: contents;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="payroll_provider" value="quickbooks">
                            <input type="hidden" name="export_format" value="csv">
                            <input type="hidden" name="pay_period" value="biweekly">
                            <input type="hidden" name="week_option" value="custom">
                            <input type="hidden" name="start_date" value="{biweekly_start}">
                            <input type="hidden" name="end_date" value="{biweekly_end}">
                            <input type="hidden" name="include_summary" value="true">
                            <input type="hidden" name="separate_positions" value="true">
                            <button type="submit" class="btn btn-light">QuickBooks Bi-weekly</button>
                        </form>

                        <form action="/generate_payroll_export" method="post" style="display: contents;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="payroll_provider" value="generic">
                            <input type="hidden" name="export_format" value="csv">
                            <input type="hidden" name="pay_period" value="weekly">
                            <input type="hidden" name="week_option" value="custom">
                            <input type="hidden" name="start_date" value="{start_of_week}">
                            <input type="hidden" name="end_date" value="{end_of_week}">
                            <input type="hidden" name="include_summary" value="true">
                            <input type="hidden" name="separate_positions" value="true">
                            <button type="submit" class="btn btn-light">Generic CSV Weekly</button>
                        </form>
                    </div>
                </div>
                
                <div style="text-align: center;">
                    <a href="/menu?restaurant_id={restaurant.id}" class="btn btn-secondary">Back to Dashboard</a>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return STYLE + f"<div class='container'><div class='card'><div class='error'><h3>Error: {str(e)}</h3></div></div></div>"
    except Exception as e:
        return STYLE + f"<div class='container'><div class='card'><div class='error'><h3>Error: {str(e)}</h3></div></div></div>"
@app.post("/payroll_exports", response_class=HTMLResponse)
def payroll_exports_form(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Show the payroll exports interface"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Get current pay period dates
        today = date.today()
        
        # Default to current week
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        # Bi-weekly period (last 14 days)
        biweekly_start = today - timedelta(days=13)
        biweekly_end = today
        
        # Monthly period
        monthly_start = today.replace(day=1)
        if today.month == 12:
            monthly_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            monthly_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → Payroll Exports
                </div>
                
                <div class="header">
                    <h2>Payroll Export Center</h2>
                    <p><strong>{restaurant.name}</strong></p>
                    <p style="color: var(--secondary);">Export tip data for seamless payroll processing</p>
                </div>
                
                <div style="background: var(--light); padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Export Configuration</h3>
                    <form action="/generate_payroll_export" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Payroll Provider:</label>
                                <select name="payroll_provider" required>
                                    <option value="adp">ADP Workforce Now</option>
                                    <option value="quickbooks">QuickBooks Payroll</option>
                                    <option value="paychex">Paychex</option>
                                    <option value="gusto">Gusto</option>
                                    <option value="toast_payroll">Toast Payroll</option>
                                    <option value="generic">Generic CSV</option>
                                    <option value="excel">Excel Spreadsheet</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Export Format:</label>
                                <select name="export_format" required>
                                    <option value="csv">CSV File</option>
                                    <option value="excel">Excel (.xlsx)</option>
                                </select>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Pay Period:</label>
                                <select name="pay_period" required>
                                    <option value="weekly">Weekly</option>
                                    <option value="biweekly">Bi-weekly</option>
                                    <option value="monthly">Monthly</option>
                                    <option value="custom">Custom Range</option>
                                </select>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Start Date:</label>
                                <input type="date" name="start_date" value="{start_of_week}" required>
                            </div>
                            <div class="form-group">
                                <label>End Date:</label>
                                <input type="date" name="end_date" value="{end_of_week}" required>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Export Options:</label>
                            <div style="margin-top: 10px;">
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="include_summary" value="true" checked style="margin-right: 10px;">
                                    Include summary totals
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="separate_positions" value="true" checked style="margin-right: 10px;">
                                    Separate columns by tip position
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="include_hourly_data" value="true" style="margin-right: 10px;">
                                    Include hours worked (if available)
                                </label>
                            </div>
                        </div>
                        
                        <div style="text-align: center; margin-top: 20px;">
                            <button type="submit" class="btn btn-success">Generate Export</button>
                        </div>
                    </form>
                </div>
                
                <div style="background: var(--primary); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Quick Exports</h3>
                    <p style="margin-bottom: 15px;">Common payroll scenarios for immediate download</p>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <form action="/generate_payroll_export" method="post" style="display: contents;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="payroll_provider" value="quickbooks">
                            <input type="hidden" name="export_format" value="csv">
                            <input type="hidden" name="pay_period" value="biweekly">
                            <input type="hidden" name="start_date" value="{biweekly_start}">
                            <input type="hidden" name="end_date" value="{biweekly_end}">
                            <input type="hidden" name="include_summary" value="true">
                            <input type="hidden" name="separate_positions" value="true">
                            <button type="submit" class="btn btn-light">QuickBooks<br>Bi-weekly</button>
                        </form>
    
                        <form action="/generate_payroll_export" method="post" style="display: contents;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="payroll_provider" value="adp">
                            <input type="hidden" name="export_format" value="csv">
                            <input type="hidden" name="pay_period" value="weekly">
                            <input type="hidden" name="week_option" value="custom">
                            <input type="hidden" name="start_date" value="{start_of_week}">
                            <input type="hidden" name="end_date" value="{end_of_week}">
                            <input type="hidden" name="include_summary" value="true">
                            <input type="hidden" name="separate_positions" value="true">
                            <button type="submit" class="btn btn-light">ADP<br>Weekly</button>
                        </form>
    
                        <form action="/generate_payroll_export" method="post" style="display: contents;">
                            <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                            <input type="hidden" name="payroll_provider" value="excel">
                            <input type="hidden" name="export_format" value="excel">
                            <input type="hidden" name="pay_period" value="monthly">
                            <input type="hidden" name="week_option" value="custom">
                            <input type="hidden" name="start_date" value="{monthly_start}">
                            <input type="hidden" name="end_date" value="{monthly_end}">
                            <input type="hidden" name="include_summary" value="true">
                            <input type="hidden" name="separate_positions" value="true">
                            <button type="submit" class="btn btn-light">Excel<br>Monthly</button>
                        </form>
                    </div>
                </div>
                
                <div style="text-align: center;">
                    <form action="/menu" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Dashboard</button>
                    </form>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        print(f"Payroll exports form error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Payroll Exports</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/generate_payroll_export")
async def generate_payroll_export(
    restaurant_id: int = Form(...),
    payroll_provider: str = Form(...),
    export_format: str = Form(...),
    pay_period: str = Form(...),
    week_option: str = Form(...),
    start_date: Optional[str] = Form(""),
    end_date: Optional[str] = Form(""),
    include_summary: Optional[str] = Form(None),
    separate_positions: Optional[str] = Form(None),
    include_hourly_data: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Generate and download payroll export file"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        
        # Get tipouts for the specified period
        # Calculate date range based on week option
        from datetime import datetime, timedelta
        
        if week_option == "current":
            today = datetime.now().date()
            days_since_monday = today.weekday()
            start_dt = today - timedelta(days=days_since_monday)
            end_dt = start_dt + timedelta(days=6)
        elif week_option == "last":
            today = datetime.now().date()
            days_since_monday = today.weekday()
            current_monday = today - timedelta(days=days_since_monday)
            start_dt = current_monday - timedelta(days=7)
            end_dt = start_dt + timedelta(days=6)
        else:  # custom
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        start_date_str = start_dt.strftime("%Y-%m-%d")
        end_date_str = end_dt.strftime("%Y-%m-%d")
        
        # Get tipouts for the calculated period
        tipouts = db.query(Tipout).filter(
            Tipout.restaurant_id == restaurant_id,
            Tipout.date >= start_date_str,
            Tipout.date <= end_date_str
        ).all()
        
        if not tipouts:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="warning">
                        <h3>No Data Found</h3>
                        <p>No tipout records found for the selected date range ({start_date} to {end_date}).</p>
                        <p>Please select a different date range or ensure tipouts have been calculated.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/payroll_exports" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Exports</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        

        # Process tipout data for export
        export_data = process_complete_tipout_data_for_export(
            tipouts, 
            include_servers=True,  # Include servers in export
            include_hours=include_hourly_data == "true"
        )
        
        # Generate filename
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        filename_base = f"{restaurant.name.replace(' ', '_')}_{payroll_provider}_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}"
        
        if export_format == "excel":
            filename = f"{filename_base}.xlsx"
            file_content = generate_excel_export(export_data, payroll_provider, restaurant, start_dt, end_dt, include_summary == "true")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            filename = f"{filename_base}.csv"
            file_content = generate_csv_export(export_data, payroll_provider, include_summary == "true")
            media_type = "text/csv"
        
        # Return file download
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        print(f"Generate payroll export error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Export Generation Error</h3>
                    <p>Error generating export: {str(e)}</p>
                </div>
                <div style="text-align: center;">
                    <form action="/payroll_exports" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                        <button type="submit" class="btn btn-primary">Back to Exports</button>
                    </form>
                </div>
            </div>
        </div>
        """
@app.post("/add_employee", response_class=HTMLResponse)
def add_employee(
    restaurant_id: int = Form(...),
    position_id: int = Form(...),
    employee_name: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        position = db.query(TipPosition).filter(TipPosition.id == position_id).first()
        if not position:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Position not found!</h3></div></div></div>"
        
        # Get current employees
        try:
            current_employees = json.loads(position.employee_names) if position.employee_names else []
        except:
            current_employees = []
        
        # Check if employee already exists
        employee_name = employee_name.strip()
        if employee_name.lower() in [emp.lower() for emp in current_employees]:
            return STYLE + f"""
            <div class="container">
                <div class="card">
                    <div class="error">
                        <h3>Employee Already Exists</h3>
                        <p>"{employee_name}" is already assigned to this position.</p>
                    </div>
                    <div style="text-align: center;">
                        <form action="/settings" method="post">
                            <input type="hidden" name="restaurant_id" value="{restaurant_id}">
                            <button type="submit" class="btn btn-primary">Back to Settings</button>
                        </form>
                    </div>
                </div>
            </div>
            """
        
        # Add new employee
        current_employees.append(employee_name)
        position.employee_names = json.dumps(current_employees)
        db.commit()
        
        return restaurant_settings(restaurant_id, db)
        
    except Exception as e:
        print(f"Add employee error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Adding Employee</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/remove_employee", response_class=HTMLResponse)
def remove_employee(
    restaurant_id: int = Form(...),
    position_id: int = Form(...),
    employee_name: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        position = db.query(TipPosition).filter(TipPosition.id == position_id).first()
        if not position:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Position not found!</h3></div></div></div>"
        
        # Get current employees
        try:
            current_employees = json.loads(position.employee_names) if position.employee_names else []
        except:
            current_employees = []
        
        # Remove employee
        if employee_name in current_employees:
            current_employees.remove(employee_name)
            position.employee_names = json.dumps(current_employees)
            db.commit()
        
        return restaurant_settings(restaurant_id, db)
        
    except Exception as e:
        print(f"Remove employee error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Removing Employee</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
def process_tipout_data_for_export(tipouts, separate_positions=True, include_hours=False):
    """Process tipout data into export-ready format"""
    export_data = []
    
    for tipout in tipouts:
        try:
            # Parse tipout details
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            
            if separate_positions:
                # Create rows for actual tip recipients (the positions getting tips)
                for position_name, position_data in details.items():
                    total_amount = position_data.get('amount', 0.0)
                    per_person = position_data.get('per_person', 0.0)
                    employees_working = position_data.get('employees', [])
                    
                    # Use actual employee names if available
                    if employees_working:
                        for emp_name in employees_working:
                            row = {
                                "employee_name": emp_name,  # Use actual employee name
                                "date": tipout.date,
                                "position": position_name,
                                "tip_amount": per_person,  # Amount each person receives
                                "staff_count": len(employees_working),
                                "per_person": per_person,
                                "shift_start": tipout.start_time,
                                "shift_end": tipout.end_time,
                                "source_server": tipout.server_name,
                                "total_sales": tipout.total_alc_sales + tipout.total_food_sales
                            }
                            
                            if include_hours:
                                try:
                                    start_time = datetime.strptime(tipout.start_time, "%H:%M")
                                    end_time = datetime.strptime(tipout.end_time, "%H:%M")
                                    hours = (end_time - start_time).seconds / 3600
                                    if hours <= 0:
                                        hours += 24
                                    row["hours_worked"] = round(hours, 2)
                                except:
                                    row["hours_worked"] = 0
                            
                            export_data.append(row)
                    else:
                        # Fallback to generic names if no specific employees
                        num_staff = position_data.get('num_staff', 1)
                        for staff_index in range(num_staff):
                            row = {
                                "employee_name": f"{position_name}_{staff_index + 1}",
                                "date": tipout.date,
                                "position": position_name,
                                "tip_amount": per_person,
                                "staff_count": num_staff,
                                "per_person": per_person,
                                "shift_start": tipout.start_time,
                                "shift_end": tipout.end_time,
                                "source_server": tipout.server_name,
                                "total_sales": tipout.total_alc_sales + tipout.total_food_sales
                            }
                            
                            if include_hours:
                                try:
                                    start_time = datetime.strptime(tipout.start_time, "%H:%M")
                                    end_time = datetime.strptime(tipout.end_time, "%H:%M")
                                    hours = (end_time - start_time).seconds / 3600
                                    if hours <= 0:
                                        hours += 24
                                    row["hours_worked"] = round(hours, 2)
                                except:
                                    row["hours_worked"] = 0
                            
                            export_data.append(row)
            else:
                # Single row showing server's total tipout deduction
                total_tipout = sum(pos_data.get('amount', 0) for pos_data in details.values())
                
                row = {
                    "employee_name": tipout.server_name,
                    "date": tipout.date,
                    "position": "Server",
                    "tip_amount": -total_tipout,  # Negative because it's a deduction
                    "staff_count": 1,
                    "per_person": -total_tipout,
                    "shift_start": tipout.start_time,
                    "shift_end": tipout.end_time,
                    "source_server": tipout.server_name,
                    "total_sales": tipout.total_alc_sales + tipout.total_food_sales
                }
                
                if include_hours:
                    try:
                        start_time = datetime.strptime(tipout.start_time, "%H:%M")
                        end_time = datetime.strptime(tipout.end_time, "%H:%M")
                        hours = (end_time - start_time).seconds / 3600
                        if hours <= 0:
                            hours += 24
                        row["hours_worked"] = round(hours, 2)
                    except:
                        row["hours_worked"] = 0
                
                export_data.append(row)
                
        except Exception as e:
            print(f"Error processing tipout {tipout.id}: {e}")
            continue
    
    return export_data

def process_complete_tipout_data_for_export(tipouts, include_servers=True, include_hours=False):
    """Process tipout data with proper consolidation and weekly date ranges"""
    from datetime import datetime, timedelta
    
    # Calculate current week (Monday to Sunday)
    today = datetime.now().date()
    days_since_monday = today.weekday()  # Monday = 0, Sunday = 6
    monday = today - timedelta(days=days_since_monday)
    sunday = monday + timedelta(days=6)
    
    # Dictionary to consolidate entries by employee
    consolidated_data = {}
    
    for tipout in tipouts:
        try:
            # Parse tipout details
            details = json.loads(tipout.tipout_details) if tipout.tipout_details else {}
            
            # Calculate hours worked for this shift
            hours_worked = 0
            if include_hours:
                try:
                    start_time = datetime.strptime(tipout.start_time, "%H:%M")
                    end_time = datetime.strptime(tipout.end_time, "%H:%M")
                    hours = (end_time - start_time).seconds / 3600
                    if hours <= 0:
                        hours += 24
                    hours_worked = round(hours, 2)
                except:
                    hours_worked = 0
            
            # Add server entry (showing tipout as deduction)
            if include_servers:
                total_tipout = sum(pos_data.get('amount', 0) for pos_data in details.values())
                server_name = tipout.server_name
                
                if server_name not in consolidated_data:
                    consolidated_data[server_name] = {
                        "employee_name": server_name,
                        "position": "Server",
                        "tip_amount": 0,
                        "hours_worked": 0,
                        "total_sales": 0,
                        "tips_earned": 0,
                        "shifts": 0,
                        "week_start": monday.strftime("%m/%d/%Y"),
                        "week_end": sunday.strftime("%m/%d/%Y"),
                        "description": "Server tipout deductions"
                    }
                
                # Consolidate server data
                consolidated_data[server_name]["tip_amount"] -= total_tipout  # Negative for deductions
                consolidated_data[server_name]["hours_worked"] += hours_worked
                consolidated_data[server_name]["total_sales"] += (tipout.total_alc_sales + tipout.total_food_sales)
                consolidated_data[server_name]["tips_earned"] += tipout.server_tips
                consolidated_data[server_name]["shifts"] += 1
            
            # Add tip recipient entries
            for position_name, position_data in details.items():
                per_person = position_data.get('per_person', 0.0)
                employees_working = position_data.get('employees', [])
                
                if employees_working:
                    for emp_name in employees_working:
                        if emp_name not in consolidated_data:
                            consolidated_data[emp_name] = {
                                "employee_name": emp_name,
                                "position": position_name,
                                "tip_amount": 0,
                                "hours_worked": 0,
                                "total_sales": 0,  # Tip recipients don't have sales
                                "shifts": 0,
                                "week_start": monday.strftime("%m/%d/%Y"),
                                "week_end": sunday.strftime("%m/%d/%Y"),
                                "description": f"Tips received ({position_name})"
                            }
                        
                        # Consolidate tip recipient data
                        consolidated_data[emp_name]["tip_amount"] += per_person
                        consolidated_data[emp_name]["shifts"] += 1
                        # Note: Tip recipients don't get hours or sales attributed to them
                
                else:
                    # Fallback for positions without named employees
                    num_staff = position_data.get('num_staff', 1)
                    for staff_index in range(num_staff):
                        generic_name = f"{position_name}_{staff_index + 1}"
                        
                        if generic_name not in consolidated_data:
                            consolidated_data[generic_name] = {
                                "employee_name": generic_name,
                                "position": position_name,
                                "tip_amount": 0,
                                "hours_worked": 0,
                                "total_sales": 0,
                                "shifts": 0,
                                "week_start": monday.strftime("%m/%d/%Y"),
                                "week_end": sunday.strftime("%m/%d/%Y"),
                                "description": f"Tips received ({position_name})"
                            }
                        
                        consolidated_data[generic_name]["tip_amount"] += per_person
                        consolidated_data[generic_name]["shifts"] += 1
                
        except Exception as e:
            print(f"Error processing tipout {tipout.id}: {e}")
            continue
    
    # Convert consolidated data to list format
    export_data = []
    for emp_data in consolidated_data.values():
        # Format the final row
        row = {
            "employee_name": emp_data["employee_name"],
            "position": emp_data["position"],
            "tip_amount": round(emp_data["tip_amount"], 2),
            "hours_worked": emp_data["hours_worked"],
            "total_sales": emp_data["total_sales"],
            "shifts_worked": emp_data["shifts"],
            "week_period": f"{emp_data['week_start']} - {emp_data['week_end']}",
            "description": emp_data["description"]
        }
        
        # Add additional fields for servers
        if emp_data["position"] == "Server":
            row["tips_earned"] = emp_data.get("tips_earned", 0)
            row["net_tips"] = emp_data.get("tips_earned", 0) + emp_data["tip_amount"]  # tips earned minus tipouts
        
        export_data.append(row)
    
    return export_data

def generate_csv_export(export_data, payroll_provider, include_summary=True):
    """Generate CSV export based on payroll provider format"""
    output = io.StringIO()
    
    if payroll_provider == "adp":
        # ADP Workforce Now format
        fieldnames = ["Employee_ID", "Employee_Name", "Pay_Code", "Amount", "Date", "Hours"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in export_data:
            # Use week_period if available, otherwise use a default
            date_value = row.get("week_period", "Current Week")
            
            writer.writerow({
                "Employee_ID": row["employee_name"].replace(" ", "").lower(),
                "Employee_Name": row["employee_name"],
                "Pay_Code": "TIPS",
                "Amount": f"{row['tip_amount']:.2f}",
                "Date": date_value,
                "Hours": row.get("hours_worked", 0)
            })
            
    elif payroll_provider == "quickbooks":
        # QuickBooks Payroll format
        fieldnames = ["Employee", "Item", "Rate", "Hours", "Customer:Job", "Service Date"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in export_data:
            # Use week_period if available, otherwise use a default date
            service_date = row.get("week_period", "Current Week")
            
            writer.writerow({
                "Employee": row["employee_name"],
                "Item": "Tips",
                "Rate": f"{row['tip_amount']:.2f}",
                "Hours": row.get("hours_worked", 1),
                "Customer:Job": row["position"],
                "Service Date": service_date
            })
            
    else:
        # Generic CSV format
        fieldnames = ["Employee_Name", "Position", "Week_Period", "Tip_Amount", "Hours_Worked", "Shifts_Worked", "Total_Sales", "Tips_Earned", "Net_Tips", "Description"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in export_data:
            csv_row = {
                "Employee_Name": row["employee_name"],
                "Position": row["position"],
                "Week_Period": row["week_period"],
                "Tip_Amount": f"{row['tip_amount']:.2f}",
                "Hours_Worked": row["hours_worked"],
                "Shifts_Worked": row["shifts_worked"],
                "Total_Sales": f"{row['total_sales']:.2f}" if row["position"] == "Server" else "N/A",
                "Description": row["description"]
            }
            
            # Add server-specific fields (empty for non-servers)
            if row["position"] == "Server":
                csv_row["Tips_Earned"] = f"{row.get('tips_earned', 0):.2f}"
                csv_row["Net_Tips"] = f"{row.get('net_tips', 0):.2f}"
            else:
                csv_row["Tips_Earned"] = "N/A"
                csv_row["Net_Tips"] = "N/A"
            
            writer.writerow(csv_row)
    
    # Add summary if requested
    if include_summary:
        output.write("\n\n# SUMMARY\n")
        total_tips = sum(row["tip_amount"] for row in export_data)
        total_employees = len(set(row["employee_name"] for row in export_data))
        output.write(f"# Total Tips: ${total_tips:.2f}\n")
        output.write(f"# Total Employees: {total_employees}\n")
        output.write(f"# Records: {len(export_data)}\n")
    
    content = output.getvalue().encode('utf-8')
    output.close()
    return content

def generate_excel_export(export_data, payroll_provider, restaurant, start_dt, end_dt, include_summary=True):
    """Generate Excel export with formatting"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payroll Export"
    
    # Header styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    center_alignment = Alignment(horizontal="center")
    
    # Title
    ws.merge_cells("A1:F1")
    ws["A1"] = f"{restaurant.name} - Payroll Export ({start_dt.strftime('%m/%d/%Y')} - {end_dt.strftime('%m/%d/%Y')})"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = center_alignment
    
    # Headers

    headers = ["Employee Name", "Position", "Week Period", "Tip Amount", "Hours Worked", "Shifts", "Total Sales", "Description"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_alignment
    
    # Data rows
    for row_idx, data_row in enumerate(export_data, 4):
        ws.cell(row=row_idx, column=1, value=data_row["employee_name"])
        ws.cell(row=row_idx, column=2, value=data_row["position"])
        ws.cell(row=row_idx, column=3, value=data_row["week_period"])
        ws.cell(row=row_idx, column=4, value=data_row["tip_amount"])
        ws.cell(row=row_idx, column=5, value=data_row["hours_worked"])
        ws.cell(row=row_idx, column=6, value=data_row["shifts_worked"])
        
        # Only show sales for servers
        if data_row["position"] == "Server":
            ws.cell(row=row_idx, column=7, value=data_row["total_sales"])
        else:
            ws.cell(row=row_idx, column=7, value="N/A")
            
        ws.cell(row=row_idx, column=8, value=data_row["description"])
        
        # Format currency columns
        ws.cell(row=row_idx, column=4).number_format = "$#,##0.00"
        if data_row["position"] == "Server":
            ws.cell(row=row_idx, column=7).number_format = "$#,##0.00"
    
    # Summary section
    if include_summary:
        summary_row = len(export_data) + 6
        total_tips = sum(row["tip_amount"] for row in export_data)
        total_employees = len(set(row["employee_name"] for row in export_data))
        
        ws.cell(row=summary_row, column=1, value="SUMMARY").font = Font(bold=True)
        ws.cell(row=summary_row + 1, column=1, value="Total Tips:")
        ws.cell(row=summary_row + 1, column=2, value=total_tips).number_format = "$#,##0.00"
        ws.cell(row=summary_row + 2, column=1, value="Total Employees:")
        ws.cell(row=summary_row + 2, column=2, value=total_employees)
        ws.cell(row=summary_row + 3, column=1, value="Total Records:")
        ws.cell(row=summary_row + 3, column=2, value=len(export_data))
    
    # Auto-adjust column widths
    for col_num in range(1, len(headers) + 1):
        max_length = 0
        column_letter = openpyxl.utils.get_column_letter(col_num)
        
        # Check all cells in this column
        for row_num in range(1, len(export_data) + 10):  # Add some buffer
            try:
                cell = ws.cell(row=row_num, column=col_num)
                if hasattr(cell, 'value') and cell.value is not None:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            except:
                pass
        
        # Set column width
        adjusted_width = min(max(max_length + 2, 10), 50)  # Min 10, max 50
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
@app.post("/employee_management", response_class=HTMLResponse)
def employee_management(restaurant_id: int = Form(...), db: Session = Depends(get_db)):
    """Employee management interface"""
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        employees = db.query(Employee).filter(
            Employee.restaurant_id == restaurant_id,
            Employee.is_active == True
        ).order_by(Employee.first_name, Employee.last_name).all()
        
        employee_rows = []
        for emp in employees:
            full_name = f"{emp.first_name} {emp.last_name}".strip()
            
            roles = []
            if emp.is_server:
                roles.append("Server")
            if emp.is_tip_recipient:
                roles.append("Tip Recipient")
            if emp.is_manager:
                roles.append("Manager")
            
            role_text = ", ".join(roles) if roles else "Staff"
            
            # Truncate email if too long
            email_display = emp.email if emp.email else 'N/A'
            if emp.email and len(emp.email) > 20:
                email_display = emp.email[:17] + "..."

            employee_rows.append(f"""
            <tr>
                <td style="padding: 8px; font-size: 0.85em;">{emp.employee_id}</td>
                <td style="padding: 8px; font-size: 0.85em;"><strong>{full_name}</strong></td>
                <td style="padding: 8px; font-size: 0.85em;">{emp.position_title or 'N/A'}</td>
                <td style="padding: 8px; font-size: 0.85em;">{role_text}</td>
                <td style="padding: 8px; font-size: 0.85em;" title="{emp.email or 'N/A'}">{email_display}</td>
                <td style="padding: 8px; font-size: 0.85em;">{emp.hire_date.strftime('%m/%d/%Y') if emp.hire_date else 'N/A'}</td>
                <td style="padding: 8px; text-align: center;">
                    <div style="display: flex; gap: 4px; justify-content: center;">
                        <button class="btn btn-sm btn-warning" onclick="editEmployee({emp.id})" style="padding: 4px 8px; font-size: 0.8em;">Edit</button>
                        <button class="btn btn-sm btn-danger" onclick="deactivateEmployee({emp.id}, {restaurant_id})" style="padding: 4px 8px; font-size: 0.8em;">Del</button>
                    </div>
                </td>
            </tr>
            """)
        employee_table = "".join(employee_rows) if employee_rows else "<tr><td colspan='7' style='text-align: center; padding: 20px;'>No employees found. Add your first employee below.</td></tr>"
        
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="breadcrumb">
                    <a href="/">Home</a> → <a href="/menu?restaurant_id={restaurant.id}">Dashboard</a> → <a href="/settings?restaurant_id={restaurant.id}">Settings</a> → Employee Management
                </div>
                
                <div class="header">
                    <h2>Employee Management</h2>
                    <p><strong>{restaurant.name}</strong></p>
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value">{len(employees)}</div>
                        <div class="summary-label">Active Employees</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([e for e in employees if e.is_server])}</div>
                        <div class="summary-label">Servers</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([e for e in employees if e.is_tip_recipient])}</div>
                        <div class="summary-label">Tip Recipients</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value">{len([e for e in employees if e.is_manager])}</div>
                        <div class="summary-label">Managers</div>
                    </div>
                </div>
                
                <h3>Current Employees</h3>
                <div style="overflow-x: auto; margin: 20px 0;">
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                    <thead style="background: var(--primary); color: white;">
                        <tr>
                            <th style="padding: 10px; font-size: 0.9em;">ID</th>
                            <th style="padding: 10px; font-size: 0.9em;">Name</th>
                            <th style="padding: 10px; font-size: 0.9em;">Position</th>
                            <th style="padding: 10px; font-size: 0.9em;">Roles</th>
                            <th style="padding: 10px; font-size: 0.9em;">Email</th>
                            <th style="padding: 10px; font-size: 0.9em;">Hire Date</th>
                            <th style="padding: 10px; font-size: 0.9em;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {employee_table}
                    </tbody>
                </table>
                </div>
                
                <div style="text-align: center; margin: 20px 0;">
                    <button id="addEmployeeBtn" class="btn btn-success" onclick="toggleAddEmployeeForm()">+ Add New Employee</button>
                </div>
                
                <div id="addEmployeeForm" class="add-position-form" style="display: none;">
                    <h4>Add New Employee</h4>
                    <form action="/create_employee" method="post">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>First Name:</label>
                                <input type="text" name="first_name" required>
                            </div>
                            <div class="form-group">
                                <label>Last Name:</label>
                                <input type="text" name="last_name" required>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Email:</label>
                                <input type="email" name="email">
                            </div>
                            <div class="form-group">
                                <label>Phone:</label>
                                <input type="tel" name="phone">
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Position Title:</label>
                                <input type="text" name="position_title" placeholder="e.g., Server, Host, Kitchen Staff">
                            </div>
                            <div class="form-group">
                                <label>Hourly Wage:</label>
                                <input type="number" name="wage_rate" step="0.01" min="0" placeholder="15.00">
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Employee Roles:</label>
                            <div style="margin-top: 10px;">
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="is_server" value="true" style="margin-right: 10px;">
                                    Server (can have tipouts calculated)
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="is_tip_recipient" value="true" style="margin-right: 10px;">
                                    Tip Recipient (receives tips from servers)
                                </label>
                                <label style="display: flex; align-items: center; margin-bottom: 10px;">
                                    <input type="checkbox" name="is_manager" value="true" style="margin-right: 10px;">
                                    Manager (can access management features)
                                </label>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Notes:</label>
                            <textarea name="notes" rows="3" placeholder="Additional notes about this employee"></textarea>
                        </div>
                        
                        <div style="text-align: center;">
                            <button type="submit" class="btn btn-primary">Add Employee</button>
                        </div>
                    </form>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <form action="/settings" method="post" style="display: inline;">
                        <input type="hidden" name="restaurant_id" value="{restaurant.id}">
                        <button type="submit" class="btn btn-secondary">Back to Settings</button>
                    </form>
                </div>
            </div>
        </div>
        
        <script>
        function toggleAddEmployeeForm() {{
            const form = document.getElementById('addEmployeeForm');
            const button = document.getElementById('addEmployeeBtn');
            
            if (form.style.display === 'none' || form.style.display === '') {{
                form.style.display = 'block';
                button.textContent = 'Cancel';
                button.className = 'btn btn-light';
            }} else {{
                form.style.display = 'none';
                button.textContent = '+ Add New Employee';
                button.className = 'btn btn-success';
            }}
        }}
        
        function editEmployee(employeeId) {{
            alert('Edit employee functionality coming in next phase!');
        }}
        
        function deactivateEmployee(employeeId, restaurantId) {{
            if (confirm('Are you sure you want to deactivate this employee?')) {{
                fetch('/deactivate_employee', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded',
                    }},
                    body: `employee_id=${{employeeId}}&restaurant_id=${{restaurantId}}`
                }})
                .then(response => response.text())
                .then(html => {{
                    document.body.innerHTML = html;
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Error deactivating employee');
                }});
            }}
        }}
        </script>
        """
        
    except Exception as e:
        print(f"Employee management error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Loading Employee Management</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/create_employee", response_class=HTMLResponse)
def add_employee_to_system(
    restaurant_id: int = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: Optional[str] = Form(""),
    phone: Optional[str] = Form(""),
    position_title: Optional[str] = Form(""),
    wage_rate: Optional[float] = Form(None),
    is_server: Optional[str] = Form(None),
    is_tip_recipient: Optional[str] = Form(None),
    is_manager: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if not restaurant:
            return STYLE + "<div class='container'><div class='card'><div class='error'><h3>Restaurant not found!</h3></div></div></div>"
        
        # Generate employee ID
        employee_count = db.query(Employee).filter(Employee.restaurant_id == restaurant_id).count()
        employee_id = f"EMP{restaurant_id:03d}{employee_count+1:03d}"
        
        # Create new employee
        new_employee = Employee(
            restaurant_id=restaurant_id,
            employee_id=employee_id,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email.strip() if email.strip() else None,
            phone=phone.strip() if phone.strip() else None,
            position_title=position_title.strip() if position_title.strip() else None,
            wage_rate=wage_rate,
            is_server=is_server == "true",
            is_tip_recipient=is_tip_recipient == "true", 
            is_manager=is_manager == "true",
            notes=notes.strip() if notes.strip() else None
        )
        
        db.add(new_employee)
        db.commit()
        
        return employee_management(restaurant_id, db)
        
    except Exception as e:
        print(f"Add employee error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Adding Employee</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """

@app.post("/deactivate_employee", response_class=HTMLResponse)
def deactivate_employee(
    employee_id: int = Form(...),
    restaurant_id: int = Form(...),
    db: Session = Depends(get_db)
):
    try:
        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        if employee:
            employee.is_active = False
            db.commit()
        
        return employee_management(restaurant_id, db)
        
    except Exception as e:
        print(f"Deactivate employee error: {e}")
        return STYLE + f"""
        <div class="container">
            <div class="card">
                <div class="error">
                    <h3>Error Deactivating Employee</h3>
                    <p>{str(e)}</p>
                </div>
            </div>
        </div>
        """
    
@app.get("/debug")
def debug_info(db: Session = Depends(get_db)):
    try:
        restaurants = db.query(Restaurant).all()
        tipouts = db.query(Tipout).all()
        positions = db.query(TipPosition).all()
        
        return {
            "status": "Custom Positions System Working!",
            "restaurants_count": len(restaurants),
            "tipouts_count": len(tipouts),
            "positions_count": len(positions),
            "features": [
                "Custom tip positions management",
                "Add/delete positions in settings",
                "Flexible calculation bases (food/alcohol/total sales)",
                "Position-based tipout calculations",
                "Data migration from old system",
                "Soft delete for positions",
                "Enhanced settings interface"
            ],
            "restaurants": [{"id": r.id, "name": r.name, "toast_connected": bool(r.toast_client_id)} for r in restaurants],
            "positions": [{"restaurant": p.restaurant_id, "name": p.position_name, "percentage": p.percentage, "base": p.calculation_base, "active": p.is_active} for p in positions],
            "database_file": "tipout_management.db"
        }
    except Exception as e:
        return {"error": str(e), "message": "Database connection failed"}

if __name__ == "__main__":
    print("Starting Enhanced Tipout Management Server with Custom Positions...")
    print("Open: http://localhost:8080")
    print("Debug: http://localhost:8080/debug")
    print("Database: tipout_management.db")
    print("\nPhase 1 Features:")
    print("  • Custom tip positions management")
    print("  • Add/delete positions in settings")
    print("  • Flexible calculation bases")
    print("  • Data migration support")
    print("  • Enhanced UI for position management")
    uvicorn.run(app, host="0.0.0.0", port=8080)