import sqlite3

# Connect to your database
conn = sqlite3.connect('tipout_management.db')
cursor = conn.cursor()

try:
    # Check if column exists
    cursor.execute("PRAGMA table_info(tipouts)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'server_employee_id' not in columns:
        print("Adding server_employee_id column...")
        cursor.execute("ALTER TABLE tipouts ADD COLUMN server_employee_id INTEGER")
        conn.commit()
        print("Column added successfully!")
    else:
        print("Column already exists!")
        
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()

print("Database fix complete. You can now restart your server.")