#!/usr/bin/env python3
"""
Agent Tools for MMM-LLMsAssistant
Provides tool functions for the LLM agent to access MagicMirror data
"""

import datetime
import json
import os
import requests
from typing import Optional, Dict, Any, List
from memory_manager import MemoryManager
import pytz  # For timezone handling

# Import lunar calendar for Vietnamese lunar date conversion
try:
    from lunar_calendar import (
        solar_to_lunar, lunar_to_solar, 
        get_lunar_month_name, get_year_can_chi, get_day_can_chi,
        check_lunar_holiday, LUNAR_HOLIDAYS
    )
    LUNAR_AVAILABLE = True
except ImportError:
    LUNAR_AVAILABLE = False


class AgentTools:
    """Collection of tools that the agent can use"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Initialize memory manager
        soul_path = config.get("soul_path") if config else None
        if not soul_path:
            soul_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soul.md")
        self.memory = MemoryManager(soul_path)
        
        # Backend API URL for holidays
        self.holiday_api_url = self.config.get("holiday_api_url", "http://127.0.0.1:8000/api/holidays")
        # OpenMeteo API for weather
        self.weather_lat = self.config.get("lat", 16.463713)
        self.weather_lon = self.config.get("lon", 107.590866)
        # Timezone
        self.timezone = pytz.timezone(self.config.get("timezone", "Asia/Ho_Chi_Minh"))
    
    # ==================== DATE/TIME TOOLS ====================
    
    def get_current_datetime(self) -> Dict[str, Any]:
        """
        Get the current date and time with detailed information.
        Returns current datetime, day of week, week number, and formatted strings.
        """
        now = datetime.datetime.now(self.timezone)
        
        # Vietnamese day names
        day_names_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        day_name_vi = day_names_vi[now.weekday()]
        
        # Vietnamese month names
        month_names_vi = ["", "Tháng Một", "Tháng Hai", "Tháng Ba", "Tháng Tư", "Tháng Năm", 
                         "Tháng Sáu", "Tháng Bảy", "Tháng Tám", "Tháng Chín", "Tháng Mười", 
                         "Tháng Mười Một", "Tháng Mười Hai"]
        
        return {
            "success": True,
            "data": {
                "datetime_iso": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "time_12h": now.strftime("%I:%M %p"),
                "day": now.day,
                "month": now.month,
                "year": now.year,
                "day_of_week": now.strftime("%A"),
                "day_of_week_vi": day_name_vi,
                "month_name_vi": month_names_vi[now.month],
                "week_number": now.isocalendar()[1],
                "day_of_year": now.timetuple().tm_yday,
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "formatted_vi": f"{day_name_vi}, ngay {now.day} thang {now.month} nam {now.year}",
                "formatted_time_vi": f"{now.hour} gio {now.minute} phut",
                "timezone": str(self.timezone)
            }
        }
    
    def get_date_info(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed information about a specific date including LUNAR CALENDAR info.
        This is the PRIMARY tool for answering questions about dates.
        
        Args:
            date_str: Date string in format "YYYY-MM-DD" or natural language like "tomorrow", "ngay mai"
        
        Returns:
            Solar date info, lunar date info, and any holidays (both solar and lunar)
        """
        now = datetime.datetime.now(self.timezone)
        
        if date_str is None or date_str.lower() == "today" or date_str.lower() == "hom nay":
            target_date = now.date()
        elif date_str.lower() == "tomorrow" or date_str.lower() == "ngay mai":
            target_date = (now + datetime.timedelta(days=1)).date()
        elif date_str.lower() == "yesterday" or date_str.lower() == "hom qua":
            target_date = (now - datetime.timedelta(days=1)).date()
        else:
            try:
                target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return {"success": False, "error": f"Invalid date format: {date_str}. Use YYYY-MM-DD format."}
        
        # Calculate days difference
        days_diff = (target_date - now.date()).days
        
        # Vietnamese day names
        day_names_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        weekday = target_date.weekday()
        
        result = {
            "success": True,
            "data": {
                "solar": {
                    "date": target_date.strftime("%Y-%m-%d"),
                    "day": target_date.day,
                    "month": target_date.month,
                    "year": target_date.year,
                    "day_of_week": target_date.strftime("%A"),
                    "day_of_week_vi": day_names_vi[weekday],
                    "is_weekend": weekday >= 5,
                },
                "days_from_today": days_diff,
                "relative": "today" if days_diff == 0 else ("in the past" if days_diff < 0 else "in the future"),
                "formatted_vi": f"{day_names_vi[weekday]}, ngay {target_date.day} thang {target_date.month} nam {target_date.year}",
                "holidays": []
            }
        }
        
        # Add lunar calendar info if available
        if LUNAR_AVAILABLE:
            lunar = solar_to_lunar(target_date.day, target_date.month, target_date.year)
            lunar_month_name = get_lunar_month_name(lunar['month'], lunar['leap'])
            
            result["data"]["lunar"] = {
                "day": lunar['day'],
                "month": lunar['month'],
                "year": lunar['year'],
                "leap": lunar['leap'],
                "month_name": lunar_month_name,
                "can_chi_year": get_year_can_chi(lunar['year']),
                "can_chi_day": get_day_can_chi(lunar['jd']),
                "formatted_vi": f"Ngay {lunar['day']} {lunar_month_name} nam {get_year_can_chi(lunar['year'])}"
            }
            
            # Check for lunar holidays (pass solar date for Giao Thua detection)
            lunar_holiday = check_lunar_holiday(lunar['day'], lunar['month'], target_date.day, target_date.month, target_date.year)
            if lunar_holiday:
                result["data"]["holidays"].append({
                    "name": lunar_holiday['name'],
                    "nameVi": lunar_holiday['nameVi'],
                    "type": "lunar",
                    "lunar_date": f"{lunar['day']}/{lunar['month']}"
                })
        
        # Check for solar holidays from API (don't use check_holiday to avoid duplicating lunar holidays)
        try:
            api_result = self.get_holidays(month=target_date.month, year=target_date.year)
            if api_result.get("success"):
                date_str = target_date.strftime("%Y-%m-%d")
                for h in api_result["data"].get("holidays", []):
                    if h.get("date") == date_str:
                        # Avoid duplicating lunar holidays (already added above)
                        if h.get("type") != "lunar":
                            result["data"]["holidays"].append({
                                "name": h.get("name"),
                                "nameVi": h.get("nameVi", h.get("name")),
                                "type": h.get("type", "solar")
                            })
        except Exception:
            pass  # API unavailable, lunar holidays already checked
        
        return result
    
    def calculate_date_difference(self, date1: str, date2: str) -> Dict[str, Any]:
        """
        Calculate the difference between two dates.
        Args:
            date1: First date in YYYY-MM-DD format
            date2: Second date in YYYY-MM-DD format
        """
        try:
            d1 = datetime.datetime.strptime(date1, "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(date2, "%Y-%m-%d").date()
            diff = d2 - d1
            
            return {
                "success": True,
                "data": {
                    "date1": date1,
                    "date2": date2,
                    "days_difference": diff.days,
                    "weeks_difference": diff.days // 7,
                    "months_approx": diff.days // 30,
                    "direction": "same" if diff.days == 0 else ("forward" if diff.days > 0 else "backward")
                }
            }
        except ValueError as e:
            return {"success": False, "error": f"Invalid date format: {str(e)}"}
    
    # ==================== HOLIDAY/CALENDAR TOOLS ====================
    
    def get_holidays(self, month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Get holidays from the backend API.
        Args:
            month: Optional month (1-12) to filter holidays
            year: Optional year to filter holidays
        """
        try:
            response = requests.get(self.holiday_api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            holidays = data.get("data", [])
            
            # Filter by month and year if specified
            if month or year:
                filtered = []
                for h in holidays:
                    date_str = h.get("date", "")
                    if not date_str:
                        # Skip holidays without date (lunar holidays are handled separately)
                        continue
                    try:
                        h_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        if month and h_date.month != month:
                            continue
                        if year and h_date.year != year:
                            continue
                        filtered.append(h)
                    except ValueError:
                        continue
                holidays = filtered
            
            return {
                "success": True,
                "data": {
                    "holidays": holidays,
                    "count": len(holidays),
                    "filter": {"month": month, "year": year}
                }
            }
        except requests.RequestException as e:
            # Fall back to built-in Vietnamese holidays
            return self._get_builtin_holidays(month, year)
    
    def _get_builtin_holidays(self, month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
        """Fallback built-in Vietnamese holidays"""
        now = datetime.datetime.now(self.timezone)
        current_year = year or now.year
        
        # Major Vietnamese holidays (fixed dates)
        holidays = [
            {"date": f"{current_year}-01-01", "name": "Tết Dương lịch", "type": "public"},
            {"date": f"{current_year}-02-14", "name": "Lễ tình nhân", "type": "observance"},
            {"date": f"{current_year}-03-08", "name": "Ngày Quốc tế Phụ nữ", "type": "observance"},
            {"date": f"{current_year}-04-30", "name": "Ngày Thống nhất", "type": "public"},
            {"date": f"{current_year}-05-01", "name": "Ngày Quốc tế Lao động", "type": "public"},
            {"date": f"{current_year}-06-01", "name": "Ngày Quốc tế Thiếu nhi", "type": "observance"},
            {"date": f"{current_year}-09-02", "name": "Quốc khánh Việt Nam", "type": "public"},
            {"date": f"{current_year}-10-20", "name": "Ngày Phụ nữ Việt Nam", "type": "observance"},
            {"date": f"{current_year}-11-20", "name": "Ngày Nhà giáo Việt Nam", "type": "observance"},
            {"date": f"{current_year}-12-25", "name": "Giáng sinh", "type": "observance"},
        ]
        
        if month:
            holidays = [h for h in holidays if datetime.datetime.strptime(h["date"], "%Y-%m-%d").month == month]
        
        return {
            "success": True,
            "data": {
                "holidays": holidays,
                "count": len(holidays),
                "source": "builtin",
                "note": "Using built-in holiday list (backend unavailable)"
            }
        }
    
    def get_upcoming_holidays(self, days: int = 30) -> Dict[str, Any]:
        """
        Get holidays within the next N days.
        Args:
            days: Number of days to look ahead (default: 30)
        """
        now = datetime.datetime.now(self.timezone).date()
        end_date = now + datetime.timedelta(days=days)
        
        result = self.get_holidays()
        if not result["success"]:
            return result
        
        upcoming = []
        for h in result["data"]["holidays"]:
            try:
                h_date = datetime.datetime.strptime(h["date"], "%Y-%m-%d").date()
                if now <= h_date <= end_date:
                    days_until = (h_date - now).days
                    h["days_until"] = days_until
                    upcoming.append(h)
            except (ValueError, KeyError):
                continue
        
        # Sort by date
        upcoming.sort(key=lambda x: x["date"])
        
        return {
            "success": True,
            "data": {
                "holidays": upcoming,
                "count": len(upcoming),
                "date_range": {"from": str(now), "to": str(end_date)},
                "days_ahead": days
            }
        }
    
    def check_holiday(self, date_str: str) -> Dict[str, Any]:
        """
        Check if a specific date is a holiday (both solar AND lunar holidays).
        This checks:
        1. Solar holidays from the backend API
        2. Lunar holidays by converting to lunar date and checking
        
        Args:
            date_str: Date in YYYY-MM-DD format (solar/Gregorian date)
        """
        try:
            check_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"success": False, "error": f"Invalid date format: {date_str}"}
        
        matching_holidays = []
        
        # Check lunar holidays first if available
        if LUNAR_AVAILABLE:
            lunar = solar_to_lunar(check_date.day, check_date.month, check_date.year)
            lunar_holiday = check_lunar_holiday(lunar['day'], lunar['month'], check_date.day, check_date.month, check_date.year)
            if lunar_holiday:
                matching_holidays.append({
                    "name": lunar_holiday['name'],
                    "nameVi": lunar_holiday['nameVi'],
                    "type": "lunar",
                    "lunar_day": lunar['day'],
                    "lunar_month": lunar['month'],
                    "date": date_str
                })
        
        # Check solar holidays from API
        result = self.get_holidays(month=check_date.month, year=check_date.year)
        if result["success"]:
            for h in result["data"]["holidays"]:
                if h.get("date") == date_str:
                    matching_holidays.append(h)
        
        return {
            "success": True,
            "data": {
                "date": date_str,
                "is_holiday": len(matching_holidays) > 0,
                "holidays": matching_holidays,
                "is_weekend": check_date.weekday() >= 5
            }
        }
    
    def find_holiday(self, holiday_name: str, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Find a holiday by name and return its solar date.
        Use this when user asks about a specific holiday like 'Giao thua', 'Tet', 'Trung Thu'.
        
        Args:
            holiday_name: Name of the holiday to find (e.g., 'Giao thua', 'Tet', 'Mung 1')
            year: Year to search in (defaults to current year)
        """
        if year is None:
            year = datetime.datetime.now(self.timezone).year
        
        # Normalize search term
        search_lower = holiday_name.lower().strip()
        
        # Common Vietnamese holiday name mappings
        name_mappings = {
            'tet': ['tet day 1', 'mung 1', 'tet nguyen dan'],
            'giao thua': ['giao thua', 'giao thừa', 'dem giao thua'],
            'trung thu': ['mid-autumn', 'trung thu'],
            'vu lan': ['vu lan', 'le vu lan'],
            'ong cong': ['kitchen gods', 'ong cong ong tao', 'táo quân'],
            'hung vuong': ['hung kings', 'gio to hung vuong'],
            'doan ngo': ['doan ngo', 'tet doan ngo'],
        }
        
        # Expand search terms
        search_terms = [search_lower]
        for key, aliases in name_mappings.items():
            if any(alias in search_lower or search_lower in alias for alias in aliases + [key]):
                search_terms.extend(aliases)
                search_terms.append(key)
        
        # Get holidays from API
        try:
            response = requests.get(f"{self.holiday_api_url}?year={year}", timeout=10)
            response.raise_for_status()
            data = response.json()
            holidays = data.get("data", [])
        except requests.RequestException:
            holidays = []
        
        # Also check built-in lunar holidays
        if LUNAR_AVAILABLE:
            lunar_holiday_map = {
                'giao thua': {'lunar_day': 29, 'lunar_month': 12, 'name': 'Giao Thua', 'nameVi': 'Giao thừa'},
                'mung 1': {'lunar_day': 1, 'lunar_month': 1, 'name': 'Tet Day 1', 'nameVi': 'Mùng 1 Tết'},
                'tet': {'lunar_day': 1, 'lunar_month': 1, 'name': 'Tet Day 1', 'nameVi': 'Mùng 1 Tết'},
                'trung thu': {'lunar_day': 15, 'lunar_month': 8, 'name': 'Mid-Autumn Festival', 'nameVi': 'Tết Trung Thu'},
                'vu lan': {'lunar_day': 15, 'lunar_month': 7, 'name': 'Vu Lan Festival', 'nameVi': 'Lễ Vu Lan'},
                'ong cong': {'lunar_day': 23, 'lunar_month': 12, 'name': 'Kitchen Gods Day', 'nameVi': 'Ông Công Ông Táo'},
            }
            
            for term in search_terms:
                if term in lunar_holiday_map:
                    h = lunar_holiday_map[term]
                    # Special handling for Giao Thua
                    if term == 'giao thua':
                        # Check which lunar year we need (year-1 for Tet in Jan/Feb)
                        for lunar_year in [year - 1, year]:
                            solar_30 = lunar_to_solar(30, 12, lunar_year, False)
                            if solar_30 and solar_30['day'] > 0:
                                verify = solar_to_lunar(solar_30['day'], solar_30['month'], solar_30['year'])
                                if verify['month'] == 12 and verify['day'] == 30:
                                    if solar_30['year'] == year:
                                        return {
                                            "success": True,
                                            "data": {
                                                "name": h['name'],
                                                "nameVi": h['nameVi'],
                                                "date": f"{solar_30['year']:04d}-{solar_30['month']:02d}-{solar_30['day']:02d}",
                                                "lunar_date": f"30/12 âm lịch năm {lunar_year}",
                                                "day_of_week": datetime.date(solar_30['year'], solar_30['month'], solar_30['day']).strftime('%A'),
                                                "type": "lunar"
                                            }
                                        }
                            # Try day 29
                            solar_29 = lunar_to_solar(29, 12, lunar_year, False)
                            if solar_29 and solar_29['day'] > 0 and solar_29['year'] == year:
                                return {
                                    "success": True,
                                    "data": {
                                        "name": h['name'],
                                        "nameVi": h['nameVi'],
                                        "date": f"{solar_29['year']:04d}-{solar_29['month']:02d}-{solar_29['day']:02d}",
                                        "lunar_date": f"29/12 âm lịch năm {lunar_year}",
                                        "day_of_week": datetime.date(solar_29['year'], solar_29['month'], solar_29['day']).strftime('%A'),
                                        "type": "lunar"
                                    }
                                }
                    else:
                        # Normal lunar holiday
                        for lunar_year in [year - 1, year]:
                            solar = lunar_to_solar(h['lunar_day'], h['lunar_month'], lunar_year, False)
                            if solar and solar['day'] > 0 and solar['year'] == year:
                                return {
                                    "success": True,
                                    "data": {
                                        "name": h['name'],
                                        "nameVi": h['nameVi'],
                                        "date": f"{solar['year']:04d}-{solar['month']:02d}-{solar['day']:02d}",
                                        "lunar_date": f"{h['lunar_day']}/{h['lunar_month']} âm lịch",
                                        "day_of_week": datetime.date(solar['year'], solar['month'], solar['day']).strftime('%A'),
                                        "type": "lunar"
                                    }
                                }
        
        # Search in API results
        for h in holidays:
            name = h.get('name', '').lower()
            name_vi = h.get('nameVi', '').lower()
            if any(term in name or term in name_vi or name in term or name_vi in term for term in search_terms):
                if h.get('date'):
                    date_obj = datetime.datetime.strptime(h['date'], '%Y-%m-%d')
                    return {
                        "success": True,
                        "data": {
                            "name": h.get('name'),
                            "nameVi": h.get('nameVi'),
                            "date": h['date'],
                            "day_of_week": date_obj.strftime('%A'),
                            "type": h.get('type', 'unknown')
                        }
                    }
        
        return {
            "success": False,
            "error": f"Holiday '{holiday_name}' not found for year {year}"
        }
    
    # ==================== WEATHER TOOLS ====================
    
    def get_current_weather(self) -> Dict[str, Any]:
        """
        Get current weather information from OpenMeteo API.
        Returns temperature, humidity, wind speed, and weather condition.
        """
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": self.weather_lat,
                "longitude": self.weather_lon,
                "current": [
                    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
                    "weather_code", "wind_speed_10m", "wind_direction_10m",
                    "precipitation", "rain", "cloud_cover"
                ],
                "timezone": "Asia/Ho_Chi_Minh"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current", {})
            
            # Weather code to description mapping
            weather_descriptions = {
                0: "Troi quang",
                1: "Chu yeu quang",
                2: "Co may mot phan",
                3: "Am u",
                45: "Suong mu",
                48: "Suong mu dong bang",
                51: "Mua phun nhe",
                53: "Mua phun vua",
                55: "Mua phun nang",
                61: "Mua nhe",
                63: "Mua vua",
                65: "Mua to",
                71: "Tuyet nhe",
                73: "Tuyet vua",
                75: "Tuyet day",
                77: "Hat tuyet",
                80: "Mua rao nhe",
                81: "Mua rao vua",
                82: "Mua rao manh",
                85: "Mua tuyet nhe",
                86: "Mua tuyet nang",
                95: "Giong bao",
                96: "Giong bao va mua da nhe",
                99: "Giong bao va mua da manh"
            }
            
            weather_code = current.get("weather_code", 0)
            description = weather_descriptions.get(weather_code, "Khong xac dinh")
            
            return {
                "success": True,
                "data": {
                    "temperature": current.get("temperature_2m"),
                    "temperature_unit": "°C",
                    "feels_like": current.get("apparent_temperature"),
                    "humidity": current.get("relative_humidity_2m"),
                    "humidity_unit": "%",
                    "wind_speed": current.get("wind_speed_10m"),
                    "wind_unit": "km/h",
                    "wind_direction": current.get("wind_direction_10m"),
                    "precipitation": current.get("precipitation"),
                    "rain": current.get("rain"),
                    "cloud_cover": current.get("cloud_cover"),
                    "weather_code": weather_code,
                    "description": description,
                    "location": {
                        "lat": self.weather_lat,
                        "lon": self.weather_lon
                    },
                    "formatted_vi": f"Nhiet do {current.get('temperature_2m')}°C, {description.lower()}, do am {current.get('relative_humidity_2m')}%"
                }
            }
        except requests.RequestException as e:
            return {"success": False, "error": f"Weather API error: {str(e)}"}
    
    def get_weather_forecast(self, days: int = 3) -> Dict[str, Any]:
        """
        Get weather forecast for the next N days.
        Args:
            days: Number of days to forecast (1-7)
        """
        # Convert to int in case Gemini passes a float
        days = int(min(max(days, 1), 7))  # Limit between 1 and 7
        
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": self.weather_lat,
                "longitude": self.weather_lon,
                "daily": [
                    "temperature_2m_max", "temperature_2m_min",
                    "weather_code", "precipitation_sum", "precipitation_probability_max",
                    "wind_speed_10m_max"
                ],
                "timezone": "Asia/Ho_Chi_Minh",
                "forecast_days": 7  # Always get 7 days to cover tomorrow/next week even if LLM asks for 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            
            # Weather code to description
            weather_descriptions = {
                0: "Troi quang", 1: "Chu yeu quang", 2: "Co may", 3: "Am u",
                45: "Suong mu", 48: "Suong mu", 
                51: "Mua phun", 53: "Mua phun", 55: "Mua phun",
                61: "Mua", 63: "Mua", 65: "Mua to",
                80: "Mua rao", 81: "Mua rao", 82: "Mua to",
                95: "Giong bao", 96: "Giong bao", 99: "Giong bao"
            }
            
            forecasts = []
            dates = daily.get("time", [])
            
            # Calculate today in correct timezone for relative date comparison
            today = datetime.datetime.now(self.timezone).date()
            
            for i in range(len(dates)):
                # Calculate relative day description
                forecast_date = datetime.datetime.strptime(dates[i], "%Y-%m-%d").date()
                diff_days = (forecast_date - today).days
                
                relative_day = ""
                if diff_days == 0:
                    relative_day = "HOM NAY (Today)"
                elif diff_days == 1:
                    relative_day = "NGAY MAI (Tomorrow)" 
                elif diff_days == 2:
                    relative_day = "NGAY KIA"
                else:
                    relative_day = f"Sau {diff_days} ngay"

                weather_code = daily.get("weather_code", [])[i] if i < len(daily.get("weather_code", [])) else 0
                forecasts.append({
                    "relative_day": relative_day,
                    "date": dates[i],
                    "temp_max": daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else None,
                    "temp_min": daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else None,
                    "weather_code": weather_code,
                    "description": weather_descriptions.get(weather_code, "Khong xac dinh"),
                    "precipitation_sum": daily.get("precipitation_sum", [])[i] if i < len(daily.get("precipitation_sum", [])) else None,
                    "precipitation_probability": daily.get("precipitation_probability_max", [])[i] if i < len(daily.get("precipitation_probability_max", [])) else None,
                    "wind_speed_max": daily.get("wind_speed_10m_max", [])[i] if i < len(daily.get("wind_speed_10m_max", [])) else None
                })
            
            return {
                "success": True,
                "data": {
                    "forecasts": forecasts,
                    "days": len(forecasts),
                    "location": {"lat": self.weather_lat, "lon": self.weather_lon}
                }
            }
        except requests.RequestException as e:
            return {"success": False, "error": f"Weather API error: {str(e)}"}
    
    # ==================== MUSIC CONTROL TOOLS ====================
    
    def music_play(self) -> Dict[str, Any]:
        """
        Play music - send play command to MMM-SoundCloud module.
        """
        return {
            "success": True,
            "action": "MUSIC_PLAY",
            "data": {"command": "play"},
            "message": "Đã phát nhạc"
        }
    
    def music_pause(self) -> Dict[str, Any]:
        """
        Pause music - send pause command to MMM-SoundCloud module.
        """
        return {
            "success": True,
            "action": "MUSIC_PAUSE", 
            "data": {"command": "pause"},
            "message": "Đã tạm dừng nhạc"
        }
    
    def music_next(self) -> Dict[str, Any]:
        """
        Play next track - send next command to MMM-SoundCloud module.
        """
        return {
            "success": True,
            "action": "MUSIC_NEXT",
            "data": {"command": "next"},
            "message": "Đã chuyển sang bài tiếp theo"
        }
    
    def music_prev(self) -> Dict[str, Any]:
        """
        Play previous track - send prev command to MMM-SoundCloud module.
        """
        return {
            "success": True,
            "action": "MUSIC_PREV",
            "data": {"command": "prev"},
            "message": "Đã quay lại bài trước"
        }
    
    def music_volume(self, level: int) -> Dict[str, Any]:
        """
        Set music volume.
        Args:
            level: Volume level (0-100)
        """
        level = max(0, min(100, level))
        return {
            "success": True,
            "action": "MUSIC_SET_VOLUME",
            "data": {"volume": level},
            "message": f"Đã đặt âm lượng {level}%"
        }
    
    def music_adjust_volume(self, adjustment_type: str, amount: float = 10) -> Dict[str, Any]:
        """
        Adjust music volume relatively (increase/decrease by amount or multiply).
        Args:
            adjustment_type: Type of adjustment:
                - 'increase': Increase volume by amount%
                - 'decrease': Decrease volume by amount%
                - 'multiply': Multiply volume by amount (e.g., 2 for double, 0.5 for half)
                - 'increase_little': Increase by 5% (ignores amount)
                - 'decrease_little': Decrease by 5% (ignores amount)
                - 'increase_lot': Increase by 20% (ignores amount)
                - 'decrease_lot': Decrease by 20% (ignores amount)
            amount: Amount to adjust (percentage for increase/decrease, multiplier for multiply)
        """
        return {
            "success": True,
            "action": "MUSIC_ADJUST_VOLUME",
            "data": {"adjustment_type": adjustment_type, "amount": amount},
            "message": f"Đang điều chỉnh âm lượng ({adjustment_type}, {amount})"
        }
    
    def music_search_play(self, song_name: str) -> Dict[str, Any]:
        """
        Search for a song by name and play it.
        After the song finishes, playback will return to the previous position.
        Args:
            song_name: Name or part of the song name to search for
        """
        if not song_name or not song_name.strip():
            return {
                "success": False,
                "error": "Vui lòng cung cấp tên bài hát"
            }
        
        return {
            "success": True,
            "action": "MUSIC_SEARCH_PLAY",
            "data": {"song_name": song_name.strip()},
            "message": f"Đang tìm và phát bài hát: {song_name}"
        }
    
    def music_play_mood(self, mood: str) -> Dict[str, Any]:
        """
        Play music by mood, genre, theme or random.
        Switches to Global mode for continuous auto-play of related tracks.
        Args:
            mood: Mood, genre, theme or description of music style.
                  Examples: 'buồn', 'vui', 'chill', 'tết', 'random', 'jazz', 'lofi',
                  'nhạc buồn', 'nhạc sôi động', 'workout music', 'sleep music'
        """
        if not mood or not mood.strip():
            return {
                "success": False,
                "error": "Vui lòng mô tả thể loại hoặc tâm trạng nhạc"
            }
        
        return {
            "success": True,
            "action": "MUSIC_PLAY_MOOD",
            "data": {"mood": mood.strip()},
            "message": f"Đang tìm và phát nhạc theo chủ đề: {mood}"
        }
    
    # ==================== MEMORY TOOLS ====================
    
    def memory_save(self, section: str, content: str) -> Dict[str, Any]:
        """
        Save a new memory to persistent storage (soul.md).
        Use this to remember user preferences, facts, names, or important information.
        Args:
            section: Section to save to. Options: 'user profile', 'learned facts', 'conversation notes'
            content: The memory content to save (e.g., 'User's name is Minh', 'User likes coffee')
        """
        result = self.memory.add_memory(section, content)
        return {
            "success": result["status"] == "success" or result["status"] == "exists",
            "message": result["message"]
        }
    
    def memory_list(self, section: str = None) -> Dict[str, Any]:
        """
        List all stored memories, optionally filtered by section.
        Use this when user asks 'what do you know about me?' or 'what do you remember?'
        Args:
            section: Optional section to filter ('user profile', 'learned facts', 'conversation notes')
        """
        result = self.memory.list_memories(section)
        if result["status"] == "success":
            return {
                "success": True,
                "memories": result["memories"]
            }
        return {"success": False, "error": result.get("message", "Unknown error")}
    
    def memory_remove(self, section: str, content: str) -> Dict[str, Any]:
        """
        Remove a memory from persistent storage.
        Use when user says to forget something or correct outdated info.
        Args:
            section: Section to remove from ('user profile', 'learned facts', 'conversation notes')
            content: The memory content to remove (partial match supported)
        """
        result = self.memory.remove_memory(section, content)
        return {
            "success": result["status"] == "success",
            "message": result["message"]
        }
    
    # ==================== UTILITY METHODS ====================
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a tool by name with given arguments.
        Args:
            tool_name: Name of the tool to execute
            arguments: Dictionary of arguments for the tool
        """
        arguments = arguments or {}
        
        tool_map = {
            "get_current_datetime": self.get_current_datetime,
            "get_date_info": self.get_date_info,
            "calculate_date_difference": self.calculate_date_difference,
            "get_holidays": self.get_holidays,
            "get_upcoming_holidays": self.get_upcoming_holidays,
            "check_holiday": self.check_holiday,
            "find_holiday": self.find_holiday,
            "get_current_weather": self.get_current_weather,
            "get_weather_forecast": self.get_weather_forecast,
            # Music control tools
            "music_play": self.music_play,
            "music_pause": self.music_pause,
            "music_next": self.music_next,
            "music_prev": self.music_prev,
            "music_volume": self.music_volume,
            "music_adjust_volume": self.music_adjust_volume,
            "music_search_play": self.music_search_play,
            "music_play_mood": self.music_play_mood,
            # Memory tools
            "memory_save": self.memory_save,
            "memory_list": self.memory_list,
            "memory_remove": self.memory_remove,
        }
        
        if tool_name not in tool_map:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            return tool_map[tool_name](**arguments)
        except TypeError as e:
            return {"success": False, "error": f"Invalid arguments for {tool_name}: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Tool execution error: {str(e)}"}


# Tool definitions for Gemini Function Calling
TOOL_DECLARATIONS = [
    {
        "name": "get_current_datetime",
        "description": "Get the current date and time with detailed information including day of week, week number, and Vietnamese formatted strings. Use this when user asks about current time, date, or 'what time is it', 'what day is today'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_date_info",
        "description": "IMPORTANT: This is the PRIMARY tool for answering 'what day is it', 'ngay mai ngay gi', 'hom nay ngay am gi'. Returns BOTH solar (Gregorian) and LUNAR (am lich) calendar info plus any holidays. Use for: tomorrow, yesterday, ngay mai, hom qua, ngay am, lich am, Tet, Ong Cong Ong Tao, Ram, etc. Returns lunar date (ngay am), Can Chi, and matching lunar holidays like Tet, Vu Lan, Trung Thu, Ong Cong Ong Tao.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format or natural language: 'today', 'tomorrow', 'yesterday', 'ngay mai', 'hom qua', 'hom nay'"
                }
            },
            "required": []
        }
    },
    {
        "name": "calculate_date_difference",
        "description": "Calculate the difference between two dates in days, weeks, and approximate months.",
        "parameters": {
            "type": "object",
            "properties": {
                "date1": {
                    "type": "string",
                    "description": "First date in YYYY-MM-DD format"
                },
                "date2": {
                    "type": "string",
                    "description": "Second date in YYYY-MM-DD format"
                }
            },
            "required": ["date1", "date2"]
        }
    },
    {
        "name": "get_holidays",
        "description": "Get list of holidays from database. Use get_date_info instead if you need to check holidays for a specific date (it includes lunar holidays). This is for listing all holidays in a month/year.",
        "parameters": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "integer",
                    "description": "Month (1-12) to filter holidays"
                },
                "year": {
                    "type": "integer",
                    "description": "Year to filter holidays"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_upcoming_holidays",
        "description": "Get holidays within the next N days. For checking a specific date, use get_date_info instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead (default: 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "check_holiday",
        "description": "Check if a specific date is a holiday (checks BOTH solar and lunar holidays). Requires date in YYYY-MM-DD format. For natural language dates like 'tomorrow', use get_date_info instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format"
                }
            },
            "required": ["date_str"]
        }
    },
    {
        "name": "find_holiday",
        "description": "Find a specific holiday by name and get its solar/Gregorian date. Use this when user asks 'when is Giao thua?', 'Tet is what date?', 'ngay giao thua la ngay may duong', 'Trung Thu nam nay', etc. Returns the exact solar date for holidays like Giao Thua, Tet, Trung Thu, Vu Lan, Ong Cong Ong Tao.",
        "parameters": {
            "type": "object",
            "properties": {
                "holiday_name": {
                    "type": "string",
                    "description": "Name of the holiday to find (e.g., 'Giao thua', 'Tet', 'Trung Thu', 'Vu Lan', 'Ong Cong')"
                },
                "year": {
                    "type": "integer",
                    "description": "Year to search in (optional, defaults to current year)"
                }
            },
            "required": ["holiday_name"]
        }
    },
    {
        "name": "get_current_weather",
        "description": "Get current weather information including temperature, humidity, wind, and conditions. Use when user asks about 'weather now', 'thoi tiet', 'nhiet do'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_weather_forecast",
        "description": "Get weather forecast for the next 1-7 days. IMPORTANT: This returns a LIST of daily forecasts. You MUST look at the 'date' field in each item to find the specific day the user asked for (e.g. tomorrow). Do not just take the first item.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to forecast (1-7, default: 3)"
                }
            },
            "required": []
        }
    },
    # Music control tools
    {
        "name": "music_play",
        "description": "Bật nhạc, phát nhạc, mở nhạc. Use when user says 'bật nhạc', 'phát nhạc', 'play music', 'mở nhạc', 'chơi nhạc'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "music_pause",
        "description": "Tạm dừng nhạc, pause. Use when user says 'dừng lại', 'tạm dừng', 'pause', 'tắt nhạc', 'ngừng nhạc', 'stop music'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "music_next",
        "description": "Chuyển sang bài tiếp theo. Use when user says 'bài tiếp', 'next', 'bài khác', 'chuyển bài', 'skip'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "music_prev",
        "description": "Quay lại bài trước. Use when user says 'bài trước', 'previous', 'quay lại', 'lui lại'.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "music_volume",
        "description": "Đặt âm lượng nhạc ở mức cố định (absolute). Sử dụng khi user nói 'đặt âm lượng 50%', 'volume 80%', 'âm lượng 30'. Chỉ dùng khi user nói rõ MỨC cụ thể.",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level from 0 to 100"
                }
            },
            "required": ["level"]
        }
    },
    {
        "name": "music_adjust_volume",
        "description": "Điều chỉnh âm lượng tương đối (relative). Sử dụng khi user muốn TĂNG hoặc GIẢM theo định lượng, không phải đặt mức cố định. Ví dụ: 'tăng âm lượng', 'giảm 10%', 'to hơn', 'nhỏ hơn', 'giảm 1 xíu', 'tăng gấp đôi', 'giảm còn một nửa'.",
        "parameters": {
            "type": "object",
            "properties": {
                "adjustment_type": {
                    "type": "string",
                    "enum": ["increase", "decrease", "multiply", "increase_little", "decrease_little", "increase_lot", "decrease_lot"],
                    "description": "Type: 'increase'/'decrease' (by amount%), 'multiply' (gấp đôi=2, một nửa=0.5), 'increase_little'/'decrease_little' (1 xíu/1 chút), 'increase_lot'/'decrease_lot' (nhiều)"
                },
                "amount": {
                    "type": "number",
                    "description": "Amount to adjust: percentage for increase/decrease (default 10), multiplier for multiply (2=double, 0.5=half)"
                }
            },
            "required": ["adjustment_type"]
        }
    },
    {
        "name": "music_search_play",
        "description": "Tìm kiếm và phát một bài hát theo tên. Sau khi bài hát kết thúc sẽ quay lại bài đang phát trước đó. Use when user says 'phát bài', 'bật bài', 'mở bài', 'tìm bài', 'nghe bài', 'play song', 'search song', followed by a song name. Example: 'phát bài Em của ngày hôm qua', 'bật bài Chạy ngay đi'.",
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {
                    "type": "string",
                    "description": "Name or part of the song name to search for"
                }
            },
            "required": ["song_name"]
        }
    },
    {
        "name": "music_play_mood",
        "description": "Phát nhạc theo tâm trạng, thể loại hoặc chủ đề. Tự động chuyển sang chế độ Global để phát liên tục các bài liên quan. Sử dụng khi user muốn nghe nhạc theo mood/genre/theme mà KHÔNG chỉ định tên bài cụ thể. Ví dụ: 'phát nhạc buồn', 'mở nhạc chill', 'bật nhạc tết', 'phát nhạc ngẫu nhiên', 'play some jazz', 'nhạc để ngủ', 'nhạc tập gym', 'nhạc sôi động'. KHÔNG dùng tool này khi user nói tên bài hát cụ thể (dùng music_search_play thay vì).",
        "parameters": {
            "type": "object",
            "properties": {
                "mood": {
                    "type": "string",
                    "description": "Mood, genre, theme or description. Examples: 'buồn', 'vui', 'chill', 'tết', 'random', 'jazz', 'lofi', 'workout', 'sleep', 'sôi động', 'lãng mạn'"
                }
            },
            "required": ["mood"]
        }
    },
    # Memory tools
    {
        "name": "memory_save",
        "description": "Save a memory about the user or an important fact to persistent local storage (soul.md). Use this PROACTIVELY when user reveals personal info (name, age, preferences, hobbies), states opinions or facts worth remembering. Examples: user says 'My name is Minh' -> save to 'user profile'; user says 'I have a meeting tomorrow at 9' -> save to 'conversation notes'; user teaches you something -> save to 'learned facts'.",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["user profile", "learned facts", "conversation notes"],
                    "description": "Section to save to: 'user profile' for user info/preferences, 'learned facts' for knowledge, 'conversation notes' for reminders"
                },
                "content": {
                    "type": "string",
                    "description": "The memory content to save, written as a clear factual statement"
                }
            },
            "required": ["section", "content"]
        }
    },
    {
        "name": "memory_list",
        "description": "List all stored memories from persistent storage. Use when user asks 'what do you know about me?', 'what do you remember?', 'ban nho gi ve toi?', 'ban biet gi ve toi?'.",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["user profile", "learned facts", "conversation notes"],
                    "description": "Optional: filter by section"
                }
            },
            "required": []
        }
    },
    {
        "name": "memory_remove",
        "description": "Remove a memory from persistent storage. Use when user says 'forget that', 'that's wrong', 'xoa di', 'quen di', or corrects previous info.",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["user profile", "learned facts", "conversation notes"],
                    "description": "Section to remove from"
                },
                "content": {
                    "type": "string",
                    "description": "The memory content to remove (partial match supported)"
                }
            },
            "required": ["section", "content"]
        }
    }
]


def get_gemini_tools():
    """Get tools in format for new Google GenAI SDK"""
    from google.genai import types
    
    declarations = []
    for decl in TOOL_DECLARATIONS:
        declarations.append(
            types.FunctionDeclaration(
                name=decl["name"],
                description=decl["description"],
                parameters=decl["parameters"]
            )
        )
    
    return types.Tool(function_declarations=declarations)


if __name__ == "__main__":
    # Test the tools
    tools = AgentTools()
    
    print("=== Testing get_current_datetime ===")
    print(json.dumps(tools.get_current_datetime(), indent=2, ensure_ascii=False))
    
    print("\n=== Testing get_date_info (tomorrow) ===")
    print(json.dumps(tools.get_date_info("tomorrow"), indent=2, ensure_ascii=False))
    
    print("\n=== Testing get_holidays ===")
    print(json.dumps(tools.get_holidays(month=9), indent=2, ensure_ascii=False))
    
    print("\n=== Testing get_current_weather ===")
    print(json.dumps(tools.get_current_weather(), indent=2, ensure_ascii=False))
    
    print("\n=== Testing get_weather_forecast ===")
    print(json.dumps(tools.get_weather_forecast(3), indent=2, ensure_ascii=False))
