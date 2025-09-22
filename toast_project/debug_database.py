# debug_database.py
import os
import sqlite3

print("🔍 Database Diagnostic Tool")
print("=" * 50)

# Check if database file exists
db_file = "tipout_management.db"
if os.path.exists(db_file):
    print(f"✅ Database file found: {db_file}")
    file_size = os.path.getsize(db_file)
    print(f"📏 File size: {file_size} bytes")
else:
    print(f"❌ Database file not found: {db_file}")
    print("🔧 Will create new database")

# Connect and inspect database
try:
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"\n📊 Tables found: {[table[0] for table in tables]}")
    
    # Check restaurants table structure
    if ('restaurants',) in tables:
        cursor.execute("PRAGMA table_info(restaurants);")
        columns = cursor.fetchall()
        print("\n🏪 Restaurants table columns:")
        for col in columns:
            print(f"   {col[1]} ({col[2]})")
        
        # Check if problematic columns exist
        column_names = [col[1] for col in columns]
        required_columns = ['toast_client_id', 'toast_client_secret', 'toast_restaurant_guid', 'toast_management_group_guid']
        missing_columns = [col for col in required_columns if col not in column_names]
        
        if missing_columns:
            print(f"\n❌ Missing columns: {missing_columns}")
            print("🔧 Need to recreate database")
        else:
            print("\n✅ All required columns present")
    
    # Check tipouts table structure  
    if ('tipouts',) in tables:
        cursor.execute("PRAGMA table_info(tipouts);")
        columns = cursor.fetchall()
        print("\n💰 Tipouts table columns:")
        for col in columns:
            print(f"   {col[1]} ({col[2]})")
    
    conn.close()

except Exception as e:
    print(f"❌ Database error: {e}")

print("\n" + "=" * 50)
print("🔧 FIXING DATABASE...")

# Force delete and recreate
try:
    if os.path.exists(db_file):
        os.remove(db_file)
        print("🗑️ Old database deleted")
    
    # Create new database with correct structure
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Create restaurants table with ALL required columns
    cursor.execute('''
    CREATE TABLE restaurants (
        id INTEGER PRIMARY KEY,
        name VARCHAR UNIQUE NOT NULL,
        toast_client_id VARCHAR,
        toast_client_secret VARCHAR,
        toast_restaurant_guid VARCHAR,
        toast_management_group_guid VARCHAR,
        bartender_percent FLOAT NOT NULL,
        assistant_percent FLOAT NOT NULL,
        server_names VARCHAR NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create tipouts table
    cursor.execute('''
    CREATE TABLE tipouts (
        id INTEGER PRIMARY KEY,
        restaurant_id INTEGER,
        server_name VARCHAR NOT NULL,
        date VARCHAR NOT NULL,
        start_time VARCHAR NOT NULL,
        end_time VARCHAR NOT NULL,
        num_assistants INTEGER NOT NULL,
        total_alc_sales FLOAT NOT NULL DEFAULT 0.0,
        total_food_sales FLOAT NOT NULL DEFAULT 0.0,
        time_based_food_sales FLOAT NOT NULL DEFAULT 0.0,
        server_tips FLOAT NOT NULL,
        bartender_tipout FLOAT NOT NULL,
        assistant_tipout FLOAT NOT NULL,
        assistant_per_person FLOAT NOT NULL,
        toast_sync BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (restaurant_id) REFERENCES restaurants (id)
    )
    ''')
    
    conn.commit()
    
    # Verify tables were created
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"✅ Tables created: {[table[0] for table in tables]}")
    
    # Verify restaurants table structure
    cursor.execute("PRAGMA table_info(restaurants);")
    columns = cursor.fetchall()
    print("✅ Restaurants table columns:")
    for col in columns:
        print(f"   {col[1]} ({col[2]})")
    
    conn.close()
    print("🎉 Database recreated successfully!")
    
except Exception as e:
    print(f"❌ Error recreating database: {e}")

print("\n🚀 Now try starting your app again:")
print("uvicorn main:app --host 0.0.0.0 --port 8080")