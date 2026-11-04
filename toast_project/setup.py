from setuptools import setup, find_packages

setup(
    name="tipout-manager",
    version="1.0.0",
    description="Restaurant Tipout Management System with Custom Positions",
    author="Bhrett Boggs",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.109.2",
        "uvicorn[standard]>=0.27.1",
        "sqlalchemy>=2.0.34",
        "httpx>=0.27.0",
        "python-multipart>=0.0.9",
        "jinja2>=3.1.3",
        "python-dotenv>=1.0.1",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)