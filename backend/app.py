"""
Holiday Management Backend API for MagicMirror.

Run with: python app.py
API will be available at http://0.0.0.0:8000

Endpoints:
- GET    /api/holidays         - List all holidays
- GET    /api/holidays/:id     - Get single holiday
- POST   /api/holidays         - Create holiday
- PUT    /api/holidays/:id     - Update holiday
- DELETE /api/holidays/:id     - Delete holiday
"""

import sys
import os

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from flask_cors import CORS

from config.settings import HOST, PORT, DEBUG, CORS_ORIGINS
from routes.holidays import holiday_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Enable CORS for all routes
    CORS(app, origins=CORS_ORIGINS)
    
    # Register blueprints
    app.register_blueprint(holiday_bp)
    
    # Health check endpoint
    @app.route('/api/health')
    def health_check():
        return jsonify({
            'status': 'ok',
            'message': 'Holiday API is running'
        })
    
    # Root endpoint
    @app.route('/')
    def index():
        return jsonify({
            'name': 'Holiday Management API',
            'version': '1.0.0',
            'endpoints': {
                'holidays': '/api/holidays',
                'health': '/api/health'
            }
        })
    
    return app


if __name__ == '__main__':
    app = create_app()
    print(f"Starting Holiday API server at http://{HOST}:{PORT}")
    print(f"Press Ctrl+C to stop the server")
    app.run(host=HOST, port=PORT, debug=DEBUG)
