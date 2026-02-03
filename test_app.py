#!/usr/bin/env python3
"""
Minimal test application for Render deployment
"""
import os
import sys
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "LMS Attendance Bot is running!"

@app.route('/health')
def health():
    return {"status": "healthy", "port": os.environ.get('PORT', 'not set')}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    print(f"Starting minimal app on {host}:{port}")
    print(f"Python version: {sys.version}")
    print(f"Environment PORT: {os.environ.get('PORT')}")
    
    app.run(host=host, port=port, debug=False)