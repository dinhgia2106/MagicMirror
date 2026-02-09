/* MMM-HolidayCalendar
 * A grid-style desk calendar module for MagicMirror²
 * Supports Vietnamese holidays and touch gestures for month navigation
 * Infinity scroll carousel style
 */

Module.register("MMM-HolidayCalendar", {
    defaults: {
        calendarUrl: "https://www.officeholidays.com/ics/vietnam",
        backendApiUrl: null, // e.g., "http://192.168.1.100:8000/api/holidays"
        fetchInterval: 7 * 24 * 60 * 60 * 1000, // 7 days
        language: "vi", // "vi" for Vietnamese, "en" for English
        highlightToday: true,
        panelWidth: 340, // Width of each month panel
    },

    // Vietnamese day names
    dayNamesVi: ["CN", "T2", "T3", "T4", "T5", "T6", "T7"],
    dayNamesEn: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],

    // Vietnamese month names
    monthNamesVi: [
        "Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4",
        "Tháng 5", "Tháng 6", "Tháng 7", "Tháng 8",
        "Tháng 9", "Tháng 10", "Tháng 11", "Tháng 12"
    ],
    monthNamesEn: [
        "January", "February", "March", "April",
        "May", "June", "July", "August",
        "September", "October", "November", "December"
    ],

    // Vietnamese lunar month names (1-12)
    lunarMonthNames: [
        "Giêng", "Hai", "Ba", "Tư", "Năm", "Sáu",
        "Bảy", "Tám", "Chín", "Mười", "Mười Một", "Chạp"
    ],

    // Holiday name translations
    holidayTranslations: {
        "Hung Kings Temple Festival": "Giỗ Tổ Hùng Vương",
        "Reunification Day": "Ngày Thống nhất",
        "Labour Day": "Ngày Quốc tế Lao động",
        "National Day": "Quốc khánh",
        "National Day Holiday": "Nghỉ Quốc khánh",
        "New Year's Day": "Tết Dương lịch",
        "New Year's Day Holiday": "Nghỉ Tết Dương lịch",
        "International Women's Day": "Quốc tế Phụ nữ",
        "Vietnamese Women's Day": "Ngày Phụ nữ Việt Nam",
        "Teacher's Day": "Ngày Nhà giáo Việt Nam",
        "Children's Day": "Ngày Quốc tế Thiếu nhi"
    },

    // Extra international holidays popular in Vietnam (fixed dates)
    // Format: { month: day } or { month: [day1, day2] }
    extraHolidaysVi: [
        { month: 1, day: 1, name: "Tết Dương lịch" },
        { month: 2, day: 14, name: "Lễ tình nhân" },
        { month: 2, day: 22, name: "Sinh nhật Mẹ" },
        { month: 3, day: 8, name: "Quốc tế Phụ nữ" },
        { month: 4, day: 1, name: "Cá tháng Tư" },
        { month: 4, day: 22, name: "Ngày Trái Đất" },
        { month: 5, day: 1, name: "Quốc tế Lao động" },
        { month: 6, day: 1, name: "Quốc tế Thiếu nhi" },
        { month: 6, day: 10, name: "Sinh nhật Ba" },
        { month: 6, day: 21, name: "Sinh nhật Gia" },
        { month: 10, day: 20, name: "Ngày Phụ nữ VN" },
        { month: 10, day: 31, name: "Halloween" },
        { month: 11, day: 20, name: "Ngày Nhà giáo VN" },
        { month: 12, day: 16, name: "Sinh nhật Duyên" },
        { month: 12, day: 24, name: "Đêm Giáng sinh" },
        { month: 12, day: 25, name: "Giáng sinh" }
    ],

    extraHolidaysEn: [
        { month: 1, day: 1, name: "New Year's Day" },
        { month: 2, day: 14, name: "Valentine's Day" },
        { month: 3, day: 8, name: "Women's Day" },
        { month: 4, day: 1, name: "April Fools' Day" },
        { month: 4, day: 22, name: "Earth Day" },
        { month: 5, day: 1, name: "Labour Day" },
        { month: 6, day: 1, name: "Children's Day" },
        { month: 10, day: 20, name: "VN Women's Day" },
        { month: 10, day: 31, name: "Halloween" },
        { month: 11, day: 20, name: "VN Teacher's Day" },
        { month: 12, day: 24, name: "Christmas Eve" },
        { month: 12, day: 25, name: "Christmas" },
        { month: 12, day: 31, name: "New Year's Eve" }
    ],

    start: function () {
        Log.info("Starting module: " + this.name);
        this.holidays = {};
        this.currentDate = new Date();
        this.loaded = false;

        // Month index system: 0 = current month, +1 = next month, -1 = previous month
        this.monthIndex = 0;

        // Calculate base references
        this.baseSolarYear = this.currentDate.getFullYear();
        this.baseSolarMonth = this.currentDate.getMonth(); // 0-11

        // Get current lunar month as base
        this.baseLunarDate = null; // Will be set after lunar.js loads

        // Drag state
        this.isDragging = false;
        this.dragStartX = 0;
        this.currentOffset = 0;
        this.wasDragging = false;

        // Display Mode: 'solar' or 'lunar'
        this.displayMode = "solar";

        // Only add hardcoded holidays if NOT using backend API
        if (!this.config.backendApiUrl) {
            this.addExtraHolidays();
            this.addLunarHolidays();
        }

        this.loadHolidays();
        this.loadCustomHolidays();
        this.scheduleUpdate();
    },

    // Get solar date for a given month index
    getSolarDateForIndex: function (index) {
        const date = new Date(this.baseSolarYear, this.baseSolarMonth + index, 1);
        return date;
    },

    // Get lunar month/year for a given month index
    getLunarInfoForIndex: function (index) {
        if (typeof LunarCalendar === 'undefined') return null;

        // Get current lunar date as base
        const today = this.currentDate;
        const baseLunar = LunarCalendar.getLunarDate(today.getDate(), today.getMonth() + 1, today.getFullYear());

        // Calculate target lunar month
        let targetMonth = baseLunar.month + index;
        let targetYear = baseLunar.year;

        // Handle month overflow/underflow
        while (targetMonth > 12) {
            targetMonth -= 12;
            targetYear++;
        }
        while (targetMonth < 1) {
            targetMonth += 12;
            targetYear--;
        }

        return {
            month: targetMonth,
            year: targetYear
        };
    },

    // Get the first day of a lunar month in solar calendar
    getFirstDayOfLunarMonth: function (lunarMonth, lunarYear) {
        if (typeof LunarCalendar === 'undefined') return null;
        return LunarCalendar.getSolarDate(1, lunarMonth, lunarYear, false);
    },

    addExtraHolidays: function () {
        const isVi = this.config.language === "vi";
        const extraList = isVi ? this.extraHolidaysVi : this.extraHolidaysEn;
        const currentYear = this.currentDate.getFullYear();

        // Add for previous year, current year and next year
        [currentYear - 1, currentYear, currentYear + 1].forEach(year => {
            extraList.forEach(h => {
                const dateKey = `${year}-${String(h.month).padStart(2, '0')}-${String(h.day).padStart(2, '0')}`;
                if (!this.holidays[dateKey]) {
                    this.holidays[dateKey] = [];
                }
                const exists = this.holidays[dateKey].some(existing => existing.name === h.name);
                if (!exists) {
                    this.holidays[dateKey].push({
                        name: h.name,
                        isExtra: true
                    });
                }
            });
        });
    },

    addLunarHolidays: function () {
        if (typeof LunarCalendar === 'undefined' || this.config.language !== 'vi') return;

        const currentYear = this.currentDate.getFullYear();

        // Get lunar holidays from library (doesn't include Giao Thừa)
        const lunarHolidays = LunarCalendar.getHolidays();

        // Check surrounding lunar years
        [currentYear - 1, currentYear, currentYear + 1].forEach(lunarYear => {
            // Add regular lunar holidays
            lunarHolidays.forEach(h => {
                const solar = LunarCalendar.getSolarDate(h.day, h.month, lunarYear, false);
                if (solar && solar.day > 0) {
                    const dateKey = this.getDateKey(solar.year, solar.month - 1, solar.day);
                    this.addHoliday(dateKey, h.name);
                }
            });

            // Add Giao Thừa dynamically (last day of lunar month 12, can be 29 or 30)
            // Check if day 30 exists, otherwise use day 29
            const day30Solar = LunarCalendar.getSolarDate(30, 12, lunarYear, false);
            if (day30Solar && day30Solar.day > 0) {
                // Verify this is actually day 30 of month 12 (not invalid)
                const verify = LunarCalendar.getLunarDate(day30Solar.day, day30Solar.month, day30Solar.year);
                if (verify.month === 12 && verify.day === 30) {
                    const dateKey = this.getDateKey(day30Solar.year, day30Solar.month - 1, day30Solar.day);
                    this.addHoliday(dateKey, "Giao thừa");
                } else {
                    // Month 12 only has 29 days, use day 29 for Giao thừa
                    const day29Solar = LunarCalendar.getSolarDate(29, 12, lunarYear, false);
                    if (day29Solar && day29Solar.day > 0) {
                        const dateKey = this.getDateKey(day29Solar.year, day29Solar.month - 1, day29Solar.day);
                        this.addHoliday(dateKey, "Giao thừa");
                    }
                }
            } else {
                // Day 30 doesn't exist, use day 29
                const day29Solar = LunarCalendar.getSolarDate(29, 12, lunarYear, false);
                if (day29Solar && day29Solar.day > 0) {
                    const dateKey = this.getDateKey(day29Solar.year, day29Solar.month - 1, day29Solar.day);
                    this.addHoliday(dateKey, "Giao thừa");
                }
            }
        });
    },

    addHoliday: function (dateKey, name) {
        if (!this.holidays[dateKey]) {
            this.holidays[dateKey] = [];
        }
        // Avoid dups
        const exists = this.holidays[dateKey].some(h => h.name === name);
        if (!exists) {
            this.holidays[dateKey].push({ name: name, isLunar: true });
        }
    },

    getScripts: function () {
        return ["lunar.js"];
    },

    getStyles: function () {
        return ["MMM-HolidayCalendar.css"];
    },

    getDom: function () {
        const wrapper = document.createElement("div");
        wrapper.className = "holiday-calendar-wrapper";
        wrapper.id = "holiday-calendar-" + this.identifier;

        if (!this.loaded) {
            wrapper.innerHTML = '<div class="loading">Đang tải...</div>';
            return wrapper;
        }

        // Apply current display mode class
        wrapper.classList.add(this.displayMode === "lunar" ? "show-lunar" : "show-solar");

        // Create flip container for smooth transition
        const flipContainer = document.createElement("div");
        flipContainer.className = "calendar-flip-container";

        // === SOLAR CALENDAR (Front) ===
        const solarFace = document.createElement("div");
        solarFace.className = "calendar-face solar-face";
        solarFace.appendChild(this.buildCarousel("solar"));
        flipContainer.appendChild(solarFace);

        // === LUNAR CALENDAR (Back) ===
        const lunarFace = document.createElement("div");
        lunarFace.className = "calendar-face lunar-face";
        lunarFace.appendChild(this.buildCarousel("lunar"));
        flipContainer.appendChild(lunarFace);

        wrapper.appendChild(flipContainer);

        // Custom double-click detection with 300ms threshold
        let lastClickTime = 0;
        let clickTimeout = null;

        flipContainer.addEventListener('click', (e) => {
            // Prevent if was dragging
            if (this.wasDragging) {
                this.wasDragging = false;
                return;
            }

            const currentTime = Date.now();
            const timeDiff = currentTime - lastClickTime;

            if (timeDiff < 300 && timeDiff > 0) {
                // Double-click detected - return to current month
                clearTimeout(clickTimeout);
                clickTimeout = null;
                lastClickTime = 0;

                // Only animate if not already at current month
                if (this.monthIndex !== 0) {
                    this.animateToCurrentMonth(wrapper);
                }
            } else {
                // First click - wait to see if it's a double-click
                lastClickTime = currentTime;
                clickTimeout = setTimeout(() => {
                    // Single click confirmed - toggle solar/lunar
                    this.displayMode = this.displayMode === "solar" ? "lunar" : "solar";
                    wrapper.classList.remove("show-solar", "show-lunar");
                    wrapper.classList.add(this.displayMode === "lunar" ? "show-lunar" : "show-solar");

                    // Rebuild holiday list with correct day format
                    const oldList = wrapper.querySelector('.holiday-list');
                    if (oldList) {
                        const newList = this.buildHolidayList(this.getSolarDateForIndex(this.monthIndex));
                        this.setupHolidayListEvents(newList);
                        wrapper.replaceChild(newList, oldList);
                    }

                    clickTimeout = null;
                    lastClickTime = 0;
                }, 300);
            }
        });

        // Holiday list OUTSIDE flip container - based on current solar month
        const currentSolarDate = this.getSolarDateForIndex(this.monthIndex);
        const holidayList = this.buildHolidayList(currentSolarDate);
        wrapper.appendChild(holidayList);

        // Setup scroll events for holiday list
        this.setupHolidayListEvents(holidayList);

        // Add touch event listeners for BOTH carousels
        const solarTrack = wrapper.querySelector('.solar-face .calendar-track');
        const lunarTrack = wrapper.querySelector('.lunar-face .calendar-track');
        if (solarTrack) this.addTouchListeners(wrapper, solarTrack, lunarTrack);

        return wrapper;
    },

    buildCarousel: function (mode) {
        const viewport = document.createElement("div");
        viewport.className = "calendar-viewport";

        const track = document.createElement("div");
        track.className = "calendar-track";

        // Build 3 panels based on monthIndex: prev (-1), current (0), next (+1)
        track.appendChild(this.buildPanel(this.monthIndex - 1, "prev", mode));
        track.appendChild(this.buildPanel(this.monthIndex, "current", mode));
        track.appendChild(this.buildPanel(this.monthIndex + 1, "next", mode));

        viewport.appendChild(track);
        return viewport;
    },

    buildPanel: function (index, position, mode) {
        const panel = document.createElement("div");
        panel.className = "calendar-panel " + position;

        // Header
        const header = document.createElement("div");
        header.className = "calendar-header";

        const monthYear = document.createElement("div");
        monthYear.className = "month-year";

        if (mode === "lunar") {
            // Get lunar month/year for this index
            const lunarInfo = this.getLunarInfoForIndex(index);
            if (lunarInfo) {
                const monthName = this.lunarMonthNames[lunarInfo.month - 1];
                const canChi = LunarCalendar.getYearCanChi(lunarInfo.year);
                monthYear.innerHTML = `Tháng ${monthName} - ${canChi}`;
            }
        } else {
            // Solar mode
            const solarDate = this.getSolarDateForIndex(index);
            const isVi = this.config.language === "vi";
            const monthNames = isVi ? this.monthNamesVi : this.monthNamesEn;
            monthYear.innerHTML = `${monthNames[solarDate.getMonth()]} ${solarDate.getFullYear()}`;
        }

        header.appendChild(monthYear);
        panel.appendChild(header);

        // Calendar grid
        panel.appendChild(this.buildCalendarGrid(index, mode));

        return panel;
    },

    buildCalendarGrid: function (index, mode) {
        const calendar = document.createElement("div");
        calendar.className = "calendar-grid";

        const isVi = this.config.language === "vi";
        const dayNames = isVi ? this.dayNamesVi : this.dayNamesEn;

        // Day headers
        const dayHeader = document.createElement("div");
        dayHeader.className = "day-header-row";
        dayNames.forEach((day, dayIndex) => {
            const dayCell = document.createElement("div");
            dayCell.className = "day-header";
            if (dayIndex === 0) dayCell.classList.add("sunday");
            if (dayIndex === 6) dayCell.classList.add("saturday");
            dayCell.textContent = day;
            dayHeader.appendChild(dayCell);
        });
        calendar.appendChild(dayHeader);

        // Get reference solar date for this index
        const solarDate = this.getSolarDateForIndex(index);
        const year = solarDate.getFullYear();
        const month = solarDate.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDay = firstDay.getDay();
        const daysInMonth = lastDay.getDate();
        const prevMonthLastDay = new Date(year, month, 0).getDate();

        let dayCount = 1;
        let nextMonthDay = 1;

        for (let week = 0; week < 6; week++) {
            const weekRow = document.createElement("div");
            weekRow.className = "week-row";

            for (let dayOfWeek = 0; dayOfWeek < 7; dayOfWeek++) {
                const dayCell = document.createElement("div");
                dayCell.className = "day-cell";

                const cellIndex = week * 7 + dayOfWeek;

                if (cellIndex < startDay) {
                    const prevDay = prevMonthLastDay - startDay + cellIndex + 1;
                    dayCell.textContent = prevDay;
                    dayCell.classList.add("other-month");
                } else if (dayCount <= daysInMonth) {

                    // Main Day Display based on mode
                    if (mode === "lunar" && typeof LunarCalendar !== 'undefined') {
                        const lunar = LunarCalendar.getLunarDate(dayCount, month + 1, year);
                        if (lunar.day === 1) {
                            dayCell.innerHTML = `${lunar.day}<span class="lunar-month">/${lunar.month}</span>`;
                        } else {
                            dayCell.textContent = lunar.day;
                        }
                        dayCell.classList.add("is-lunar");
                    } else {
                        dayCell.textContent = dayCount;
                    }

                    // Highlight today
                    if (this.config.highlightToday &&
                        year === this.currentDate.getFullYear() &&
                        month === this.currentDate.getMonth() &&
                        dayCount === this.currentDate.getDate()) {
                        dayCell.classList.add("today");
                    }

                    // Check holidays
                    const dateKey = this.getDateKey(year, month, dayCount);
                    if (this.holidays[dateKey]) {
                        dayCell.classList.add("holiday");
                    }

                    if (dayOfWeek === 0) dayCell.classList.add("sunday");
                    if (dayOfWeek === 6) dayCell.classList.add("saturday");

                    dayCount++;
                } else {
                    dayCell.textContent = nextMonthDay;
                    dayCell.classList.add("other-month");
                    nextMonthDay++;
                }

                weekRow.appendChild(dayCell);
            }

            calendar.appendChild(weekRow);
            if (dayCount > daysInMonth && week >= 4) break;
        }

        return calendar;
    },

    buildHolidayList: function (viewDate) {
        const listContainer = document.createElement("div");
        listContainer.className = "holiday-list";

        const year = viewDate.getFullYear();
        const month = viewDate.getMonth();

        const monthHolidays = [];
        for (let day = 1; day <= 31; day++) {
            const dateKey = this.getDateKey(year, month, day);
            if (this.holidays[dateKey]) {
                this.holidays[dateKey].forEach(holiday => {
                    // Calculate lunar day if in lunar mode
                    let displayDay = day;
                    if (this.displayMode === "lunar" && typeof LunarCalendar !== 'undefined') {
                        const lunar = LunarCalendar.getLunarDate(day, month + 1, year);
                        displayDay = lunar.day;
                    }
                    monthHolidays.push({ day: day, displayDay: displayDay, ...holiday });
                });
            }
        }

        if (monthHolidays.length === 0) {
            const noHoliday = document.createElement("div");
            noHoliday.className = "no-holiday";
            noHoliday.textContent = this.config.language === "vi"
                ? "Không có ngày lễ"
                : "No holidays";
            listContainer.appendChild(noHoliday);
        } else {
            // Render ALL holidays (scrollable via CSS)
            monthHolidays.forEach(holiday => {
                const item = document.createElement("div");
                item.className = "holiday-item";

                const daySpan = document.createElement("span");
                daySpan.className = "holiday-day";
                daySpan.textContent = holiday.displayDay;

                const nameSpan = document.createElement("span");
                nameSpan.className = "holiday-name";
                nameSpan.textContent = holiday.name;

                item.appendChild(daySpan);
                item.appendChild(nameSpan);
                listContainer.appendChild(item);
            });
        }

        return listContainer;
    },

    setupHolidayListEvents: function (holidayList) {
        // State for scroll handling with smooth momentum (like month swipe)
        let isDragging = false;
        let startY = 0;
        let scrollStart = 0;
        let lastY = 0;
        let velocity = 0;
        let lastTime = 0;
        let animationId = null;

        // Stop any ongoing momentum animation
        const stopMomentum = () => {
            if (animationId) {
                cancelAnimationFrame(animationId);
                animationId = null;
            }
        };

        // Apply smooth momentum scrolling - like iOS/native scroll feel
        const applyMomentum = () => {
            // Lower friction = longer, smoother scroll (0.97 feels like native)
            const friction = 0.97;
            const minVelocity = 0.1;

            velocity *= friction;

            if (Math.abs(velocity) > minVelocity) {
                holidayList.scrollTop += velocity;
                animationId = requestAnimationFrame(applyMomentum);
            } else {
                animationId = null;
            }
        };

        // Touch scroll with momentum - immediate response
        holidayList.addEventListener('touchstart', (e) => {
            e.stopPropagation();
            e.preventDefault(); // Prevent browser delay for immediate drag response
            stopMomentum();
            isDragging = true;
            startY = e.touches[0].clientY;
            lastY = startY;
            scrollStart = holidayList.scrollTop;
            lastTime = Date.now();
            velocity = 0;
        }, { passive: false });

        holidayList.addEventListener('touchmove', (e) => {
            e.stopPropagation();
            if (!isDragging) return;

            const currentY = e.touches[0].clientY;
            const currentTime = Date.now();
            const deltaTime = currentTime - lastTime;

            // Calculate velocity with higher multiplier for sensitivity
            if (deltaTime > 0) {
                velocity = (lastY - currentY) / deltaTime * 25; // Higher = more sensitive to light swipes
            }

            const deltaY = startY - currentY;
            holidayList.scrollTop = scrollStart + deltaY;

            lastY = currentY;
            lastTime = currentTime;
        }, { passive: false });

        holidayList.addEventListener('touchend', (e) => {
            e.stopPropagation();
            isDragging = false;
            // Apply momentum with very low threshold - light swipes trigger scroll
            if (Math.abs(velocity) > 0.3) {
                applyMomentum();
            }
        }, { passive: false });

        // Mouse scroll (drag) with momentum
        holidayList.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            stopMomentum();
            isDragging = true;
            startY = e.clientY;
            lastY = startY;
            scrollStart = holidayList.scrollTop;
            lastTime = Date.now();
            velocity = 0;
            holidayList.style.cursor = 'grabbing';
        });

        holidayList.addEventListener('mousemove', (e) => {
            e.stopPropagation();
            if (!isDragging) return;
            e.preventDefault();

            const currentY = e.clientY;
            const currentTime = Date.now();
            const deltaTime = currentTime - lastTime;

            // Calculate velocity with higher multiplier for sensitivity
            if (deltaTime > 0) {
                velocity = (lastY - currentY) / deltaTime * 25;
            }

            const deltaY = startY - currentY;
            holidayList.scrollTop = scrollStart + deltaY;

            lastY = currentY;
            lastTime = currentTime;
        });

        holidayList.addEventListener('mouseup', (e) => {
            e.stopPropagation();
            isDragging = false;
            holidayList.style.cursor = 'grab';
            // Apply momentum with low threshold
            if (Math.abs(velocity) > 0.3) {
                applyMomentum();
            }
        });

        holidayList.addEventListener('mouseleave', (e) => {
            e.stopPropagation();
            if (isDragging) {
                isDragging = false;
                holidayList.style.cursor = 'grab';
                // Apply momentum with low threshold
                if (Math.abs(velocity) > 0.3) {
                    applyMomentum();
                }
            }
        });

        // Mouse wheel scroll - already smooth via CSS
        holidayList.addEventListener('wheel', (e) => {
            e.stopPropagation();
        }, { passive: true });
    },

    addTouchListeners: function (wrapper, solarTrack, lunarTrack) {
        const self = this;
        const panelWidth = this.config.panelWidth;

        const updatePosition = (offset, animate) => {
            const transition = animate ? 'transform 0.3s ease' : 'none';
            const transform = `translateX(${-panelWidth + offset}px)`;
            if (solarTrack) {
                solarTrack.style.transition = transition;
                solarTrack.style.transform = transform;
            }
            if (lunarTrack) {
                lunarTrack.style.transition = transition;
                lunarTrack.style.transform = transform;
            }
        };

        // Initialize position (show middle panel)
        updatePosition(0, false);

        // Touch events
        wrapper.addEventListener("touchstart", function (e) {
            // If touching holiday list, don't trigger carousel drag
            if (e.target.closest('.holiday-list')) return;

            self.isDragging = true;
            self.dragStartX = e.changedTouches[0].screenX;
            self.currentOffset = 0;
            if (solarTrack) solarTrack.style.transition = 'none';
            if (lunarTrack) lunarTrack.style.transition = 'none';
        }, { passive: true });

        wrapper.addEventListener("touchmove", function (e) {
            // Skip if touching holiday list
            if (e.target.closest('.holiday-list')) return;

            if (self.isDragging) {
                self.currentOffset = e.changedTouches[0].screenX - self.dragStartX;
                updatePosition(self.currentOffset, false);
            }
        }, { passive: true });

        wrapper.addEventListener("touchend", function (e) {
            // Skip if touching holiday list
            if (e.target.closest('.holiday-list')) return;

            if (self.isDragging) {
                self.isDragging = false;
                self.handleDragEnd(solarTrack, lunarTrack, panelWidth);
            }
        }, { passive: true });

        // Mouse events
        wrapper.addEventListener("mousedown", function (e) {
            // If clicking holiday list, don't trigger carousel drag
            if (e.target.closest('.holiday-list')) return;

            self.isDragging = true;
            self.dragStartX = e.screenX;
            self.currentOffset = 0;
            if (solarTrack) solarTrack.style.transition = 'none';
            if (lunarTrack) lunarTrack.style.transition = 'none';
            e.preventDefault();
        });

        wrapper.addEventListener("mousemove", function (e) {
            // Skip if on holiday list
            if (e.target.closest('.holiday-list')) return;

            if (self.isDragging) {
                self.currentOffset = e.screenX - self.dragStartX;
                updatePosition(self.currentOffset, false);
            }
        });

        wrapper.addEventListener("mouseup", function (e) {
            // Skip if on holiday list
            if (e.target.closest('.holiday-list')) return;

            if (self.isDragging) {
                self.isDragging = false;
                self.handleDragEnd(solarTrack, lunarTrack, panelWidth);
            }
        });

        wrapper.addEventListener("mouseleave", function (e) {
            // Skip if leaving to/from holiday list
            if (e.target.closest('.holiday-list')) return;

            if (self.isDragging) {
                self.isDragging = false;
                self.handleDragEnd(solarTrack, lunarTrack, panelWidth);
            }
        });
    },

    handleDragEnd: function (solarTrack, lunarTrack, panelWidth) {
        const threshold = panelWidth * 0.3; // 30% of panel width to trigger change

        const animateTracks = (transform) => {
            if (solarTrack) {
                solarTrack.style.transition = 'transform 0.3s ease';
                solarTrack.style.transform = transform;
            }
            if (lunarTrack) {
                lunarTrack.style.transition = 'transform 0.3s ease';
                lunarTrack.style.transform = transform;
            }
        };

        // Mark as dragging if moved more than 10px (to prevent accidental flip)
        if (Math.abs(this.currentOffset) > 10) {
            this.wasDragging = true;
        }

        if (this.currentOffset > threshold) {
            // Go to previous month
            animateTracks(`translateX(0px)`);

            setTimeout(() => {
                this.monthIndex--;
                this.updateDom(0);
                // Reset wasDragging after DOM update so click-to-flip works immediately
                this.wasDragging = false;
            }, 300);
        } else if (this.currentOffset < -threshold) {
            // Go to next month
            animateTracks(`translateX(${-panelWidth * 2}px)`);

            setTimeout(() => {
                this.monthIndex++;
                this.updateDom(0);
                // Reset wasDragging after DOM update so click-to-flip works immediately
                this.wasDragging = false;
            }, 300);
        } else {
            // Snap back to current
            animateTracks(`translateX(${-panelWidth}px)`);
            // Also reset wasDragging when snapping back
            this.wasDragging = false;
        }

        this.currentOffset = 0;
    },

    // Animate slide back to current month (monthIndex = 0)
    animateToCurrentMonth: function (wrapper) {
        const panelWidth = this.config.panelWidth;
        const solarTrack = wrapper.querySelector('.solar-face .calendar-track');
        const lunarTrack = wrapper.querySelector('.lunar-face .calendar-track');

        if (!solarTrack && !lunarTrack) {
            // Fallback: just reset without animation
            this.monthIndex = 0;
            this.updateDom(0);
            return;
        }

        // Determine direction based on current monthIndex
        // If monthIndex > 0 (in the future), slide right to go back
        // If monthIndex < 0 (in the past), slide left to go forward
        const slideRight = this.monthIndex > 0;
        const targetX = slideRight ? panelWidth : -panelWidth * 3;

        const animateTracks = (transform) => {
            if (solarTrack) {
                solarTrack.style.transition = 'transform 0.25s ease-out';
                solarTrack.style.transform = transform;
            }
            if (lunarTrack) {
                lunarTrack.style.transition = 'transform 0.25s ease-out';
                lunarTrack.style.transform = transform;
            }
        };

        // Slide out of view
        animateTracks(`translateX(${targetX}px)`);

        // Reset to current month immediately after slide-out animation
        setTimeout(() => {
            this.monthIndex = 0;
            this.updateDom(0);
        }, 250);
    },

    getDateKey: function (year, month, day) {
        return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    },

    loadHolidays: function () {
        if (this.config.calendarUrl) {
            this.sendSocketNotification("FETCH_HOLIDAYS", {
                url: this.config.calendarUrl,
                id: this.identifier
            });
        } else {
            // No external calendar, mark as loaded
            this.loaded = true;
        }
    },

    loadCustomHolidays: function () {
        if (this.config.backendApiUrl) {
            this.sendSocketNotification("FETCH_CUSTOM_HOLIDAYS", {
                url: this.config.backendApiUrl,
                id: this.identifier
            });
        }
    },

    // Calculate date for rule-based holidays (e.g., 2nd Monday of March)
    calculateRuleBasedDate: function (rule, year) {
        const month = rule.month - 1; // 0-indexed
        const weekday = rule.weekday; // 0=Monday, 6=Sunday
        const ordinal = rule.ordinal;

        // Convert weekday: our 0=Monday, JS 0=Sunday
        const jsWeekday = (weekday + 1) % 7;

        if (ordinal === -1) {
            // Last occurrence
            const lastDay = new Date(year, month + 1, 0);
            let day = lastDay.getDate();
            while (new Date(year, month, day).getDay() !== jsWeekday) {
                day--;
            }
            return { year, month: month + 1, day };
        } else {
            // Nth occurrence
            let count = 0;
            for (let day = 1; day <= 31; day++) {
                const date = new Date(year, month, day);
                if (date.getMonth() !== month) break;
                if (date.getDay() === jsWeekday) {
                    count++;
                    if (count === ordinal) {
                        return { year, month: month + 1, day };
                    }
                }
            }
        }
        return null;
    },

    addCustomHoliday: function (holiday) {
        const currentYear = this.currentDate.getFullYear();
        const isVi = this.config.language === "vi";
        const name = (isVi && holiday.nameVi) ? holiday.nameVi : holiday.name;

        // If API provides precomputed date, use it directly (handles Giao Thua correctly)
        if (holiday.date) {
            const dateParts = holiday.date.split('-');
            const year = parseInt(dateParts[0]);
            const month = parseInt(dateParts[1]) - 1; // JS months are 0-indexed
            const day = parseInt(dateParts[2]);

            // Only add if in range of current year +/- 1
            if (year >= currentYear - 1 && year <= currentYear + 1) {
                const dateKey = this.getDateKey(year, month, day);
                this.addHoliday(dateKey, name);
            }
            return;
        }

        // Fallback: compute dates locally for holidays without precomputed date
        const years = [currentYear - 1, currentYear, currentYear + 1];

        years.forEach(year => {
            let dateKey = null;

            if (holiday.type === "solar") {
                dateKey = this.getDateKey(year, holiday.month - 1, holiday.day);
            } else if (holiday.type === "lunar" && typeof LunarCalendar !== 'undefined') {
                // Special handling for Giao Thua (month 12, day 30)
                if (holiday.lunarMonth === 12 && holiday.lunarDay === 30) {
                    // Check if day 30 exists, otherwise use day 29
                    const solar30 = LunarCalendar.getSolarDate(30, 12, year, false);
                    if (solar30 && solar30.day > 0) {
                        const verify = LunarCalendar.getLunarDate(solar30.day, solar30.month, solar30.year);
                        if (verify.month === 12 && verify.day === 30) {
                            dateKey = this.getDateKey(solar30.year, solar30.month - 1, solar30.day);
                        } else {
                            // Month 12 has only 29 days
                            const solar29 = LunarCalendar.getSolarDate(29, 12, year, false);
                            if (solar29 && solar29.day > 0) {
                                dateKey = this.getDateKey(solar29.year, solar29.month - 1, solar29.day);
                            }
                        }
                    } else {
                        const solar29 = LunarCalendar.getSolarDate(29, 12, year, false);
                        if (solar29 && solar29.day > 0) {
                            dateKey = this.getDateKey(solar29.year, solar29.month - 1, solar29.day);
                        }
                    }
                } else {
                    const solar = LunarCalendar.getSolarDate(holiday.lunarDay, holiday.lunarMonth, year, false);
                    if (solar && solar.day > 0) {
                        dateKey = this.getDateKey(solar.year, solar.month - 1, solar.day);
                    }
                }
            } else if (holiday.type === "specific" && holiday.year === year) {
                dateKey = this.getDateKey(year, holiday.month - 1, holiday.day);
            } else if (holiday.type === "rule" && holiday.rule) {
                const ruleDate = this.calculateRuleBasedDate(holiday.rule, year);
                if (ruleDate) {
                    dateKey = this.getDateKey(ruleDate.year, ruleDate.month - 1, ruleDate.day);
                }
            }

            if (dateKey) {
                this.addHoliday(dateKey, name);
            }
        });
    },

    scheduleUpdate: function () {
        const self = this;

        // Refresh ICS calendar at fetchInterval (default 7 days)
        if (this.config.calendarUrl) {
            setInterval(function () {
                self.loadHolidays();
            }, this.config.fetchInterval);
        }

        // Refresh custom holidays from backend more frequently (5 minutes)
        if (this.config.backendApiUrl) {
            const refreshInterval = this.config.backendRefreshInterval || 5 * 60 * 1000; // 5 minutes
            setInterval(function () {
                // Clear existing custom holidays and reload
                self.holidays = {};
                if (!self.config.backendApiUrl) {
                    self.addExtraHolidays();
                    self.addLunarHolidays();
                }
                self.loadCustomHolidays();
            }, refreshInterval);
        }

        const now = new Date();
        const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        const msUntilMidnight = tomorrow - now;

        setTimeout(function () {
            self.currentDate = new Date();
            self.updateDom(0);
            setInterval(function () {
                self.currentDate = new Date();
                self.updateDom(0);
            }, 24 * 60 * 60 * 1000);
        }, msUntilMidnight);
    },

    translateHolidayName: function (name) {
        if (this.config.language !== "vi") return name;
        name = name.replace(/^Vietnam:\s*/i, "");
        for (const [en, vi] of Object.entries(this.holidayTranslations)) {
            if (name.toLowerCase().includes(en.toLowerCase())) {
                return vi;
            }
        }
        return name;
    },

    parseICS: function (icsData) {
        const holidays = {};
        const lines = icsData.split(/\r?\n/);
        let currentEvent = null;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            if (line === "BEGIN:VEVENT") {
                currentEvent = {};
            } else if (line === "END:VEVENT" && currentEvent) {
                if (currentEvent.date && currentEvent.name) {
                    // Filter out Tet-related holidays (already handled by lunar.js)
                    const tetFilters = ["Tet Holiday", "Tet Eve", "Tet Nguyen Dan"];
                    const isTetHoliday = tetFilters.some(f => currentEvent.name.includes(f));
                    if (!isTetHoliday) {
                        const dateKey = currentEvent.date;
                        if (!holidays[dateKey]) {
                            holidays[dateKey] = [];
                        }
                        holidays[dateKey].push({
                            name: this.translateHolidayName(currentEvent.name),
                            originalName: currentEvent.name
                        });
                    }
                }
                currentEvent = null;
            } else if (currentEvent) {
                if (line.startsWith("DTSTART")) {
                    const match = line.match(/(\d{4})(\d{2})(\d{2})/);
                    if (match) {
                        currentEvent.date = `${match[1]}-${match[2]}-${match[3]}`;
                    }
                } else if (line.startsWith("SUMMARY")) {
                    currentEvent.name = line.replace(/^SUMMARY[^:]*:/, "").trim();
                }
            }
        }

        return holidays;
    },

    socketNotificationReceived: function (notification, payload) {
        if (notification === "HOLIDAYS_FETCHED" && payload.id === this.identifier) {
            // Merge fetched holidays with local extras (don't replace)
            const fetchedHolidays = this.parseICS(payload.data);
            for (const [dateKey, holidays] of Object.entries(fetchedHolidays)) {
                if (!this.holidays[dateKey]) {
                    this.holidays[dateKey] = [];
                }
                // Add fetched holidays that don't already exist
                holidays.forEach(holiday => {
                    const exists = this.holidays[dateKey].some(h => h.name === holiday.name);
                    if (!exists) {
                        this.holidays[dateKey].push(holiday);
                    }
                });
            }
            this.loaded = true;
            this.updateDom(0);
        } else if (notification === "FETCH_ERROR" && payload.id === this.identifier) {
            Log.warn("Could not fetch holidays from server, using local holidays only");
            this.loaded = true;
            this.updateDom(0);
        } else if (notification === "CUSTOM_HOLIDAYS_FETCHED" && payload.id === this.identifier) {
            // Add custom holidays from backend API
            payload.data.forEach(holiday => {
                this.addCustomHoliday(holiday);
            });
            this.updateDom(0);
        } else if (notification === "CUSTOM_HOLIDAYS_ERROR" && payload.id === this.identifier) {
            Log.warn("Could not fetch custom holidays from backend API:", payload.error);
        }
    },

    notificationReceived: function (notification, payload, sender) {
        if (notification === "TOUCH_SWIPE_LEFT") {
            this.monthIndex++;
            this.updateDom(0);
        } else if (notification === "TOUCH_SWIPE_RIGHT") {
            this.monthIndex--;
            this.updateDom(0);
        }
    }
});
