#!/usr/bin/env python3
"""
Vietnamese Lunar Calendar Library
Python port of lunar.js - based on Ho Ngoc Duc's algorithm
Optimized for Vietnam timezone (GMT+7)

Reference: https://www.informatik.uni-leipzig.de/~duc/amlich/
"""

import math
from typing import Dict, Any, Optional, Tuple

# Constants
PI = math.pi
TIMEZONE = 7  # Vietnam GMT+7


def jd_from_date(dd: int, mm: int, yy: int) -> int:
    """
    Calculate Julian Day Number from Solar date
    Using the standard astronomical formula
    """
    a = (14 - mm) // 12
    y = yy + 4800 - a
    m = mm + 12 * a - 3
    jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jd


def jd_to_date(jd: float) -> Dict[str, int]:
    """
    Convert Julian Day Number to Solar date
    """
    Z = int(jd + 0.5)
    F = jd + 0.5 - Z
    
    if Z < 2299161:
        a = Z
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        a = Z + 1 + alpha - alpha // 4
    
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    
    day = b - d - int(30.6001 * e) + F
    
    if e < 14:
        m = e - 1
    else:
        m = e - 13
    
    if m > 2:
        y = c - 4716
    else:
        y = c - 4715
    
    return {"day": int(day), "month": m, "year": y}


def get_new_moon_day(k: int, time_zone: int) -> int:
    """
    Calculate Julian Day of the k-th New Moon after J2000
    Formula from "Astronomical Algorithms" by Jean Meeus
    """
    T = k / 1236.85
    T2 = T * T
    T3 = T2 * T
    dr = PI / 180

    Jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * T2 - 0.000000155 * T3
    Jd1 = Jd1 + 0.00033 * math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr)

    M = 359.2242 + 29.10535608 * k - 0.0000333 * T2 - 0.00000347 * T3
    Mpr = 306.0253 + 385.81691806 * k + 0.0107306 * T2 + 0.00001236 * T3
    F = 21.2964 + 390.67050646 * k - 0.0016528 * T2 - 0.00000239 * T3

    C1 = (0.1734 - 0.000393 * T) * math.sin(M * dr) + 0.0021 * math.sin(2 * dr * M)
    C1 = C1 - 0.4068 * math.sin(Mpr * dr) + 0.0161 * math.sin(dr * 2 * Mpr)
    C1 = C1 - 0.0004 * math.sin(dr * 3 * Mpr)
    C1 = C1 + 0.0104 * math.sin(dr * 2 * F) - 0.0051 * math.sin(dr * (M + Mpr))
    C1 = C1 - 0.0074 * math.sin(dr * (M - Mpr)) + 0.0004 * math.sin(dr * (2 * F + M))
    C1 = C1 - 0.0004 * math.sin(dr * (2 * F - M)) - 0.0006 * math.sin(dr * (2 * F + Mpr))
    C1 = C1 + 0.0010 * math.sin(dr * (2 * F - Mpr)) + 0.0005 * math.sin(dr * (2 * Mpr + M))

    if T < -11:
        deltat = 0.001 + 0.000839 * T + 0.0002261 * T2 - 0.00000845 * T3 - 0.000000081 * T * T3
        JdNew = Jd1 + C1 - deltat
    else:
        JdNew = Jd1 + C1

    return int(JdNew + 0.5 + time_zone / 24)


def get_sun_longitude(jdn: float, time_zone: int) -> float:
    """
    Calculate Sun's longitude at a given Julian Day
    Returns value in radians
    """
    T = (jdn - 0.5 - time_zone / 24 - 2451545.0) / 36525
    T2 = T * T
    dr = PI / 180

    M = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2
    L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2
    DL = (1.914600 - 0.004817 * T - 0.000014 * T2) * math.sin(dr * M)
    DL = DL + (0.019993 - 0.000101 * T) * math.sin(dr * 2 * M) + 0.000290 * math.sin(dr * 3 * M)
    L = L0 + DL

    L = L * dr
    L = L - PI * 2 * math.floor(L / (PI * 2))
    return L


def get_sun_longitude_index(jdn: float, time_zone: int) -> int:
    """
    Get Sun longitude at noon on a given Julian Day
    Returns the "Major Solar Term" index (0-11)
    Each major term is 30 degrees apart
    """
    sun_long = get_sun_longitude(jdn, time_zone) / PI * 6
    return int(sun_long)


def get_lunar_month_11(yy: int, time_zone: int) -> int:
    """
    Find the day of the Lunar Month 11 of a given year
    Month 11 is the month containing the Winter Solstice
    """
    off = jd_from_date(31, 12, yy) - 2415021
    k = int(off / 29.530588853)
    nm = get_new_moon_day(k, time_zone)
    sun_long = get_sun_longitude_index(nm, time_zone)

    if sun_long >= 9:
        nm = get_new_moon_day(k - 1, time_zone)
    return nm


