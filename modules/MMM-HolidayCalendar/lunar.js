/**
 * Vietnamese Lunar Calendar Library
 * Clean implementation based on Ho Ngoc Duc's algorithm
 * Optimized for Vietnam timezone (GMT+7)
 * 
 * Reference: https://www.informatik.uni-leipzig.de/~duc/amlich/
 */

var LunarCalendar = (function () {
    'use strict';

    // Constants
    var PI = Math.PI;
    var TIMEZONE = 7; // Vietnam GMT+7

    /**
     * Calculate Julian Day Number from Solar date
     * Using the standard astronomical formula
     */
    function jdFromDate(dd, mm, yy) {
        var a = Math.floor((14 - mm) / 12);
        var y = yy + 4800 - a;
        var m = mm + 12 * a - 3;
        var jd = dd + Math.floor((153 * m + 2) / 5) + 365 * y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400) - 32045;
        return jd;
    }

    /**
     * Convert Julian Day Number to Solar date
     */
    function jdToDate(jd) {
        var a, b, c, d, e, m;
        var Z = Math.floor(jd + 0.5);
        var F = jd + 0.5 - Z;
        if (Z < 2299161) {
            a = Z;
        } else {
            var alpha = Math.floor((Z - 1867216.25) / 36524.25);
            a = Z + 1 + alpha - Math.floor(alpha / 4);
        }
        b = a + 1524;
        c = Math.floor((b - 122.1) / 365.25);
        d = Math.floor(365.25 * c);
        e = Math.floor((b - d) / 30.6001);
        var day = b - d - Math.floor(30.6001 * e) + F;
        if (e < 14) {
            m = e - 1;
        } else {
            m = e - 13;
        }
        var y;
        if (m > 2) {
            y = c - 4716;
        } else {
            y = c - 4715;
        }
        return { day: Math.floor(day), month: m, year: y };
    }

    /**
     * Calculate Julian Day of the k-th New Moon after J2000
     * Formula from "Astronomical Algorithms" by Jean Meeus
     */
    function getNewMoonDay(k, timeZone) {
        var T = k / 1236.85;
        var T2 = T * T;
        var T3 = T2 * T;
        var dr = PI / 180;

        var Jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * T2 - 0.000000155 * T3;
        Jd1 = Jd1 + 0.00033 * Math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr);

        var M = 359.2242 + 29.10535608 * k - 0.0000333 * T2 - 0.00000347 * T3;
        var Mpr = 306.0253 + 385.81691806 * k + 0.0107306 * T2 + 0.00001236 * T3;
        var F = 21.2964 + 390.67050646 * k - 0.0016528 * T2 - 0.00000239 * T3;

        var C1 = (0.1734 - 0.000393 * T) * Math.sin(M * dr) + 0.0021 * Math.sin(2 * dr * M);
        C1 = C1 - 0.4068 * Math.sin(Mpr * dr) + 0.0161 * Math.sin(dr * 2 * Mpr);
        C1 = C1 - 0.0004 * Math.sin(dr * 3 * Mpr);
        C1 = C1 + 0.0104 * Math.sin(dr * 2 * F) - 0.0051 * Math.sin(dr * (M + Mpr));
        C1 = C1 - 0.0074 * Math.sin(dr * (M - Mpr)) + 0.0004 * Math.sin(dr * (2 * F + M));
        C1 = C1 - 0.0004 * Math.sin(dr * (2 * F - M)) - 0.0006 * Math.sin(dr * (2 * F + Mpr));
        C1 = C1 + 0.0010 * Math.sin(dr * (2 * F - Mpr)) + 0.0005 * Math.sin(dr * (2 * Mpr + M));

        var JdNew;
        if (T < -11) {
            var deltat = 0.001 + 0.000839 * T + 0.0002261 * T2 - 0.00000845 * T3 - 0.000000081 * T * T3;
            JdNew = Jd1 + C1 - deltat;
        } else {
            JdNew = Jd1 + C1;
        }

        return Math.floor(JdNew + 0.5 + timeZone / 24);
    }

    /**
     * Calculate Sun's longitude at a given Julian Day
     * Returns value in radians
     */
    function getSunLongitude(jdn, timeZone) {
        var T = (jdn - 0.5 - timeZone / 24 - 2451545.0) / 36525;
        var T2 = T * T;
        var dr = PI / 180;

        var M = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2;
        var L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2;
        var DL = (1.914600 - 0.004817 * T - 0.000014 * T2) * Math.sin(dr * M);
        DL = DL + (0.019993 - 0.000101 * T) * Math.sin(dr * 2 * M) + 0.000290 * Math.sin(dr * 3 * M);
        var L = L0 + DL;

        L = L * dr;
        L = L - PI * 2 * Math.floor(L / (PI * 2));
        return L;
    }

    /**
     * Get Sun longitude at noon on a given Julian Day
     * Returns the "Major Solar Term" index (0-11)
     * Each major term is 30 degrees apart
     */
    function getSunLongitudeIndex(jdn, timeZone) {
        var sunLong = getSunLongitude(jdn, timeZone) / PI * 6;
        return Math.floor(sunLong);
    }

    /**
     * Find the day of the Lunar Month 11 of a given year
     * Month 11 is the month containing the Winter Solstice
     */
    function getLunarMonth11(yy, timeZone) {
        var off = jdFromDate(31, 12, yy) - 2415021;
        var k = Math.floor(off / 29.530588853);
        var nm = getNewMoonDay(k, timeZone);
        var sunLong = getSunLongitudeIndex(nm, timeZone);

        if (sunLong >= 9) {
            nm = getNewMoonDay(k - 1, timeZone);
        }
        return nm;
    }

    /**
     * Find the index of the leap month after month 11
     * A leap month is a month without a major solar term
     */
    function getLeapMonthOffset(a11, timeZone) {
        var k = Math.floor((a11 - 2415021.076998695) / 29.530588853 + 0.5);
        var last = 0;
        var i = 1;
        var arc = getSunLongitudeIndex(getNewMoonDay(k + i, timeZone), timeZone);

        do {
            last = arc;
            i++;
            arc = getSunLongitudeIndex(getNewMoonDay(k + i, timeZone), timeZone);
        } while (arc !== last && i < 14);

        return i - 1;
    }

    /**
     * Convert Solar date to Lunar date
     * Main conversion function
     * 
     * @param {number} dd - Solar day (1-31)
     * @param {number} mm - Solar month (1-12) 
     * @param {number} yy - Solar year
     * @returns {Object} { day, month, year, leap, jd }
     */
    function convertSolar2Lunar(dd, mm, yy) {
        var timeZone = TIMEZONE;
        var dayNumber = jdFromDate(dd, mm, yy);
        var k = Math.floor((dayNumber - 2415021.076998695) / 29.530588853);
        var monthStart = getNewMoonDay(k + 1, timeZone);

        if (monthStart > dayNumber) {
            monthStart = getNewMoonDay(k, timeZone);
        }

        var a11 = getLunarMonth11(yy, timeZone);
        var b11 = a11;
        var lunarYear;

        if (a11 >= monthStart) {
            lunarYear = yy;
            a11 = getLunarMonth11(yy - 1, timeZone);
        } else {
            lunarYear = yy + 1;
            b11 = getLunarMonth11(yy + 1, timeZone);
        }

        var lunarDay = dayNumber - monthStart + 1;
        var diff = Math.floor((monthStart - a11) / 29);
        var lunarLeap = false;
        var lunarMonth = diff + 11;

        if (b11 - a11 > 365) {
            var leapMonthDiff = getLeapMonthOffset(a11, timeZone);
            if (diff >= leapMonthDiff) {
                lunarMonth = diff + 10;
                if (diff === leapMonthDiff) {
                    lunarLeap = true;
                }
            }
        }

        if (lunarMonth > 12) {
            lunarMonth = lunarMonth - 12;
        }
        if (lunarMonth >= 11 && diff < 4) {
            lunarYear -= 1;
        }

        return {
            day: lunarDay,
            month: lunarMonth,
            year: lunarYear,
            leap: lunarLeap,
            jd: dayNumber
        };
    }

    /**
     * Convert Lunar date to Solar date
     * 
     * @param {number} lunarDay - Lunar day
     * @param {number} lunarMonth - Lunar month
     * @param {number} lunarYear - Lunar year
     * @param {boolean} lunarLeap - Is leap month?
     * @returns {Object} { day, month, year }
     */
    function convertLunar2Solar(lunarDay, lunarMonth, lunarYear, lunarLeap) {
        var timeZone = TIMEZONE;
        var a11, b11;

        if (lunarMonth < 11) {
            a11 = getLunarMonth11(lunarYear - 1, timeZone);
            b11 = getLunarMonth11(lunarYear, timeZone);
        } else {
            a11 = getLunarMonth11(lunarYear, timeZone);
            b11 = getLunarMonth11(lunarYear + 1, timeZone);
        }

        var k = Math.floor(0.5 + (a11 - 2415021.076998695) / 29.530588853);
        var off = lunarMonth - 11;
        if (off < 0) {
            off += 12;
        }

        if (b11 - a11 > 365) {
            var leapOff = getLeapMonthOffset(a11, timeZone);
            var leapMonth = leapOff - 2;
            if (leapMonth < 0) {
                leapMonth += 12;
            }
            if (lunarLeap && lunarMonth !== leapMonth) {
                return { day: 0, month: 0, year: 0 }; // Invalid
            } else if (lunarLeap || off >= leapOff) {
                off += 1;
            }
        }

        var monthStart = getNewMoonDay(k + off, timeZone);
        return jdToDate(monthStart + lunarDay - 1);
    }

    /**
     * Get the Can Chi (Heavenly Stem + Earthly Branch) for a year
     */
    function getYearCanChi(lunarYear) {
        var CAN = ['Giáp', 'Ất', 'Bính', 'Đinh', 'Mậu', 'Kỷ', 'Canh', 'Tân', 'Nhâm', 'Quý'];
        var CHI = ['Tý', 'Sửu', 'Dần', 'Mão', 'Thìn', 'Tỵ', 'Ngọ', 'Mùi', 'Thân', 'Dậu', 'Tuất', 'Hợi'];
        var can = CAN[(lunarYear + 6) % 10];
        var chi = CHI[(lunarYear + 8) % 12];
        return can + ' ' + chi;
    }

    /**
     * Get the day's Can Chi
     */
    function getDayCanChi(jd) {
        var CAN = ['Giáp', 'Ất', 'Bính', 'Đinh', 'Mậu', 'Kỷ', 'Canh', 'Tân', 'Nhâm', 'Quý'];
        var CHI = ['Tý', 'Sửu', 'Dần', 'Mão', 'Thìn', 'Tỵ', 'Ngọ', 'Mùi', 'Thân', 'Dậu', 'Tuất', 'Hợi'];
        var can = CAN[(jd + 9) % 10];
        var chi = CHI[(jd + 1) % 12];
        return can + ' ' + chi;
    }

    // Lunar holidays - NOTE: Giao Thua is NOT in this list because 
    // lunar month 12 can have 29 or 30 days. Use isGiaoThua() instead.
    var lunarHolidays = [
        { day: 1, month: 1, name: "Mùng 1 Tết" },
        { day: 2, month: 1, name: "Mùng 2 Tết" },
        { day: 3, month: 1, name: "Mùng 3 Tết" },
        { day: 15, month: 1, name: "Rằm tháng Giêng" },
        { day: 10, month: 3, name: "Giỗ Tổ Hùng Vương" },
        { day: 5, month: 5, name: "Tết Đoan Ngọ" },
        { day: 15, month: 7, name: "Lễ Vu Lan" },
        { day: 15, month: 8, name: "Tết Trung Thu" },
        { day: 23, month: 12, name: "Ông Công Ông Táo" }
    ];

    // Public API
    return {
        /**
         * Get Lunar date from Solar date
         * @param {number} dd - Day (1-31)
         * @param {number} mm - Month (1-12)
         * @param {number} yy - Year
         */
        getLunarDate: function (dd, mm, yy) {
            return convertSolar2Lunar(dd, mm, yy);
        },

        /**
         * Get Solar date from Lunar date
         */
        getSolarDate: function (ld, lm, ly, leap) {
            return convertLunar2Solar(ld, lm, ly, leap || false);
        },

        /**
         * Get Can Chi for a lunar year
         */
        getYearCanChi: getYearCanChi,

        /**
         * Get Can Chi for a specific Julian Day
         */
        getDayCanChi: getDayCanChi,

        /**
         * Get list of fixed lunar holidays
         */
        getHolidays: function () {
            return lunarHolidays;
        },

        /**
         * Check if a lunar date is Tet (Mung 1, 2, 3)
         */
        isTet: function (lunarDay, lunarMonth) {
            return lunarMonth === 1 && lunarDay >= 1 && lunarDay <= 3;
        },

        /**
         * Check if today is Giao Thua (last day of lunar year)
         * by checking if tomorrow is Mung 1 Tet
         */
        isGiaoThua: function (dd, mm, yy) {
            var tomorrow = new Date(yy, mm - 1, dd + 1);
            var lunar = convertSolar2Lunar(tomorrow.getDate(), tomorrow.getMonth() + 1, tomorrow.getFullYear());
            return lunar.month === 1 && lunar.day === 1;
        }
    };
})();
