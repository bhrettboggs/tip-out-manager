from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import uvicorn

# Simple test version to debug issues
app = FastAPI()

STYLE = """
<style>
body {
    background: linear-gradient(135deg, #f8ffae 0%, #43c6ac 100%);
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    text-align: center;
}
.container {
    max-width: 600px;
    margin: 0 auto;
    background: white;
    padding: 30px;
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
h1, h2 { color: #2d3e50; }
button {
    background: #43c6ac;
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 5px;
    font-size: 16px;
    cursor: pointer;
    margin: 10px;
}
button:hover { background: #2d3e50; }
input, select {
    padding: 10px;
    margin: 5px;
    border: 1px solid #ddd;
    border-radius: 5px;
    width: 200px;
}
label { display: block; margin: 10px 0 5px 0; font-weight: bold; }
.highlight { color: #e67e22; font-weight: bold; }
</style>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return STYLE + """
    <div class="container">
        <h1>🧪 Tipout Test App</h1>
        <p>If you can see this, FastAPI is working!</p>
        
        <form action="/test_calc" method="get">
            <button type="submit">Test Simple Calculation</button>
        </form>
        
        <form action="/test_form" method="get">
            <button type="submit">Test Form Submission</button>
        </form>
    </div>
    """

@app.get("/test_calc", response_class=HTMLResponse)
def test_calculation():
    # Simple test calculation
    alcohol_sales = 1000
    food_sales = 500
    bartender_percent = 0.75
    assistant_percent = 0.75
    
    bartender_tipout = alcohol_sales * (bartender_percent / 100)
    assistant_tipout = food_sales * (assistant_percent / 100)
    
    return STYLE + f"""
    <div class="container">
        <h1>✅ Calculation Test</h1>
        <p><strong>Alcohol Sales:</strong> <span class="highlight">${alcohol_sales}</span></p>
        <p><strong>Food Sales:</strong> <span class="highlight">${food_sales}</span></p>
        <p><strong>Bartender Tipout (0.75%):</strong> <span class="highlight">${bartender_tipout:.2f}</span></p>
        <p><strong>Assistant Tipout (0.75%):</strong> <span class="highlight">${assistant_tipout:.2f}</span></p>
        <p><strong>Total Tipout:</strong> <span class="highlight">${bartender_tipout + assistant_tipout:.2f}</span></p>
        
        <a href="/"><button>Back Home</button></a>
    </div>
    """

@app.get("/test_form", response_class=HTMLResponse)
def test_form():
    return STYLE + """
    <div class="container">
        <h1>📝 Form Test</h1>
        <form action="/submit_test" method="post">
            <label>Restaurant Name:</label>
            <input type="text" name="restaurant_name" required>
            
            <label>Bartender Percent:</label>
            <input type="number" name="bartender_percent" step="0.01" value="0.75" required>
            
            <label>Server Name:</label>
            <select name="server_name" required>
                <option value="Alice">Alice</option>
                <option value="Bob">Bob</option>
                <option value="Charlie">Charlie</option>
            </select>
            
            <br><br>
            <button type="submit">Submit Test</button>
        </form>
        
        <a href="/"><button>Back Home</button></a>
    </div>
    """

@app.post("/submit_test", response_class=HTMLResponse)
def submit_test(
    restaurant_name: str = Form(...),
    bartender_percent: float = Form(...),
    server_name: str = Form(...)
):
    return STYLE + f"""
    <div class="container">
        <h1>✅ Form Submission Success!</h1>
        <p><strong>Restaurant:</strong> <span class="highlight">{restaurant_name}</span></p>
        <p><strong>Bartender %:</strong> <span class="highlight">{bartender_percent}%</span></p>
        <p><strong>Server:</strong> <span class="highlight">{server_name}</span></p>
        
        <a href="/"><button>Back Home</button></a>
    </div>
    """

@app.get("/debug")
def debug_info():
    """Debug endpoint to check if the server is running"""
    return {
        "status": "Server is running!",
        "message": "If you see this, the API is working",
        "endpoints": [
            "GET /",
            "GET /test_calc", 
            "GET /test_form",
            "POST /submit_test",
            "GET /debug"
        ]
    }

if __name__ == "__main__":
    print("🚀 Starting Simple Test Server...")
    print("📱 Open your browser to: http://localhost:8000")
    print("🔍 Debug endpoint: http://localhost:8000/debug")
    uvicorn.run(app, host="0.0.0.0", port=8000)