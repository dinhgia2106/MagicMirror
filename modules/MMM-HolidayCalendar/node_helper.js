/* Node helper for MMM-HolidayCalendar */

const NodeHelper = require("node_helper");
const https = require("https");
const http = require("http");

module.exports = NodeHelper.create({
    start: function () {
        console.log("Starting node helper for: " + this.name);
    },

    socketNotificationReceived: function (notification, payload) {
        if (notification === "FETCH_HOLIDAYS") {
            this.fetchCalendar(payload.url, payload.id);
        } else if (notification === "FETCH_CUSTOM_HOLIDAYS") {
            this.fetchCustomHolidays(payload.url, payload.id);
        }
    },

    fetchCalendar: function (url, id) {
        const self = this;
        const protocol = url.startsWith("https") ? https : http;

        protocol.get(url, (response) => {
            let data = "";

            // Handle redirects
            if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
                this.fetchCalendar(response.headers.location, id);
                return;
            }

            response.on("data", (chunk) => {
                data += chunk;
            });

            response.on("end", () => {
                self.sendSocketNotification("HOLIDAYS_FETCHED", {
                    id: id,
                    data: data
                });
            });
        }).on("error", (error) => {
            console.error("Error fetching holidays:", error);
            self.sendSocketNotification("FETCH_ERROR", {
                id: id,
                error: error.message
            });
        });
    },

    fetchCustomHolidays: function (url, id) {
        const self = this;

        // Parse URL
        let parsedUrl;
        try {
            parsedUrl = new URL(url);
        } catch (e) {
            console.error("Invalid URL:", url);
            self.sendSocketNotification("CUSTOM_HOLIDAYS_ERROR", {
                id: id,
                error: "Invalid URL"
            });
            return;
        }

        const protocol = parsedUrl.protocol === "https:" ? https : http;
        const options = {
            hostname: parsedUrl.hostname,
            port: parsedUrl.port || (parsedUrl.protocol === "https:" ? 443 : 80),
            path: parsedUrl.pathname + parsedUrl.search,
            method: "GET",
            headers: {
                "Accept": "application/json"
            }
        };

        const req = protocol.request(options, (response) => {
            let data = "";

            response.on("data", (chunk) => {
                data += chunk;
            });

            response.on("end", () => {
                try {
                    const jsonData = JSON.parse(data);
                    self.sendSocketNotification("CUSTOM_HOLIDAYS_FETCHED", {
                        id: id,
                        data: jsonData.data || []
                    });
                } catch (e) {
                    console.error("Error parsing custom holidays JSON:", e);
                    self.sendSocketNotification("CUSTOM_HOLIDAYS_ERROR", {
                        id: id,
                        error: "Invalid JSON response"
                    });
                }
            });
        });

        req.on("error", (error) => {
            console.error("Error fetching custom holidays:", error);
            self.sendSocketNotification("CUSTOM_HOLIDAYS_ERROR", {
                id: id,
                error: error.message
            });
        });

        req.end();
    }
});
