/**
 * Configuration module for the Holiday Manager frontend.
 * Loads settings from config.json or uses defaults.
 */

const Config = {
    // Default settings
    _defaults: {
        apiUrl: 'http://localhost:8000',
        language: 'vi',
        dateFormat: 'DD/MM/YYYY',
        theme: 'dark'
    },

    // Current settings
    apiUrl: localStorage.getItem('holidayApiUrl') || 'http://localhost:8000',
    language: 'vi',
    dateFormat: 'DD/MM/YYYY',
    theme: 'dark',

    // Endpoints
    endpoints: {
        holidays: '/api/holidays',
        health: '/api/health'
    },

    // Load config from config.json
    async load() {
        try {
            const response = await fetch('config.json');
            if (response.ok) {
                const config = await response.json();
                this.apiUrl = localStorage.getItem('holidayApiUrl') || config.apiUrl || this._defaults.apiUrl;
                this.language = config.language || this._defaults.language;
                this.dateFormat = config.dateFormat || this._defaults.dateFormat;
                this.theme = config.theme || this._defaults.theme;
                console.log('Config loaded from config.json');
            }
        } catch (e) {
            console.log('Using default config (config.json not found)');
        }
    },

    // Get full URL for an endpoint
    getUrl(endpoint) {
        return this.apiUrl + endpoint;
    },

    // Update API URL
    setApiUrl(url) {
        // Remove trailing slash
        url = url.replace(/\/+$/, '');
        this.apiUrl = url;
        localStorage.setItem('holidayApiUrl', url);
    },

    // Month names for display
    months: [
        'January', 'February', 'March', 'April',
        'May', 'June', 'July', 'August',
        'September', 'October', 'November', 'December'
    ],

    monthsVi: [
        'Thang 1', 'Thang 2', 'Thang 3', 'Thang 4',
        'Thang 5', 'Thang 6', 'Thang 7', 'Thang 8',
        'Thang 9', 'Thang 10', 'Thang 11', 'Thang 12'
    ],

    lunarMonths: [
        'Gieng', 'Hai', 'Ba', 'Tu', 'Nam', 'Sau',
        'Bay', 'Tam', 'Chin', 'Muoi', 'Muoi Mot', 'Chap'
    ],

    weekdays: [
        'Monday', 'Tuesday', 'Wednesday', 'Thursday',
        'Friday', 'Saturday', 'Sunday'
    ],

    weekdaysVi: [
        'Thu Hai', 'Thu Ba', 'Thu Tu', 'Thu Nam',
        'Thu Sau', 'Thu Bay', 'Chu Nhat'
    ],

    ordinals: {
        1: 'First',
        2: 'Second',
        3: 'Third',
        4: 'Fourth',
        '-1': 'Last'
    },

    ordinalsVi: {
        1: 'Thu nhat',
        2: 'Thu hai',
        3: 'Thu ba',
        4: 'Thu tu',
        '-1': 'Cuoi cung'
    }
};
