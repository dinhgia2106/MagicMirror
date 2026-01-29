/**
 * API module for communicating with the Holiday backend.
 */

const Api = {
    /**
     * Make an API request.
     */
    async request(endpoint, options = {}) {
        const url = Config.getUrl(endpoint);

        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json'
            }
        };

        const mergedOptions = { ...defaultOptions, ...options };

        try {
            const response = await fetch(url, mergedOptions);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'API request failed');
            }

            return data;
        } catch (error) {
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                throw new Error('Cannot connect to server. Check API URL and server status.');
            }
            throw error;
        }
    },

    /**
     * Get all holidays.
     */
    async getHolidays(query = '') {
        const endpoint = query
            ? `${Config.endpoints.holidays}?q=${encodeURIComponent(query)}`
            : Config.endpoints.holidays;
        return this.request(endpoint);
    },

    /**
     * Get a single holiday by ID.
     */
    async getHoliday(id) {
        return this.request(`${Config.endpoints.holidays}/${id}`);
    },

    /**
     * Create a new holiday.
     */
    async createHoliday(data) {
        return this.request(Config.endpoints.holidays, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },

    /**
     * Update an existing holiday.
     */
    async updateHoliday(id, data) {
        return this.request(`${Config.endpoints.holidays}/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    /**
     * Delete a holiday.
     */
    async deleteHoliday(id) {
        return this.request(`${Config.endpoints.holidays}/${id}`, {
            method: 'DELETE'
        });
    },

    /**
     * Test connection to the backend.
     */
    async testConnection() {
        return this.request(Config.endpoints.health);
    }
};
