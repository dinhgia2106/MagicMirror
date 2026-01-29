/**
 * Main application module.
 * Handles event binding and application flow.
 */

const App = {
    holidays: [],
    currentFilter: 'all',

    /**
     * Initialize the application.
     */
    async init() {
        await Config.load();
        UI.init();
        this.bindEvents();
        await this.loadHolidays();
    },

    /**
     * Bind all event listeners.
     */
    bindEvents() {
        // Add holiday button
        UI.elements.addHolidayBtn.addEventListener('click', () => this.openAddModal());

        // Modal close
        UI.elements.modalClose.addEventListener('click', () => UI.hideModal());
        UI.elements.cancelBtn.addEventListener('click', () => UI.hideModal());
        UI.elements.modalOverlay.addEventListener('click', (e) => {
            if (e.target === UI.elements.modalOverlay) {
                UI.hideModal();
            }
        });

        // Form submission
        UI.elements.holidayForm.addEventListener('submit', (e) => this.handleFormSubmit(e));

        // Type change
        UI.elements.holidayType.addEventListener('change', (e) => {
            UI.updateFormFields(e.target.value);
        });

        // Holiday list actions (edit/delete)
        UI.elements.holidayList.addEventListener('click', (e) => {
            const action = e.target.dataset.action;
            const id = e.target.dataset.id;

            if (action === 'edit') {
                this.openEditModal(id);
            } else if (action === 'delete') {
                this.deleteHoliday(id);
            }
        });

        // Search
        let searchTimeout;
        UI.elements.searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.searchHolidays(e.target.value);
            }, 300);
        });

        // Filter tabs
        UI.elements.filterTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const filter = tab.dataset.filter;
                this.currentFilter = filter;
                UI.setActiveFilter(filter);
                UI.filterHolidays(filter);
            });
        });

        // API URL settings
        UI.elements.saveApiUrl.addEventListener('click', () => this.saveApiUrl());
        UI.elements.testConnection.addEventListener('click', () => this.testConnection());

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                UI.hideModal();
            }
        });
    },

    /**
     * Load all holidays from the API.
     */
    async loadHolidays() {
        UI.showLoading();

        try {
            const response = await Api.getHolidays();
            this.holidays = response.data || [];
            UI.renderHolidays(this.holidays);

            // Re-apply filter
            if (this.currentFilter !== 'all') {
                UI.filterHolidays(this.currentFilter);
            }
        } catch (error) {
            console.error('Failed to load holidays:', error);
            UI.showError(error.message);
        }
    },

    /**
     * Search holidays.
     */
    async searchHolidays(query) {
        if (!query.trim()) {
            UI.renderHolidays(this.holidays);
            UI.filterHolidays(this.currentFilter);
            return;
        }

        try {
            const response = await Api.getHolidays(query);
            UI.renderHolidays(response.data || []);
            UI.filterHolidays(this.currentFilter);
        } catch (error) {
            console.error('Search failed:', error);
            UI.showToast('Search failed: ' + error.message, 'error');
        }
    },

    /**
     * Open modal for adding a new holiday.
     */
    openAddModal() {
        UI.resetForm();
        UI.showModal('Add Holiday');
    },

    /**
     * Open modal for editing a holiday.
     */
    async openEditModal(id) {
        try {
            const response = await Api.getHoliday(id);
            UI.populateForm(response.data);
            UI.showModal('Edit Holiday');
        } catch (error) {
            console.error('Failed to load holiday:', error);
            UI.showToast('Failed to load holiday: ' + error.message, 'error');
        }
    },

    /**
     * Handle form submission.
     */
    async handleFormSubmit(e) {
        e.preventDefault();

        const data = UI.getFormData();
        const isEditing = !!data.id;

        try {
            if (isEditing) {
                await Api.updateHoliday(data.id, data);
                UI.showToast('Holiday updated successfully');
            } else {
                await Api.createHoliday(data);
                UI.showToast('Holiday created successfully');
            }

            UI.hideModal();
            await this.loadHolidays();
        } catch (error) {
            console.error('Failed to save holiday:', error);
            UI.showToast('Failed to save: ' + error.message, 'error');
        }
    },

    /**
     * Delete a holiday.
     */
    async deleteHoliday(id) {
        if (!confirm('Are you sure you want to delete this holiday?')) {
            return;
        }

        try {
            await Api.deleteHoliday(id);
            UI.showToast('Holiday deleted');
            await this.loadHolidays();
        } catch (error) {
            console.error('Failed to delete holiday:', error);
            UI.showToast('Failed to delete: ' + error.message, 'error');
        }
    },

    /**
     * Save API URL.
     */
    saveApiUrl() {
        const url = UI.elements.apiUrl.value.trim();
        if (url) {
            Config.setApiUrl(url);
            UI.showToast('API URL saved');
        }
    },

    /**
     * Test connection to the backend.
     */
    async testConnection() {
        try {
            await Api.testConnection();
            UI.showToast('Connected successfully');
            await this.loadHolidays();
        } catch (error) {
            UI.showToast('Connection failed: ' + error.message, 'error');
        }
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());
