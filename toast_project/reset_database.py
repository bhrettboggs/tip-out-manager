# reset_database.py
import os
import sqlite3
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from datetime import datetime
import json

# Remove old database if it exists
if os.path.exists("tipout_management.db"):
    os.remove("tipout_management.db")
    print("🗑️ Old database deleted")

# Create new database with correct schema
DATABASE_URL = "sqlite:///./tipout_management.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()

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
    server_names = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

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

# Create all tables
try:
    Base.metadata.create_all(bind=engine)
    print("✅ New database created successfully!")
    print("📊 Tables created: restaurants, tipouts")
    
    # Test database connection
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    # Add a test restaurant
    test_restaurant = Restaurant(
        name="Test Restaurant",
        bartender_percent=0.75,
        assistant_percent=0.75,
        server_names=json.dumps(["Alice", "Bob", "Charlie"])
    )
    
    db.add(test_restaurant)
    db.commit()
    print("🧪 Test restaurant added successfully!")
    
    db.close()
    print("🎉 Database reset complete! You can now start the main app.")
    
except Exception as e:
    print(f"❌ Error creating database: {e}")