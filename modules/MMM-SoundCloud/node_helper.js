/* MMM-SoundCloud Node Helper
 * Currently minimal - can be extended for playlist management
 */

const NodeHelper = require("node_helper");

module.exports = NodeHelper.create({
    start: function () {
        console.log("Starting node_helper for: " + this.name);
    },

    socketNotificationReceived: function (notification, payload) {
        // Future: Handle playlist search, track lookup, etc.
    }
});