def get_leap_month_offset(a11: int, time_zone: int) -> int:
    """
    Find the index of the leap month after month 11
    A leap month is a month without a major solar term
    """
    k = int((a11 - 2415021.076998695) / 29.530588853 + 0.5)
    last = 0
    i = 1
    arc = get_sun_longitude_index(get_new_moon_day(k + i, time_zone), time_zone)

    while arc != last and i < 14:
        last = arc
        i += 1
        arc = get_sun_longitude_index(get_new_moon_day(k + i, time_zone), time_zone)

    return i - 1


def solar_to_lunar(dd: int, mm: int, yy: int, time_zone: int = TIMEZONE) -> Dict[str, Any]:
    """
    Convert Solar date to Lunar date
    Main conversion function
    
    Args:
        dd: Solar day (1-31)
        mm: Solar month (1-12) 
        yy: Solar year
        time_zone: Timezone offset (default: 7 for Vietnam)
    
    Returns:
        Dictionary with: day, month, year, leap, jd
    """
    day_number = jd_from_date(dd, mm, yy)
    k = int((day_number - 2415021.076998695) / 29.530588853)
    month_start = get_new_moon_day(k + 1, time_zone)

    if month_start > day_number:
        month_start = get_new_moon_day(k, time_zone)

    a11 = get_lunar_month_11(yy, time_zone)
    b11 = a11

    if a11 >= month_start:
        lunar_year = yy
        a11 = get_lunar_month_11(yy - 1, time_zone)
    else:
        lunar_year = yy + 1
        b11 = get_lunar_month_11(yy + 1, time_zone)

    lunar_day = day_number - month_start + 1
    diff = (month_start - a11) // 29
    lunar_leap = False
    lunar_month = diff + 11

    if b11 - a11 > 365:
        leap_month_diff = get_leap_month_offset(a11, time_zone)
        if diff >= leap_month_diff:
            lunar_month = diff + 10
            if diff == leap_month_diff:
                lunar_leap = True

    if lunar_month > 12:
        lunar_month = lunar_month - 12
    if lunar_month >= 11 and diff < 4:
        lunar_year -= 1

    return {
        "day": lunar_day,
        "month": lunar_month,
        "year": lunar_year,
        "leap": lunar_leap,
        "jd": day_number
    }


def lunar_to_solar(lunar_day: int, lunar_month: int, lunar_year: int, 
                   lunar_leap: bool = False, time_zone: int = TIMEZONE) -> Dict[str, int]:
    """
    Convert Lunar date to Solar date
    
    Args:
        lunar_day: Lunar day
        lunar_month: Lunar month
        lunar_year: Lunar year
        lunar_leap: Is leap month?
        time_zone: Timezone offset (default: 7 for Vietnam)
    
    Returns:
        Dictionary with: day, month, year
    """
    if lunar_month < 11:
        a11 = get_lunar_month_11(lunar_year - 1, time_zone)
        b11 = get_lunar_month_11(lunar_year, time_zone)
    else:
        a11 = get_lunar_month_11(lunar_year, time_zone)
        b11 = get_lunar_month_11(lunar_year + 1, time_zone)

    k = int(0.5 + (a11 - 2415021.076998695) / 29.530588853)
    off = lunar_month - 11
    if off < 0:
        off += 12

    if b11 - a11 > 365:
        leap_off = get_leap_month_offset(a11, time_zone)
        leap_month = leap_off - 2
        if leap_month < 0:
            leap_month += 12
        if lunar_leap and lunar_month != leap_month:
            return {"day": 0, "month": 0, "year": 0}  # Invalid
        elif lunar_leap or off >= leap_off:
            off += 1

    month_start = get_new_moon_day(k + off, time_zone)
    return jd_to_date(month_start + lunar_day - 1)


def get_year_can_chi(lunar_year: int) -> str:
    """Get the Can Chi (Heavenly Stem + Earthly Branch) for a year"""
    CAN = ['Giap', 'At', 'Binh', 'Dinh', 'Mau', 'Ky', 'Canh', 'Tan', 'Nham', 'Quy']
    CHI = ['Ty', 'Suu', 'Dan', 'Mao', 'Thin', 'Ty', 'Ngo', 'Mui', 'Than', 'Dau', 'Tuat', 'Hoi']
    can = CAN[(lunar_year + 6) % 10]
    chi = CHI[(lunar_year + 8) % 12]
    return f"{can} {chi}"


