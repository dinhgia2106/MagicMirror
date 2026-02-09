"""
Holiday data service - handles all holiday data operations.
"""

import json
import os
from datetime import datetime, date
from typing import List, Optional, Dict, Any

from models.holiday import Holiday, validate_holiday
from config.settings import HOLIDAYS_FILE, DATA_DIR

# Import lunar calendar for date conversion
try:
    from utils.lunar_calendar import solar_to_lunar, lunar_to_solar, is_giao_thua
    LUNAR_AVAILABLE = True
except ImportError:
    LUNAR_AVAILABLE = False


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
    
    def _compute_holiday_date(self, holiday: Dict[str, Any], year: int) -> Optional[str]:
        """
        Compute the solar date for a holiday in a given year.
        Returns date string in YYYY-MM-DD format or None if cannot compute.
        """
        h_type = holiday.get('type')
        
        if h_type == 'solar':
            # Simple solar date
            month = holiday.get('month')
            day = holiday.get('day')
            if month and day:
                try:
                    d = date(year, month, day)
                    return d.strftime('%Y-%m-%d')
                except ValueError:
                    return None
        
        elif h_type == 'lunar' and LUNAR_AVAILABLE:
            lunar_month = holiday.get('lunarMonth')
            lunar_day = holiday.get('lunarDay')
            
            if lunar_month and lunar_day:
                # Special handling for Giao Thua (month 12, day 30)
                # Some years have only 29 days in month 12
                if lunar_month == 12 and lunar_day == 30:
                    # Check if day 30 exists by converting day 30 and verifying
                    solar_30 = lunar_to_solar(30, 12, year, False)
                    if solar_30 and solar_30['day'] > 0:
                        # Verify it's actually day 30 of month 12
                        verify = solar_to_lunar(solar_30['day'], solar_30['month'], solar_30['year'])
                        if verify['month'] == 12 and verify['day'] == 30:
                            return f"{solar_30['year']:04d}-{solar_30['month']:02d}-{solar_30['day']:02d}"
                    
                    # Day 30 doesn't exist, use day 29 for Giao Thua
                    solar_29 = lunar_to_solar(29, 12, year, False)
                    if solar_29 and solar_29['day'] > 0:
                        return f"{solar_29['year']:04d}-{solar_29['month']:02d}-{solar_29['day']:02d}"
                else:
                    # Normal lunar date conversion
                    solar = lunar_to_solar(lunar_day, lunar_month, year, False)
                    if solar and solar['day'] > 0:
                        return f"{solar['year']:04d}-{solar['month']:02d}-{solar['day']:02d}"
        
        elif h_type == 'specific':
            h_year = holiday.get('year')
            month = holiday.get('month')
            day = holiday.get('day')
            if h_year == year and month and day:
                try:
                    d = date(year, month, day)
                    return d.strftime('%Y-%m-%d')
                except ValueError:
                    return None
        
        return None
    
    def get_all(self, year: int = None) -> List[Dict[str, Any]]:
        """
        Get all holidays as a list of dictionaries.
        For a given solar year, computes dates for all holidays that occur in that year.
        For lunar holidays, checks both the previous lunar year (for Tet in Jan/Feb) 
        and current lunar year.
        """
        if year is None:
            year = datetime.now().year
        
        result = []
        for h in self._holidays.values():
            h_dict = h.to_dict()
            h_type = h_dict.get('type')
            
            if h_type == 'lunar' and LUNAR_AVAILABLE:
                # For lunar holidays, need to check both lunar year-1 and lunar year
                # because Tet (lunar new year) falls in Jan/Feb of solar year
                lunar_years = [year - 1, year]
                for lunar_year in lunar_years:
                    computed_date = self._compute_holiday_date(h_dict, lunar_year)
                    if computed_date:
                        # Check if computed date is in the requested solar year
                        computed_date_obj = datetime.strptime(computed_date, '%Y-%m-%d')
                        if computed_date_obj.year == year:
                            h_dict_copy = h_dict.copy()
                            h_dict_copy['date'] = computed_date
                            result.append(h_dict_copy)
                            break
                else:
                    # No date found for this year, still add without date
                    result.append(h_dict)
            else:
                # Non-lunar holidays
                computed_date = self._compute_holiday_date(h_dict, year)
                if computed_date:
                    h_dict['date'] = computed_date
                result.append(h_dict)
        
        return result
    
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
