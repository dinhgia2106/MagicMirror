#!/usr/bin/env python3
"""
Agent Tools for MMM-LLMsAssistant
Provides tool functions for the LLM agent to access MagicMirror data
"""

import datetime
import json
import requests
from typing import Optional, Dict, Any, List
import pytz  # For timezone handling


class AgentTools:
    """Collection of tools that the agent can use"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        # Backend API URL for holidays
        self.holiday_api_url = self.config.get("holiday_api_url", "http://192.168.1.11:8000/api/holidays")
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
        day_names_vi = ["Thu Hai", "Thu Ba", "Thu Tu", "Thu Nam", "Thu Sau", "Thu Bay", "Chu Nhat"]
        day_name_vi = day_names_vi[now.weekday()]
        
        # Vietnamese month names
        month_names_vi = ["", "Thang Gieng", "Thang Hai", "Thang Ba", "Thang Tu", "Thang Nam", 
                         "Thang Sau", "Thang Bay", "Thang Tam", "Thang Chin", "Thang Muoi", 
                         "Thang Muoi Mot", "Thang Muoi Hai"]
        
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
        Get detailed information about a specific date.
        Args:
            date_str: Date string in format "YYYY-MM-DD" or natural language like "tomorrow", "next week"
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
        day_names_vi = ["Thu Hai", "Thu Ba", "Thu Tu", "Thu Nam", "Thu Sau", "Thu Bay", "Chu Nhat"]
        weekday = target_date.weekday()
        
        return {
            "success": True,
            "data": {
                "date": target_date.strftime("%Y-%m-%d"),
                "day": target_date.day,
                "month": target_date.month,
                "year": target_date.year,
                "day_of_week": target_date.strftime("%A"),
                "day_of_week_vi": day_names_vi[weekday],
                "is_weekend": weekday >= 5,
                "days_from_today": days_diff,
                "relative": "today" if days_diff == 0 else ("in the past" if days_diff < 0 else "in the future"),
                "formatted_vi": f"{day_names_vi[weekday]}, ngay {target_date.day} thang {target_date.month} nam {target_date.year}"
            }
        }
    
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
                    h_date = datetime.datetime.strptime(h.get("date", ""), "%Y-%m-%d")
                    if month and h_date.month != month:
                        continue
                    if year and h_date.year != year:
                        continue
                    filtered.append(h)
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
            {"date": f"{current_year}-01-01", "name": "Tet Duong lich", "type": "public"},
            {"date": f"{current_year}-02-14", "name": "Le tinh nhan", "type": "observance"},
            {"date": f"{current_year}-03-08", "name": "Ngay Quoc te Phu nu", "type": "observance"},
            {"date": f"{current_year}-04-30", "name": "Ngay Thong nhat", "type": "public"},
            {"date": f"{current_year}-05-01", "name": "Ngay Quoc te Lao dong", "type": "public"},
            {"date": f"{current_year}-06-01", "name": "Ngay Quoc te Thieu nhi", "type": "observance"},
            {"date": f"{current_year}-09-02", "name": "Quoc khanh Viet Nam", "type": "public"},
            {"date": f"{current_year}-10-20", "name": "Ngay Phu nu Viet Nam", "type": "observance"},
            {"date": f"{current_year}-11-20", "name": "Ngay Nha giao Viet Nam", "type": "observance"},
            {"date": f"{current_year}-12-25", "name": "Giang sinh", "type": "observance"},
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
        Check if a specific date is a holiday.
        Args:
            date_str: Date in YYYY-MM-DD format
        """
        try:
            check_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"success": False, "error": f"Invalid date format: {date_str}"}
        
        result = self.get_holidays(month=check_date.month, year=check_date.year)
        if not result["success"]:
            return result
        
        matching_holidays = [h for h in result["data"]["holidays"] if h.get("date") == date_str]
        
        return {
            "success": True,
            "data": {
                "date": date_str,
                "is_holiday": len(matching_holidays) > 0,
                "holidays": matching_holidays,
                "is_weekend": check_date.weekday() >= 5
            }
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
                    relative_day = "NGAY MAI (Tomorrow" 
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
            "get_current_weather": self.get_current_weather,
            "get_weather_forecast": self.get_weather_forecast,
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
        "description": "Get detailed information about a specific date including day of week, whether it's weekend, and how many days from today. Supports natural language like 'tomorrow', 'yesterday', 'ngay mai', 'hom qua'.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format or natural language like 'today', 'tomorrow', 'yesterday', 'ngay mai', 'hom qua'"
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
        "description": "Get list of holidays. Can filter by month and/or year. Use this when user asks about holidays, 'ngay le', 'ngay nghi'.",
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
        "description": "Get holidays within the next N days. Use when user asks 'what holidays are coming up', 'ngay le sap toi'.",
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
        "description": "Check if a specific date is a holiday and if it's a weekend.",
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
    }
]


def get_gemini_tools():
    """Get tools in format for Gemini API"""
    return {
        "function_declarations": TOOL_DECLARATIONS
    }


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
