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

        if (notification === "SEARCH_RELATED") {
            this.searchRelatedTracks(payload.trackId, payload.genre, payload.tags, payload.title);
        }

        if (notification === "PRELOAD_NEXT") {
            this.preloadRelatedTrack(payload.trackId, payload.genre, payload.tags, payload.title, payload.excludeIds || []);
        }

        if (notification === "SEARCH_MOOD") {
            this.searchByMood(payload.mood, payload.savedState);
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

    // Search for related/recommended tracks based on genre, tags, or title keywords
    searchRelatedTracks: function (trackId, genre, tags, title) {
        console.log("[MMM-SoundCloud] Searching related tracks for: " + title + " (genre: " + genre + ", tags: " + tags + ")");

        this.getAccessToken((err, token) => {
            if (err) {
                console.error("[MMM-SoundCloud] Auth error for related search: " + err.message);
                this.sendSocketNotification("RELATED_TRACKS_RESULT", {
                    success: false,
                    error: err.message
                });
                return;
            }

            // Try to find related tracks using the /tracks/{id}/related endpoint first
            const relatedPath = `/tracks/${trackId}/related?limit=10`;

            const relatedOptions = {
                hostname: "api.soundcloud.com",
                port: 443,
                path: relatedPath,
                method: "GET",
                headers: {
                    "Authorization": "OAuth " + token,
                    "Accept": "application/json"
                }
            };

            const relatedReq = https.request(relatedOptions, (res) => {
                let data = "";
                res.on("data", chunk => data += chunk);
                res.on("end", () => {
                    try {
                        const result = JSON.parse(data);
                        const tracks = result.collection || result || [];

                        if (tracks.length > 0) {
                            console.log("[MMM-SoundCloud] Found " + tracks.length + " related tracks via /related endpoint");

                            // Filter out the current track and pick a random one from top results
                            const filtered = tracks.filter(t => t.id !== trackId && t.streamable !== false);
                            if (filtered.length > 0) {
                                // Pick a random track from top 5 to add variety
                                const pickIndex = Math.floor(Math.random() * Math.min(5, filtered.length));
                                const picked = filtered[pickIndex];
                                console.log("[MMM-SoundCloud] Picked related track: " + picked.title + " by " + (picked.user ? picked.user.username : "Unknown"));

                                this.sendSocketNotification("RELATED_TRACKS_RESULT", {
                                    success: true,
                                    track: {
                                        id: picked.id,
                                        title: picked.title,
                                        artist: picked.user ? picked.user.username : "Unknown",
                                        permalink_url: picked.permalink_url,
                                        duration: picked.duration,
                                        artwork_url: picked.artwork_url,
                                        genre: picked.genre || "",
                                        tag_list: picked.tag_list || ""
                                    }
                                });
                                return;
                            }
                        }

                        // Fallback: search by genre or tags or title keywords
                        console.log("[MMM-SoundCloud] /related endpoint returned no usable tracks, falling back to search");
                        this.fallbackRelatedSearch(token, trackId, genre, tags, title);
                    } catch (e) {
                        console.error("[MMM-SoundCloud] Related tracks parse error: " + e.message);
                        this.fallbackRelatedSearch(token, trackId, genre, tags, title);
                    }
                });
            });

            relatedReq.on("error", (e) => {
                console.error("[MMM-SoundCloud] Related tracks request error: " + e.message);
                this.fallbackRelatedSearch(token, trackId, genre, tags, title);
            });

            relatedReq.end();
        });
    },

    // Fallback: search for related tracks by genre, tags, or title keywords
    fallbackRelatedSearch: function (token, trackId, genre, tags, title) {
        // Build search query from genre, tags, or title
        let searchQuery = "";
        if (genre && genre.trim()) {
            searchQuery = genre.trim();
        } else if (tags && tags.trim()) {
            // Use first few tags
            searchQuery = tags.split(/[,\s]+/).slice(0, 3).join(" ");
        } else if (title) {
            // Extract keywords from title (remove common words)
            const stopWords = ["official", "music", "video", "mv", "lyric", "lyrics", "audio", "hd", "hq", "ft", "feat", "remix"];
            searchQuery = title
                .toLowerCase()
                .replace(/[^a-z0-9\s\u00C0-\u024F\u1E00-\u1EFF]/g, " ")
                .split(/\s+/)
                .filter(w => w.length > 2 && !stopWords.includes(w))
                .slice(0, 3)
                .join(" ");
        }

        if (!searchQuery) searchQuery = "trending music";

        console.log("[MMM-SoundCloud] Fallback related search query: " + searchQuery);

        const encodedQuery = encodeURIComponent(searchQuery);
        const path = `/tracks?q=${encodedQuery}&access=playable&limit=15`;

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
                    const filtered = tracks.filter(t => t.id !== trackId && t.streamable !== false);

                    if (filtered.length > 0) {
                        // Pick a random track from results for variety
                        const pickIndex = Math.floor(Math.random() * Math.min(8, filtered.length));
                        const picked = filtered[pickIndex];
                        console.log("[MMM-SoundCloud] Fallback picked: " + picked.title + " by " + (picked.user ? picked.user.username : "Unknown"));

                        this.sendSocketNotification("RELATED_TRACKS_RESULT", {
                            success: true,
                            track: {
                                id: picked.id,
                                title: picked.title,
                                artist: picked.user ? picked.user.username : "Unknown",
                                permalink_url: picked.permalink_url,
                                duration: picked.duration,
                                artwork_url: picked.artwork_url,
                                genre: picked.genre || "",
                                tag_list: picked.tag_list || ""
                            }
                        });
                    } else {
                        console.warn("[MMM-SoundCloud] No related tracks found");
                        this.sendSocketNotification("RELATED_TRACKS_RESULT", {
                            success: false,
                            error: "No related tracks found"
                        });
                    }
                } catch (e) {
                    console.error("[MMM-SoundCloud] Fallback search parse error: " + e.message);
                    this.sendSocketNotification("RELATED_TRACKS_RESULT", {
                        success: false,
                        error: "Parse error: " + e.message
                    });
                }
            });
        });

        req.on("error", (e) => {
            console.error("[MMM-SoundCloud] Fallback search error: " + e.message);
            this.sendSocketNotification("RELATED_TRACKS_RESULT", {
                success: false,
                error: e.message
            });
        });

        req.end();
    },

    // Preload next related track (same logic as searchRelatedTracks but sends PRELOAD_RESULT)
    preloadRelatedTrack: function (trackId, genre, tags, title, excludeIds) {
        console.log("[MMM-SoundCloud] Preloading next track for: " + title);

        this.getAccessToken((err, token) => {
            if (err) {
                console.error("[MMM-SoundCloud] Auth error for preload: " + err.message);
                this.sendSocketNotification("PRELOAD_RESULT", {
                    success: false,
                    error: err.message
                });
                return;
            }

            const relatedPath = `/tracks/${trackId}/related?limit=15`;

            const relatedOptions = {
                hostname: "api.soundcloud.com",
                port: 443,
                path: relatedPath,
                method: "GET",
                headers: {
                    "Authorization": "OAuth " + token,
                    "Accept": "application/json"
                }
            };

            const relatedReq = https.request(relatedOptions, (res) => {
                let data = "";
                res.on("data", chunk => data += chunk);
                res.on("end", () => {
                    try {
                        const result = JSON.parse(data);
                        const tracks = result.collection || result || [];
                        // Filter out current track and already-played tracks
                        const filtered = tracks.filter(t =>
                            t.id !== trackId &&
                            t.streamable !== false &&
                            !excludeIds.includes(t.id)
                        );

                        if (filtered.length > 0) {
                            const pickIndex = Math.floor(Math.random() * Math.min(5, filtered.length));
                            const picked = filtered[pickIndex];
                            console.log("[MMM-SoundCloud] Preloaded: " + picked.title + " by " + (picked.user ? picked.user.username : "Unknown"));

                            this.sendSocketNotification("PRELOAD_RESULT", {
                                success: true,
                                track: {
                                    id: picked.id,
                                    title: picked.title,
                                    artist: picked.user ? picked.user.username : "Unknown",
                                    permalink_url: picked.permalink_url,
                                    duration: picked.duration,
                                    artwork_url: picked.artwork_url,
                                    genre: picked.genre || "",
                                    tag_list: picked.tag_list || ""
                                }
                            });
                            return;
                        }

                        // Fallback: search by genre/tags/title
                        this.preloadFallbackSearch(token, trackId, genre, tags, title, excludeIds);
                    } catch (e) {
                        console.error("[MMM-SoundCloud] Preload parse error: " + e.message);
                        this.preloadFallbackSearch(token, trackId, genre, tags, title, excludeIds);
                    }
                });
            });

            relatedReq.on("error", (e) => {
                console.error("[MMM-SoundCloud] Preload request error: " + e.message);
                this.sendSocketNotification("PRELOAD_RESULT", {
                    success: false,
                    error: e.message
                });
            });

            relatedReq.end();
        });
    },

    // Fallback search for preloading
    preloadFallbackSearch: function (token, trackId, genre, tags, title, excludeIds) {
        let searchQuery = "";
        if (genre && genre.trim()) {
            searchQuery = genre.trim();
        } else if (tags && tags.trim()) {
            searchQuery = tags.split(/[,\s]+/).slice(0, 3).join(" ");
        } else if (title) {
            const stopWords = ["official", "music", "video", "mv", "lyric", "lyrics", "audio", "hd", "hq", "ft", "feat", "remix"];
            searchQuery = title
                .toLowerCase()
                .replace(/[^a-z0-9\s\u00C0-\u024F\u1E00-\u1EFF]/g, " ")
                .split(/\s+/)
                .filter(w => w.length > 2 && !stopWords.includes(w))
                .slice(0, 3)
                .join(" ");
        }
        if (!searchQuery) searchQuery = "trending music";

        const encodedQuery = encodeURIComponent(searchQuery);
        const path = `/tracks?q=${encodedQuery}&access=playable&limit=15`;

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
                    const filtered = tracks.filter(t =>
                        t.id !== trackId &&
                        t.streamable !== false &&
                        !excludeIds.includes(t.id)
                    );

                    if (filtered.length > 0) {
                        const pickIndex = Math.floor(Math.random() * Math.min(8, filtered.length));
                        const picked = filtered[pickIndex];
                        console.log("[MMM-SoundCloud] Preload fallback picked: " + picked.title);

                        this.sendSocketNotification("PRELOAD_RESULT", {
                            success: true,
                            track: {
                                id: picked.id,
                                title: picked.title,
                                artist: picked.user ? picked.user.username : "Unknown",
                                permalink_url: picked.permalink_url,
                                duration: picked.duration,
                                artwork_url: picked.artwork_url,
                                genre: picked.genre || "",
                                tag_list: picked.tag_list || ""
                            }
                        });
                    } else {
                        this.sendSocketNotification("PRELOAD_RESULT", {
                            success: false,
                            error: "No tracks found for preload"
                        });
                    }
                } catch (e) {
                    this.sendSocketNotification("PRELOAD_RESULT", {
                        success: false,
                        error: "Parse error: " + e.message
                    });
                }
            });
        });

        req.on("error", (e) => {
            this.sendSocketNotification("PRELOAD_RESULT", {
                success: false,
                error: e.message
            });
        });

        req.end();
    },

    // Search for music by mood/genre/theme (for AI assistant)
    searchByMood: function (mood, savedState) {
        console.log("[MMM-SoundCloud] Searching by mood: " + mood);

        // Map common moods/themes to better search queries
        const moodMap = {
            "buồn": "sad vietnamese music",
            "vui": "happy upbeat music",
            "tết": "nhạc tết vietnamese new year",
            "chill": "chill lofi relax",
            "tập trung": "focus study music",
            "ngủ": "sleep ambient calm",
            "sôi động": "energetic dance party",
            "romantic": "romantic love songs",
            "lãng mạn": "romantic love songs vietnamese",
            "workout": "workout gym motivation",
            "jazz": "jazz music",
            "lofi": "lofi hip hop beats",
            "rock": "rock music",
            "pop": "pop music hits",
            "classical": "classical music",
            "edm": "electronic dance music",
            "random": "popular trending music",
            "ngẫu nhiên": "popular trending music"
        };

        // Check if mood matches any mapped term
        let searchQuery = mood;
        const moodLower = mood.toLowerCase().trim();
        for (const [key, value] of Object.entries(moodMap)) {
            if (moodLower.includes(key)) {
                searchQuery = value;
                break;
            }
        }

        this.getAccessToken((err, token) => {
            if (err) {
                console.error("[MMM-SoundCloud] Auth error for mood search: " + err.message);
                this.sendSocketNotification("SEARCH_RESULT", {
                    success: false,
                    error: err.message,
                    query: mood,
                    savedState: savedState
                });
                return;
            }

            const encodedQuery = encodeURIComponent(searchQuery);
            const path = `/tracks?q=${encodedQuery}&access=playable&limit=20`;

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
                        const filtered = tracks.filter(t => t.streamable !== false);

                        if (filtered.length > 0) {
                            // Pick a random track from results for variety
                            const pickIndex = Math.floor(Math.random() * Math.min(10, filtered.length));
                            const picked = filtered[pickIndex];
                            console.log("[MMM-SoundCloud] Mood search picked: " + picked.title + " by " + (picked.user ? picked.user.username : "Unknown"));

                            this.sendSocketNotification("SEARCH_RESULT", {
                                success: true,
                                query: mood,
                                track: {
                                    id: picked.id,
                                    title: picked.title,
                                    artist: picked.user ? picked.user.username : "Unknown",
                                    permalink_url: picked.permalink_url,
                                    stream_url: picked.stream_url,
                                    duration: picked.duration,
                                    artwork_url: picked.artwork_url,
                                    genre: picked.genre || "",
                                    tag_list: picked.tag_list || ""
                                },
                                savedState: savedState
                            });
                        } else {
                            this.sendSocketNotification("SEARCH_RESULT", {
                                success: false,
                                error: "No tracks found for mood: " + mood,
                                query: mood,
                                savedState: savedState
                            });
                        }
                    } catch (e) {
                        console.error("[MMM-SoundCloud] Mood search parse error: " + e.message);
                        this.sendSocketNotification("SEARCH_RESULT", {
                            success: false,
                            error: "Parse error: " + e.message,
                            query: mood,
                            savedState: savedState
                        });
                    }
                });
            });

            req.on("error", (e) => {
                console.error("[MMM-SoundCloud] Mood search error: " + e.message);
                this.sendSocketNotification("SEARCH_RESULT", {
                    success: false,
                    error: e.message,
                    query: mood,
                    savedState: savedState
                });
            });

            req.end();
        });
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
                                    artwork_url: bestTrack.artwork_url,
                                    genre: bestTrack.genre || "",
                                    tag_list: bestTrack.tag_list || ""
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
