/* MMM-HolidayCalendar
 * A grid-style desk calendar module for MagicMirror²
 * Supports Vietnamese holidays and touch gestures for month navigation
 * Infinity scroll carousel style
 */

Module.register("MMM-HolidayCalendar", {
    defaults: {
        calendarUrl: "https://www.officeholidays.com/ics/vietnam",
        fetchInterval: 7 * 24 * 60 * 60 * 1000, // 7 days
        language: "vi", // "vi" for Vietnamese, "en" for English
        highlightToday: true,
        panelWidth: 280, // Width of each month panel
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

    // Extra international holidays popular in Vietnam (fixed dates)
    // Format: { month: day } or { month: [day1, day2] }
    extraHolidaysVi: [
        { month: 1, day: 1, name: "Tết Dương lịch" },
        { month: 2, day: 14, name: "Lễ tình nhân" },
        { month: 3, day: 8, name: "Quốc tế Phụ nữ" },
        { month: 4, day: 1, name: "Cá tháng Tư" },
        { month: 4, day: 22, name: "Ngày Trái Đất" },
        { month: 5, day: 1, name: "Quốc tế Lao động" },
        { month: 6, day: 1, name: "Quốc tế Thiếu nhi" },
        { month: 6, day: 21, name: "Ngày của Cha" },
        { month: 10, day: 20, name: "Ngày Phụ nữ VN" },
        { month: 10, day: 31, name: "Halloween" },
        { month: 11, day: 20, name: "Ngày Nhà giáo VN" },
        { month: 12, day: 24, name: "Đêm Giáng sinh" },
        { month: 12, day: 25, name: "Giáng sinh" },
        { month: 12, day: 31, name: "Đêm Giao thừa" }
    ],

    extraHolidaysEn: [
        { month: 1, day: 1, name: "New Year's Day" },
        { month: 2, day: 14, name: "Valentine's Day" },
        { month: 3, day: 8, name: "Women's Day" },
        { month: 4, day: 1, name: "April Fools' Day" },
        { month: 4, day: 22, name: "Earth Day" },
        { month: 5, day: 1, name: "Labour Day" },
        { month: 6, day: 1, name: "Children's Day" },
        { month: 6, day: 21, name: "Father's Day" },
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
        this.viewDate = new Date();
        this.loaded = false;

        // Drag state
        this.isDragging = false;
        this.dragStartX = 0;
        this.currentOffset = 0;

        // Add extra holidays first
        this.addExtraHolidays();

        this.loadHolidays();
        this.scheduleUpdate();
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
                // Check if this holiday already exists
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

        // Create carousel container
        const viewport = document.createElement("div");
        viewport.className = "calendar-viewport";

        const track = document.createElement("div");
        track.className = "calendar-track";

        // Build 3 panels: prev, current, next
        const prevDate = new Date(this.viewDate);
        prevDate.setMonth(prevDate.getMonth() - 1);

        const nextDate = new Date(this.viewDate);
        nextDate.setMonth(nextDate.getMonth() + 1);

        track.appendChild(this.buildPanel(prevDate, "prev"));
        track.appendChild(this.buildPanel(this.viewDate, "current"));
        track.appendChild(this.buildPanel(nextDate, "next"));

        viewport.appendChild(track);
        wrapper.appendChild(viewport);

        // Add touch event listeners
        this.addTouchListeners(wrapper, track);

        return wrapper;
    },

    buildPanel: function (date, position) {
        const panel = document.createElement("div");
        panel.className = "calendar-panel " + position;

        // Header
        const header = document.createElement("div");
        header.className = "calendar-header";

        const isVi = this.config.language === "vi";
        const monthNames = isVi ? this.monthNamesVi : this.monthNamesEn;

        const monthYear = document.createElement("div");
        monthYear.className = "month-year";
        monthYear.innerHTML = `${monthNames[date.getMonth()]} ${date.getFullYear()}`;

        header.appendChild(monthYear);
        panel.appendChild(header);

        // Calendar grid
        panel.appendChild(this.buildCalendarGrid(date));

        // Holiday list
        panel.appendChild(this.buildHolidayList(date));

        return panel;
    },

    buildCalendarGrid: function (viewDate) {
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
        const year = viewDate.getFullYear();
        const month = viewDate.getMonth();
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
                    dayCell.textContent = dayCount;

                    if (this.config.highlightToday &&
                        year === this.currentDate.getFullYear() &&
                        month === this.currentDate.getMonth() &&
                        dayCount === this.currentDate.getDate()) {
                        dayCell.classList.add("today");
                    }

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
                    monthHolidays.push({ day: day, ...holiday });
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
            monthHolidays.slice(0, 3).forEach(holiday => {
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

            if (monthHolidays.length > 3) {
                const more = document.createElement("div");
                more.className = "holiday-more";
                more.textContent = `+${monthHolidays.length - 3} ${this.config.language === "vi" ? "ngày khác" : "more"}`;
                listContainer.appendChild(more);
            }
        }

        return listContainer;
    },

    addTouchListeners: function (wrapper, track) {
        const self = this;
        const panelWidth = this.config.panelWidth;

        const updatePosition = (offset, animate) => {
            track.style.transition = animate ? 'transform 0.3s ease' : 'none';
            track.style.transform = `translateX(${-panelWidth + offset}px)`;
        };

        // Initialize position (show middle panel)
        updatePosition(0, false);

        // Touch events
        wrapper.addEventListener("touchstart", function (e) {
            self.isDragging = true;
            self.dragStartX = e.changedTouches[0].screenX;
            self.currentOffset = 0;
            track.style.transition = 'none';
        }, { passive: true });

        wrapper.addEventListener("touchmove", function (e) {
            if (self.isDragging) {
                self.currentOffset = e.changedTouches[0].screenX - self.dragStartX;
                updatePosition(self.currentOffset, false);
            }
        }, { passive: true });

        wrapper.addEventListener("touchend", function (e) {
            if (self.isDragging) {
                self.isDragging = false;
                self.handleDragEnd(track, panelWidth);
            }
        }, { passive: true });

        // Mouse events
        wrapper.addEventListener("mousedown", function (e) {
            self.isDragging = true;
            self.dragStartX = e.screenX;
            self.currentOffset = 0;
            track.style.transition = 'none';
            e.preventDefault();
        });

        wrapper.addEventListener("mousemove", function (e) {
            if (self.isDragging) {
                self.currentOffset = e.screenX - self.dragStartX;
                updatePosition(self.currentOffset, false);
            }
        });

        wrapper.addEventListener("mouseup", function (e) {
            if (self.isDragging) {
                self.isDragging = false;
                self.handleDragEnd(track, panelWidth);
            }
        });

        wrapper.addEventListener("mouseleave", function () {
            if (self.isDragging) {
                self.isDragging = false;
                self.handleDragEnd(track, panelWidth);
            }
        });
    },

    handleDragEnd: function (track, panelWidth) {
        const threshold = panelWidth * 0.3; // 30% of panel width to trigger change

        if (this.currentOffset > threshold) {
            // Go to previous month
            track.style.transition = 'transform 0.3s ease';
            track.style.transform = `translateX(0px)`;

            setTimeout(() => {
                this.viewDate.setMonth(this.viewDate.getMonth() - 1);
                this.updateDom(0);
            }, 300);
        } else if (this.currentOffset < -threshold) {
            // Go to next month
            track.style.transition = 'transform 0.3s ease';
            track.style.transform = `translateX(${-panelWidth * 2}px)`;

            setTimeout(() => {
                this.viewDate.setMonth(this.viewDate.getMonth() + 1);
                this.updateDom(0);
            }, 300);
        } else {
            // Snap back to current
            track.style.transition = 'transform 0.3s ease';
            track.style.transform = `translateX(${-panelWidth}px)`;
        }

        this.currentOffset = 0;
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
        }
    },

    notificationReceived: function (notification, payload, sender) {
        if (notification === "TOUCH_SWIPE_LEFT") {
            this.viewDate.setMonth(this.viewDate.getMonth() + 1);
            this.updateDom(0);
        } else if (notification === "TOUCH_SWIPE_RIGHT") {
            this.viewDate.setMonth(this.viewDate.getMonth() - 1);
            this.updateDom(0);
        }
    }
});
