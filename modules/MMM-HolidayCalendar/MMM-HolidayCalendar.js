/* MMM-HolidayCalendar
 * A grid-style desk calendar module for MagicMirror²
 * Supports Vietnamese holidays and touch gestures for month navigation
 */

Module.register("MMM-HolidayCalendar", {
    defaults: {
        calendarUrl: "https://www.officeholidays.com/ics/vietnam",
        fetchInterval: 7 * 24 * 60 * 60 * 1000, // 7 days
        language: "vi", // "vi" for Vietnamese, "en" for English
        showWeekNumbers: false,
        highlightToday: true,
        animationSpeed: 300,
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

    // Holiday name translations
    holidayTranslations: {
        "Tet Eve": "Giao thừa",
        "Tet Nguyen Dan": "Tết Nguyên Đán",
        "Tet Holiday": "Nghỉ Tết",
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

    start: function () {
        Log.info("Starting module: " + this.name);
        this.holidays = {};
        this.currentDate = new Date();
        this.viewDate = new Date();
        this.loaded = false;

        // Touch handling
        this.touchStartX = 0;
        this.touchEndX = 0;

        this.loadHolidays();
        this.scheduleUpdate();
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

        // Build calendar
        wrapper.appendChild(this.buildHeader());
        wrapper.appendChild(this.buildCalendar());
        wrapper.appendChild(this.buildHolidayList());

        // Add touch event listeners
        this.addTouchListeners(wrapper);

        return wrapper;
    },

    buildHeader: function () {
        const header = document.createElement("div");
        header.className = "calendar-header";

        const isVi = this.config.language === "vi";
        const monthNames = isVi ? this.monthNamesVi : this.monthNamesEn;

        const monthYear = document.createElement("div");
        monthYear.className = "month-year";
        monthYear.innerHTML = `${monthNames[this.viewDate.getMonth()]} ${this.viewDate.getFullYear()}`;

        const navHint = document.createElement("div");
        navHint.className = "nav-hint";
        navHint.innerHTML = isVi ? "Vuốt để đổi tháng" : "Swipe to change month";

        header.appendChild(monthYear);
        header.appendChild(navHint);

        return header;
    },

    buildCalendar: function () {
        const calendar = document.createElement("div");
        calendar.className = "calendar-grid";

        const isVi = this.config.language === "vi";
        const dayNames = isVi ? this.dayNamesVi : this.dayNamesEn;

        // Day headers
        const dayHeader = document.createElement("div");
        dayHeader.className = "day-header-row";
        dayNames.forEach((day, index) => {
            const dayCell = document.createElement("div");
            dayCell.className = "day-header";
            if (index === 0) dayCell.classList.add("sunday");
            if (index === 6) dayCell.classList.add("saturday");
            dayCell.textContent = day;
            dayHeader.appendChild(dayCell);
        });
        calendar.appendChild(dayHeader);

        // Get calendar data
        const year = this.viewDate.getFullYear();
        const month = this.viewDate.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDay = firstDay.getDay();
        const daysInMonth = lastDay.getDate();

        // Previous month days
        const prevMonthLastDay = new Date(year, month, 0).getDate();

        // Build weeks
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
                    // Previous month
                    const prevDay = prevMonthLastDay - startDay + cellIndex + 1;
                    dayCell.textContent = prevDay;
                    dayCell.classList.add("other-month");
                } else if (dayCount <= daysInMonth) {
                    // Current month
                    dayCell.textContent = dayCount;

                    // Check if today
                    if (this.config.highlightToday &&
                        year === this.currentDate.getFullYear() &&
                        month === this.currentDate.getMonth() &&
                        dayCount === this.currentDate.getDate()) {
                        dayCell.classList.add("today");
                    }

                    // Check if holiday
                    const dateKey = this.getDateKey(year, month, dayCount);
                    if (this.holidays[dateKey]) {
                        dayCell.classList.add("holiday");
                        dayCell.title = this.holidays[dateKey].map(h => h.name).join(", ");
                    }

                    // Sunday/Saturday styling
                    if (dayOfWeek === 0) dayCell.classList.add("sunday");
                    if (dayOfWeek === 6) dayCell.classList.add("saturday");

                    dayCount++;
                } else {
                    // Next month
                    dayCell.textContent = nextMonthDay;
                    dayCell.classList.add("other-month");
                    nextMonthDay++;
                }

                weekRow.appendChild(dayCell);
            }

            calendar.appendChild(weekRow);

            // Stop if we've finished the month and started next
            if (dayCount > daysInMonth && week >= 4) break;
        }

        return calendar;
    },

    buildHolidayList: function () {
        const listContainer = document.createElement("div");
        listContainer.className = "holiday-list";

        const year = this.viewDate.getFullYear();
        const month = this.viewDate.getMonth();

        // Get holidays for current view month
        const monthHolidays = [];
        for (let day = 1; day <= 31; day++) {
            const dateKey = this.getDateKey(year, month, day);
            if (this.holidays[dateKey]) {
                this.holidays[dateKey].forEach(holiday => {
                    monthHolidays.push({
                        day: day,
                        ...holiday
                    });
                });
            }
        }

        if (monthHolidays.length === 0) {
            const noHoliday = document.createElement("div");
            noHoliday.className = "no-holiday";
            noHoliday.textContent = this.config.language === "vi"
                ? "Không có ngày lễ trong tháng này"
                : "No holidays this month";
            listContainer.appendChild(noHoliday);
        } else {
            monthHolidays.forEach(holiday => {
                const item = document.createElement("div");
                item.className = "holiday-item";

                const daySpan = document.createElement("span");
                daySpan.className = "holiday-day";
                daySpan.textContent = holiday.day;

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

    addTouchListeners: function (wrapper) {
        const self = this;
        const threshold = 50;

        wrapper.addEventListener("touchstart", function (e) {
            self.touchStartX = e.changedTouches[0].screenX;
        }, { passive: true });

        wrapper.addEventListener("touchend", function (e) {
            self.touchEndX = e.changedTouches[0].screenX;
            self.handleSwipe();
        }, { passive: true });

        // Mouse support for testing
        let mouseDown = false;
        wrapper.addEventListener("mousedown", function (e) {
            mouseDown = true;
            self.touchStartX = e.screenX;
        });

        wrapper.addEventListener("mouseup", function (e) {
            if (mouseDown) {
                self.touchEndX = e.screenX;
                self.handleSwipe();
                mouseDown = false;
            }
        });

        wrapper.addEventListener("mouseleave", function () {
            mouseDown = false;
        });
    },

    handleSwipe: function () {
        const diff = this.touchEndX - this.touchStartX;
        const threshold = 50;

        if (Math.abs(diff) > threshold) {
            if (diff > 0) {
                // Swipe right - previous month
                this.prevMonth();
            } else {
                // Swipe left - next month
                this.nextMonth();
            }
        }
    },

    prevMonth: function () {
        this.viewDate.setMonth(this.viewDate.getMonth() - 1);
        this.refreshCalendar();
    },

    nextMonth: function () {
        this.viewDate.setMonth(this.viewDate.getMonth() + 1);
        this.refreshCalendar();
    },

    refreshCalendar: function () {
        // Update DOM directly without flash
        const wrapper = document.getElementById("holiday-calendar-" + this.identifier);
        if (wrapper) {
            wrapper.innerHTML = '';
            wrapper.appendChild(this.buildHeader());
            wrapper.appendChild(this.buildCalendar());
            wrapper.appendChild(this.buildHolidayList());
            this.addTouchListeners(wrapper);
        }
    },

    getDateKey: function (year, month, day) {
        return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    },

    loadHolidays: function () {
        this.sendSocketNotification("FETCH_HOLIDAYS", {
            url: this.config.calendarUrl,
            id: this.identifier
        });
    },

    scheduleUpdate: function () {
        const self = this;
        setInterval(function () {
            self.loadHolidays();
        }, this.config.fetchInterval);

        // Update current date at midnight
        const now = new Date();
        const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        const msUntilMidnight = tomorrow - now;

        setTimeout(function () {
            self.currentDate = new Date();
            self.updateDom(self.config.animationSpeed);
            // Then update every 24 hours
            setInterval(function () {
                self.currentDate = new Date();
                self.updateDom(self.config.animationSpeed);
            }, 24 * 60 * 60 * 1000);
        }, msUntilMidnight);
    },

    translateHolidayName: function (name) {
        if (this.config.language !== "vi") return name;

        // Remove "Vietnam: " prefix
        name = name.replace(/^Vietnam:\s*/i, "");

        // Check for direct translation
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
                    const dateKey = currentEvent.date;
                    if (!holidays[dateKey]) {
                        holidays[dateKey] = [];
                    }
                    holidays[dateKey].push({
                        name: this.translateHolidayName(currentEvent.name),
                        originalName: currentEvent.name
                    });
                }
                currentEvent = null;
            } else if (currentEvent) {
                if (line.startsWith("DTSTART")) {
                    // Handle both DTSTART:20260216 and DTSTART;VALUE=DATE:20260216
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
            this.holidays = this.parseICS(payload.data);
            this.loaded = true;
            this.updateDom(this.config.animationSpeed);
        } else if (notification === "FETCH_ERROR" && payload.id === this.identifier) {
            Log.error("Error fetching holidays:", payload.error);
            this.loaded = true;
            this.updateDom(this.config.animationSpeed);
        }
    },

    notificationReceived: function (notification, payload, sender) {
        // Handle touch module integration
        if (notification === "TOUCH_SWIPE_LEFT") {
            this.nextMonth();
        } else if (notification === "TOUCH_SWIPE_RIGHT") {
            this.prevMonth();
        }
    }
});
