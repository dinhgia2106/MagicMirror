/* MMM-SoundCloud Node Helper
 * Provides SoundCloud API search functionality
 */

const NodeHelper = require("node_helper");
const https = require("https");

module.exports = NodeHelper.create({
    config: null,
    accessToken: null,
    tokenExpiry: null,

    start: function () {
        console.log("Starting node_helper for: " + this.name);
    },

    socketNotificationReceived: function (notification, payload) {
        if (notification === "SET_CONFIG") {
            this.config = payload;
            console.log("[MMM-SoundCloud] Config received, clientId present: " + !!this.config.clientId);
        }

        if (notification === "SEARCH_TRACK") {
            this.searchTrack(payload.query, payload.savedState);
        }
    },

    // Get OAuth access token using client credentials
    getAccessToken: function (callback) {
        // Check if we have a valid cached token
        if (this.accessToken && this.tokenExpiry && Date.now() < this.tokenExpiry) {
            callback(null, this.accessToken);
            return;
        }

        if (!this.config || !this.config.clientId || !this.config.clientSecret) {
            callback(new Error("SoundCloud credentials not configured"), null);
            return;
        }

        const postData = new URLSearchParams({
            grant_type: "client_credentials",
            client_id: this.config.clientId,
            client_secret: this.config.clientSecret
        }).toString();

        const options = {
            hostname: "api.soundcloud.com",
            port: 443,
            path: "/oauth2/token",
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": Buffer.byteLength(postData)
            }
        };

        const req = https.request(options, (res) => {
            let data = "";
            res.on("data", chunk => data += chunk);
            res.on("end", () => {
                try {
                    const tokenData = JSON.parse(data);
                    if (tokenData.access_token) {
                        this.accessToken = tokenData.access_token;
                        // Token expires in 3600 seconds, refresh 5 minutes early
                        this.tokenExpiry = Date.now() + ((tokenData.expires_in || 3600) - 300) * 1000;
                        callback(null, this.accessToken);
                    } else {
                        callback(new Error("Failed to get access token: " + data), null);
                    }
                } catch (e) {
                    callback(new Error("Token parse error: " + e.message), null);
                }
            });
        });

        req.on("error", (e) => {
            callback(new Error("Token request error: " + e.message), null);
        });

        req.write(postData);
        req.end();
    },

    // Search for tracks using SoundCloud API
    searchTrack: function (query, savedState) {
        console.log("[MMM-SoundCloud] Searching for: " + query);

        this.getAccessToken((err, token) => {
            if (err) {
                console.error("[MMM-SoundCloud] Auth error: " + err.message);
                this.sendSocketNotification("SEARCH_RESULT", {
                    success: false,
                    error: err.message,
                    query: query,
                    savedState: savedState
                });
                return;
            }

            const encodedQuery = encodeURIComponent(query);
            const path = `/tracks?q=${encodedQuery}&access=playable&limit=5`;

            const options = {
                hostname: "api.soundcloud.com",
                port: 443,
                path: path,
                method: "GET",
                headers: {
                    "Authorization": "OAuth " + token,
                    "Accept": "application/json"
                }
            };

            const req = https.request(options, (res) => {
                let data = "";
                res.on("data", chunk => data += chunk);
                res.on("end", () => {
                    try {
                        const result = JSON.parse(data);
                        const tracks = result.collection || result || [];

                        console.log("[MMM-SoundCloud] Found " + tracks.length + " tracks");

                        if (tracks.length > 0) {
                            // Log top results
                            tracks.slice(0, 3).forEach((track, i) => {
                                console.log("  " + (i + 1) + ". " + track.title + " by " + (track.user ? track.user.username : "Unknown"));
                            });

                            const bestTrack = tracks[0];
                            this.sendSocketNotification("SEARCH_RESULT", {
                                success: true,
                                query: query,
                                track: {
                                    id: bestTrack.id,
                                    title: bestTrack.title,
                                    artist: bestTrack.user ? bestTrack.user.username : "Unknown",
                                    permalink_url: bestTrack.permalink_url,
                                    stream_url: bestTrack.stream_url,
                                    duration: bestTrack.duration,
                                    artwork_url: bestTrack.artwork_url
                                },
                                savedState: savedState
                            });
                        } else {
                            this.sendSocketNotification("SEARCH_RESULT", {
                                success: false,
                                error: "No tracks found",
                                query: query,
                                savedState: savedState
                            });
                        }
                    } catch (e) {
                        console.error("[MMM-SoundCloud] Parse error: " + e.message);
                        this.sendSocketNotification("SEARCH_RESULT", {
                            success: false,
                            error: "Parse error: " + e.message,
                            query: query,
                            savedState: savedState
                        });
                    }
                });
            });

            req.on("error", (e) => {
                console.error("[MMM-SoundCloud] Search error: " + e.message);
                this.sendSocketNotification("SEARCH_RESULT", {
                    success: false,
                    error: e.message,
                    query: query,
                    savedState: savedState
                });
            });

            req.end();
        });
    }
});
