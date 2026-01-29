"""
Holiday data service - handles all holiday data operations.
"""

import json
import os
from typing import List, Optional, Dict, Any

from models.holiday import Holiday, validate_holiday
from config.settings import HOLIDAYS_FILE, DATA_DIR


class HolidayService:
    """Service for managing holiday data."""
    
    def __init__(self):
        self._ensure_data_dir()
        self._holidays: Dict[str, Holiday] = {}
        self._load_holidays()
    
    def _ensure_data_dir(self):
        """Ensure the data directory exists."""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
    
    def _load_holidays(self):
        """Load holidays from JSON file."""
        if os.path.exists(HOLIDAYS_FILE):
            try:
                with open(HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    holidays_list = data.get('holidays', [])
                    self._holidays = {
                        h['id']: Holiday.from_dict(h) 
                        for h in holidays_list
                    }
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading holidays: {e}")
                self._holidays = {}
        else:
            self._holidays = {}
    
    def _save_holidays(self):
        """Save holidays to JSON file."""
        try:
            holidays_list = [h.to_dict() for h in self._holidays.values()]
            with open(HOLIDAYS_FILE, 'w', encoding='utf-8') as f:
                json.dump({'holidays': holidays_list}, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving holidays: {e}")
            raise
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all holidays as a list of dictionaries."""
        return [h.to_dict() for h in self._holidays.values()]
    
    def get_by_id(self, holiday_id: str) -> Optional[Dict[str, Any]]:
        """Get a holiday by ID."""
        holiday = self._holidays.get(holiday_id)
        return holiday.to_dict() if holiday else None
    
    def create(self, data: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
        """
        Create a new holiday.
        Returns (holiday_dict, error_message).
        """
        # Validate
        is_valid, error = validate_holiday(data)
        if not is_valid:
            return None, error
        
        # Generate ID if not provided
        if not data.get('id'):
            data['id'] = Holiday.generate_id()
        
        # Check for duplicate ID
        if data['id'] in self._holidays:
            data['id'] = Holiday.generate_id()
        
        holiday = Holiday.from_dict(data)
        self._holidays[holiday.id] = holiday
        self._save_holidays()
        
        return holiday.to_dict(), ''
    
    def update(self, holiday_id: str, data: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
        """
        Update an existing holiday.
        Returns (holiday_dict, error_message).
        """
        if holiday_id not in self._holidays:
            return None, 'Holiday not found'
        
        # Merge with existing data
        existing = self._holidays[holiday_id].to_dict()
        merged = {**existing, **data, 'id': holiday_id}
        
        # Validate
        is_valid, error = validate_holiday(merged)
        if not is_valid:
            return None, error
        
        holiday = Holiday.from_dict(merged)
        self._holidays[holiday_id] = holiday
        self._save_holidays()
        
        return holiday.to_dict(), ''
    
    def delete(self, holiday_id: str) -> tuple[bool, str]:
        """
        Delete a holiday.
        Returns (success, error_message).
        """
        if holiday_id not in self._holidays:
            return False, 'Holiday not found'
        
        del self._holidays[holiday_id]
        self._save_holidays()
        
        return True, ''
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search holidays by name."""
        query_lower = query.lower()
        results = []
        for holiday in self._holidays.values():
            if (query_lower in holiday.name.lower() or 
                (holiday.nameVi and query_lower in holiday.nameVi.lower())):
                results.append(holiday.to_dict())
        return results


# Singleton instance
_service_instance: Optional[HolidayService] = None


def get_holiday_service() -> HolidayService:
    """Get the holiday service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HolidayService()
    return _service_instance
