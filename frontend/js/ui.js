/**
 * UI module for DOM manipulation and rendering.
 */

const UI = {
    // Cache DOM elements
    elements: {},

    /**
     * Initialize DOM element references.
     */
    init() {
        this.elements = {
            holidayList: document.getElementById('holidayList'),
            searchInput: document.getElementById('searchInput'),
            addHolidayBtn: document.getElementById('addHolidayBtn'),
            modalOverlay: document.getElementById('modalOverlay'),
            modalTitle: document.getElementById('modalTitle'),
            modalClose: document.getElementById('modalClose'),
            holidayForm: document.getElementById('holidayForm'),
            cancelBtn: document.getElementById('cancelBtn'),
            toast: document.getElementById('toast'),
            apiUrl: document.getElementById('apiUrl'),
            saveApiUrl: document.getElementById('saveApiUrl'),
            testConnection: document.getElementById('testConnection'),
            filterTabs: document.querySelectorAll('.filter-tab'),

            // Form fields
            holidayId: document.getElementById('holidayId'),
            holidayName: document.getElementById('holidayName'),
            holidayNameVi: document.getElementById('holidayNameVi'),
            holidayType: document.getElementById('holidayType'),
            holidayRecurring: document.getElementById('holidayRecurring'),
            solarMonth: document.getElementById('solarMonth'),
            solarDay: document.getElementById('solarDay'),
            solarYear: document.getElementById('solarYear'),
            lunarMonth: document.getElementById('lunarMonth'),
            lunarDay: document.getElementById('lunarDay'),
            ruleOrdinal: document.getElementById('ruleOrdinal'),
            ruleWeekday: document.getElementById('ruleWeekday'),
            ruleMonth: document.getElementById('ruleMonth')
        };

        // Initialize API URL from config
        this.elements.apiUrl.value = Config.apiUrl;
    },

    /**
     * Show loading state in the holiday list.
     */
    showLoading() {
        this.elements.holidayList.innerHTML = '<div class="loading">Loading holidays...</div>';
    },

    /**
     * Show error message in the holiday list.
     */
    showError(message) {
        this.elements.holidayList.innerHTML = `
            <div class="empty-state">
                <h3>Error</h3>
                <p>${message}</p>
            </div>
        `;
    },

    /**
     * Render the holiday list.
     */
    renderHolidays(holidays) {
        if (!holidays || holidays.length === 0) {
            this.elements.holidayList.innerHTML = `
                <div class="empty-state">
                    <h3>No holidays found</h3>
                    <p>Click "Add Holiday" to create your first holiday.</p>
                </div>
            `;
            return;
        }

        const html = holidays.map(holiday => this.renderHolidayCard(holiday)).join('');
        this.elements.holidayList.innerHTML = html;
    },

    /**
     * Render a single holiday card.
     */
    renderHolidayCard(holiday) {
        const dateDisplay = this.getDateDisplay(holiday);
        const nameVi = holiday.nameVi ? `<div class="holiday-name-vi">${holiday.nameVi}</div>` : '';

        return `
            <div class="holiday-card" data-id="${holiday.id}" data-type="${holiday.type}">
                <div class="holiday-type-badge ${holiday.type}">
                    ${holiday.type.substring(0, 3)}
                </div>
                <div class="holiday-info">
                    <div class="holiday-name">${holiday.name}</div>
                    ${nameVi}
                    <div class="holiday-date">${dateDisplay}</div>
                </div>
                <div class="holiday-actions">
                    <button class="btn btn-edit" data-action="edit" data-id="${holiday.id}">Edit</button>
                    <button class="btn btn-delete" data-action="delete" data-id="${holiday.id}">Delete</button>
                </div>
            </div>
        `;
    },

    /**
     * Get display text for holiday date.
     */
    getDateDisplay(holiday) {
        switch (holiday.type) {
            case 'solar':
                return `${Config.months[holiday.month - 1]} ${holiday.day}`;
            case 'lunar':
                return `Lunar: ${Config.lunarMonths[holiday.lunarMonth - 1]} ${holiday.lunarDay}`;
            case 'specific':
                return `${Config.months[holiday.month - 1]} ${holiday.day}, ${holiday.year}`;
            case 'rule':
                if (holiday.rule) {
                    const ordinal = Config.ordinals[holiday.rule.ordinal] || holiday.rule.ordinal;
                    const weekday = Config.weekdays[holiday.rule.weekday];
                    const month = Config.months[holiday.rule.month - 1];
                    return `${ordinal} ${weekday} of ${month}`;
                }
                return 'Rule-based';
            default:
                return '';
        }
    },

    /**
     * Show the modal for adding/editing.
     */
    showModal(title = 'Add Holiday') {
        this.elements.modalTitle.textContent = title;
        this.elements.modalOverlay.classList.add('active');
    },

    /**
     * Hide the modal.
     */
    hideModal() {
        this.elements.modalOverlay.classList.remove('active');
        this.resetForm();
    },

    /**
     * Reset the form to default state.
     */
    resetForm() {
        this.elements.holidayForm.reset();
        this.elements.holidayId.value = '';
        this.updateFormFields('solar');
    },

    /**
     * Update form field visibility based on type.
     */
    updateFormFields(type) {
        const solarFields = document.querySelector('.solar-fields');
        const lunarFields = document.querySelector('.lunar-fields');
        const ruleFields = document.querySelector('.rule-fields');
        const yearField = document.querySelector('.year-field');

        // Hide all first
        solarFields.style.display = 'none';
        lunarFields.style.display = 'none';
        ruleFields.style.display = 'none';
        yearField.style.display = 'none';

        // Show based on type
        switch (type) {
            case 'solar':
                solarFields.style.display = 'flex';
                break;
            case 'lunar':
                lunarFields.style.display = 'flex';
                break;
            case 'specific':
                solarFields.style.display = 'flex';
                yearField.style.display = 'block';
                break;
            case 'rule':
                ruleFields.style.display = 'block';
                break;
        }
    },

    /**
     * Populate form with holiday data for editing.
     */
    populateForm(holiday) {
        this.elements.holidayId.value = holiday.id;
        this.elements.holidayName.value = holiday.name;
        this.elements.holidayNameVi.value = holiday.nameVi || '';
        this.elements.holidayType.value = holiday.type;
        this.elements.holidayRecurring.checked = holiday.recurring !== false;

        this.updateFormFields(holiday.type);

        if (holiday.type === 'solar' || holiday.type === 'specific') {
            this.elements.solarMonth.value = holiday.month || 1;
            this.elements.solarDay.value = holiday.day || 1;
            if (holiday.year) {
                this.elements.solarYear.value = holiday.year;
            }
        } else if (holiday.type === 'lunar') {
            this.elements.lunarMonth.value = holiday.lunarMonth || 1;
            this.elements.lunarDay.value = holiday.lunarDay || 1;
        } else if (holiday.type === 'rule' && holiday.rule) {
            this.elements.ruleOrdinal.value = holiday.rule.ordinal;
            this.elements.ruleWeekday.value = holiday.rule.weekday;
            this.elements.ruleMonth.value = holiday.rule.month;
        }
    },

    /**
     * Get form data as an object.
     */
    getFormData() {
        const type = this.elements.holidayType.value;

        const data = {
            name: this.elements.holidayName.value.trim(),
            nameVi: this.elements.holidayNameVi.value.trim() || null,
            type: type,
            recurring: this.elements.holidayRecurring.checked
        };

        // Add ID if editing
        if (this.elements.holidayId.value) {
            data.id = this.elements.holidayId.value;
        }

        // Add type-specific fields
        if (type === 'solar') {
            data.month = parseInt(this.elements.solarMonth.value);
            data.day = parseInt(this.elements.solarDay.value);
        } else if (type === 'lunar') {
            data.lunarMonth = parseInt(this.elements.lunarMonth.value);
            data.lunarDay = parseInt(this.elements.lunarDay.value);
        } else if (type === 'specific') {
            data.month = parseInt(this.elements.solarMonth.value);
            data.day = parseInt(this.elements.solarDay.value);
            data.year = parseInt(this.elements.solarYear.value);
            data.recurring = false;
        } else if (type === 'rule') {
            data.rule = {
                ordinal: parseInt(this.elements.ruleOrdinal.value),
                weekday: parseInt(this.elements.ruleWeekday.value),
                month: parseInt(this.elements.ruleMonth.value)
            };
        }

        return data;
    },

    /**
     * Show toast notification.
     */
    showToast(message, type = 'success') {
        const toast = this.elements.toast;
        toast.textContent = message;
        toast.className = `toast ${type} show`;

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    },

    /**
     * Set active filter tab.
     */
    setActiveFilter(filter) {
        this.elements.filterTabs.forEach(tab => {
            if (tab.dataset.filter === filter) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });
    },

    /**
     * Filter displayed holidays by type.
     */
    filterHolidays(type) {
        const cards = this.elements.holidayList.querySelectorAll('.holiday-card');

        cards.forEach(card => {
            if (type === 'all' || card.dataset.type === type) {
                card.style.display = 'flex';
            } else {
                card.style.display = 'none';
            }
        });
    }
};
