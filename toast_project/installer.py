#!/usr/bin/env python3
"""
Tipout Manager Setup Script
Automatically installs all required dependencies and sets up the application
"""

import subprocess
import sys
import os
import platform
from pathlib import Path

def run_command(command, description=""):
    """Run a command and handle errors"""
    print(f"\n{description}")
    print(f"Running: {command}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print("✅ Success!")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required!")
        print("Please upgrade Python and try again.")
        return False
    
    print("✅ Python version is compatible")
    return True

def check_pip():
    """Check if pip is available"""
    try:
        import pip
        print("✅ pip is available")
        return True
    except ImportError:
        print("❌ pip is not available")
        return False

def create_requirements_file():
    """Create requirements.txt file"""
    requirements = """fastapi==0.109.2
uvicorn[standard]==0.27.1
sqlalchemy==2.0.34
httpx==0.27.0
python-multipart==0.0.9
jinja2==3.1.3
python-dotenv==1.0.1"""
    
    with open("requirements.txt", "w") as f:
        f.write(requirements)
    print("✅ Created requirements.txt")

def create_env_file():
    """Create .env file with default settings"""
    env_content = """# Tipout Manager Environment Configuration
DATABASE_URL=sqlite:///./tipout_management.db
HOST=0.0.0.0
PORT=8080
DEBUG=True

# Toast API Configuration (Optional)
TOAST_API_BASE_URL=https://ws-api.toasttab.com
TOAST_TIMEOUT=15

# Application Settings
APP_NAME=Tipout Manager
APP_VERSION=1.0.0"""
    
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write(env_content)
        print("✅ Created .env file")
    else:
        print("✅ .env file already exists")

def install_dependencies():
    """Install all required dependencies"""
    commands = [
        "python -m pip install --upgrade pip",
        "python -m pip install -r requirements.txt"
    ]
    
    for command in commands:
        if not run_command(command, f"Installing dependencies..."):
            return False
    
    return True

def create_startup_script():
    """Create platform-specific startup scripts"""
    
    # Windows batch file
    windows_script = """@echo off
echo Starting Tipout Manager...
python main.py
pause"""
    
    with open("start_windows.bat", "w") as f:
        f.write(windows_script)
    
    # Unix/Linux/Mac shell script
    unix_script = """#!/bin/bash
echo "Starting Tipout Manager..."
python3 main.py"""
    
    with open("start_unix.sh", "w") as f:
        f.write(unix_script)
    
    # Make shell script executable on Unix systems
    if platform.system() != "Windows":
        os.chmod("start_unix.sh", 0o755)
    
    print("✅ Created startup scripts")

def create_project_structure():
    """Create necessary project directories"""
    directories = [
        "data",
        "logs", 
        "backups",
        "exports"
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    
    print("✅ Created project directories")

def create_readme():
    """Create README file with setup instructions"""
    readme_content = """# Tipout Manager

A restaurant tipout management system with custom positions and Toast POS integration.

## Features
- Custom tip positions management
- Toast POS integration
- Daily status tracking
- Tipout calculations
- Weekly reports (coming soon)

## Setup & Installation

### Option 1: Automatic Setup (Recommended)
Run the setup script:
```bash
python setup_tipout_manager.py
```

### Option 2: Manual Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python main.py
   ```

## Usage

1. Open your web browser to: http://localhost:8080
2. Register a new restaurant or login to existing one
3. Configure tip positions in Settings
4. Start calculating tipouts!

## Platform-Specific Startup

### Windows
Double-click `start_windows.bat`

### Mac/Linux
Run `./start_unix.sh` or `python3 main.py`

## Configuration

Edit `.env` file to customize:
- Database location
- Server port
- Toast API settings

## Support

For issues or questions, check the debug endpoint: http://localhost:8080/debug

## Version
1.0.0 - Custom Positions Management
"""
    
    with open("README.md", "w") as f:
        f.write(readme_content)
    print("✅ Created README.md")

def main():
    """Main setup function"""
    print("🚀 Tipout Manager Setup Script")
    print("=" * 50)
    
    # Check system requirements
    if not check_python_version():
        sys.exit(1)
    
    if not check_pip():
        print("Please install pip and try again.")
        sys.exit(1)
    
    print("\n📦 Setting up project files...")
    
    # Create project files
    create_requirements_file()
    create_env_file()
    create_project_structure()
    create_startup_script()
    create_readme()
    
    print("\n📥 Installing dependencies...")
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies!")
        print("You may need to install them manually using:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    
    print("\n✅ Setup completed successfully!")
    print("\n🎉 Next steps:")
    print("1. Make sure main.py is in the same directory")
    print("2. Run: python main.py")
    print("3. Open your browser to: http://localhost:8080")
    print("\nPlatform-specific shortcuts:")
    
    system = platform.system()
    if system == "Windows":
        print("- Windows: Double-click 'start_windows.bat'")
    else:
        print("- Mac/Linux: Run './start_unix.sh'")
    
    print("\n📚 Check README.md for detailed instructions")

if __name__ == "__main__":
    main()