def get_day_can_chi(jd: int) -> str:
    """Get the day's Can Chi"""
    CAN = ['Giap', 'At', 'Binh', 'Dinh', 'Mau', 'Ky', 'Canh', 'Tan', 'Nham', 'Quy']
    CHI = ['Ty', 'Suu', 'Dan', 'Mao', 'Thin', 'Ty', 'Ngo', 'Mui', 'Than', 'Dau', 'Tuat', 'Hoi']
    can = CAN[(jd + 9) % 10]
    chi = CHI[(jd + 1) % 12]
    return f"{can} {chi}"


def get_lunar_month_name(month: int, leap: bool = False) -> str:
    """Get Vietnamese name for lunar month"""
    MONTH_NAMES = [
        "", "Thang Gieng", "Thang Hai", "Thang Ba", "Thang Tu",
        "Thang Nam", "Thang Sau", "Thang Bay", "Thang Tam",
        "Thang Chin", "Thang Muoi", "Thang Muoi Mot", "Thang Chap"
    ]
    name = MONTH_NAMES[month] if 1 <= month <= 12 else f"Thang {month}"
    if leap:
        name = f"{name} (nhuan)"
    return name


# Fixed lunar holidays
LUNAR_HOLIDAYS = [
    {"day": 30, "month": 12, "name": "Giao thua", "nameVi": "Giao thua"},
    {"day": 1, "month": 1, "name": "Tet Day 1", "nameVi": "Mung 1 Tet"},
    {"day": 2, "month": 1, "name": "Tet Day 2", "nameVi": "Mung 2 Tet"},
    {"day": 3, "month": 1, "name": "Tet Day 3", "nameVi": "Mung 3 Tet"},
    {"day": 15, "month": 1, "name": "Lantern Festival", "nameVi": "Ram thang Gieng"},
    {"day": 10, "month": 3, "name": "Hung Kings Festival", "nameVi": "Gio To Hung Vuong"},
    {"day": 5, "month": 5, "name": "Doan Ngo Festival", "nameVi": "Tet Doan Ngo"},
    {"day": 15, "month": 7, "name": "Vu Lan Festival", "nameVi": "Le Vu Lan"},
    {"day": 15, "month": 8, "name": "Mid-Autumn Festival", "nameVi": "Tet Trung Thu"},
    {"day": 23, "month": 12, "name": "Kitchen Gods Day", "nameVi": "Ong Cong Ong Tao"},
]


def check_lunar_holiday(lunar_day: int, lunar_month: int) -> Optional[Dict[str, str]]:
    """
    Check if a lunar date matches any lunar holiday
    
    Args:
        lunar_day: Day in lunar calendar
        lunar_month: Month in lunar calendar
    
    Returns:
        Holiday info dict if found, None otherwise
    """
    for holiday in LUNAR_HOLIDAYS:
        if holiday["day"] == lunar_day and holiday["month"] == lunar_month:
            return {"name": holiday["name"], "nameVi": holiday["nameVi"]}
    return None


def is_tet(lunar_day: int, lunar_month: int) -> bool:
    """Check if a lunar date is Tet (Mung 1, 2, 3)"""
    return lunar_month == 1 and 1 <= lunar_day <= 3


def is_giao_thua(dd: int, mm: int, yy: int) -> bool:
    """Check if today is Giao Thua by checking if tomorrow is Mung 1 Tet"""
    import datetime
    tomorrow = datetime.date(yy, mm, dd) + datetime.timedelta(days=1)
    lunar = solar_to_lunar(tomorrow.day, tomorrow.month, tomorrow.year)
    return lunar["month"] == 1 and lunar["day"] == 1


if __name__ == "__main__":
    # Test the library
    import datetime
    
    today = datetime.date.today()
    lunar = solar_to_lunar(today.day, today.month, today.year)
    
    print(f"Solar: {today.day}/{today.month}/{today.year}")
    print(f"Lunar: {lunar['day']}/{lunar['month']}/{lunar['year']} (leap: {lunar['leap']})")
    print(f"Lunar Month: {get_lunar_month_name(lunar['month'], lunar['leap'])}")
    print(f"Can Chi Year: {get_year_can_chi(lunar['year'])}")
    print(f"Can Chi Day: {get_day_can_chi(lunar['jd'])}")
    
    # Check for holiday
    holiday = check_lunar_holiday(lunar['day'], lunar['month'])
    if holiday:
        print(f"Lunar Holiday: {holiday['nameVi']}")
    
    # Test conversion back
    solar = lunar_to_solar(lunar['day'], lunar['month'], lunar['year'], lunar['leap'])
    print(f"Convert back: {solar['day']}/{solar['month']}/{solar['year']}")
