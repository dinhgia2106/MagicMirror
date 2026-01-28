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
    }
});
