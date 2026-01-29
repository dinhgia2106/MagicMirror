"""
Holiday API routes.
"""

from flask import Blueprint, request, jsonify
from services.holiday_service import get_holiday_service


# Create blueprint
holiday_bp = Blueprint('holidays', __name__, url_prefix='/api/holidays')


@holiday_bp.route('', methods=['GET'])
def get_holidays():
    """Get all holidays or search by query."""
    service = get_holiday_service()
    
    # Check for search query
    query = request.args.get('q', '').strip()
    if query:
        holidays = service.search(query)
    else:
        holidays = service.get_all()
    
    return jsonify({
        'success': True,
        'data': holidays,
        'count': len(holidays)
    })


@holiday_bp.route('/<holiday_id>', methods=['GET'])
def get_holiday(holiday_id: str):
    """Get a specific holiday by ID."""
    service = get_holiday_service()
    holiday = service.get_by_id(holiday_id)
    
    if not holiday:
        return jsonify({
            'success': False,
            'error': 'Holiday not found'
        }), 404
    
    return jsonify({
        'success': True,
        'data': holiday
    })


@holiday_bp.route('', methods=['POST'])
def create_holiday():
    """Create a new holiday."""
    service = get_holiday_service()
    
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'No data provided'
        }), 400
    
    holiday, error = service.create(data)
    
    if error:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    return jsonify({
        'success': True,
        'data': holiday,
        'message': 'Holiday created successfully'
    }), 201


@holiday_bp.route('/<holiday_id>', methods=['PUT'])
def update_holiday(holiday_id: str):
    """Update an existing holiday."""
    service = get_holiday_service()
    
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'No data provided'
        }), 400
    
    holiday, error = service.update(holiday_id, data)
    
    if error:
        status = 404 if error == 'Holiday not found' else 400
        return jsonify({
            'success': False,
            'error': error
        }), status
    
    return jsonify({
        'success': True,
        'data': holiday,
        'message': 'Holiday updated successfully'
    })


@holiday_bp.route('/<holiday_id>', methods=['DELETE'])
def delete_holiday(holiday_id: str):
    """Delete a holiday."""
    service = get_holiday_service()
    
    success, error = service.delete(holiday_id)
    
    if not success:
        return jsonify({
            'success': False,
            'error': error
        }), 404
    
    return jsonify({
        'success': True,
        'message': 'Holiday deleted successfully'
    })
