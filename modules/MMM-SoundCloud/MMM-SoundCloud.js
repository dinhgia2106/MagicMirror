/* MMM-SoundCloud - Music Player Module for MagicMirror
 * Uses SoundCloud Widget API for playback control
 */

Module.register("MMM-SoundCloud", {
    defaults: {
        playlistUrl: "https://soundcloud.com/gia-nh-694104983/sets/chill",
        autoPlay: false,
        showArtwork: true,
        defaultVolume: 50,
        width: "100%",
        height: "166",
        // SoundCloud API credentials for global search (optional)
        clientId: "",
        clientSecret: ""
    },

    getStyles: function () {
        return ["MMM-SoundCloud.css"];
    },

    start: function () {
        Log.info("Starting module: " + this.name);
        this.currentTrack = null;
        this.isPaused = true;
        this.volume = this.config.defaultVolume;
        this.previousVolume = this.volume;
        this.widgetReady = false;
        this.currentPosition = 0;
        this.duration = 0;
        this.isShuffled = false;
        this.shuffleQueue = [];      // Queue of unplayed track indices
        this.totalTracks = 0;        // Total number of tracks in playlist

        // Search and play state - for returning after searched song finishes
        this.isPlayingSearched = false;   // Flag when playing a searched song
        this.savedTrackIndex = -1;         // Original track index to return to
        this.savedPosition = 0;            // Original position in that track
        this.savedIsPaused = true;         // Whether music was paused before search
        this.savedPlaylistUrl = this.config.playlistUrl;  // Original playlist URL to return to
        this.pendingSearchState = null;  // Pending search state while waiting for API response
    },

    getDom: function () {
        const wrapper = document.createElement("div");
        wrapper.className = "soundcloud-player";

        // Hidden SoundCloud iframe
        const iframe = document.createElement("iframe");
        iframe.id = "sc-widget";
        iframe.className = "sc-iframe";
        iframe.width = this.config.width;
        iframe.height = this.config.height;
        iframe.scrolling = "no";
        iframe.frameBorder = "no";
        iframe.allow = "autoplay";
        iframe.src = `https://w.soundcloud.com/player/?url=${encodeURIComponent(this.config.playlistUrl)}&color=%23ff5500&auto_play=${this.config.autoPlay}&hide_related=true&show_comments=false&show_user=true&show_reposts=false&show_teaser=false&visual=${this.config.showArtwork}`;
        wrapper.appendChild(iframe);

        // Custom player UI
        const playerUI = document.createElement("div");
        playerUI.className = "player-ui";

        // Track info row
        const trackRow = document.createElement("div");
        trackRow.className = "track-row";

        const trackName = document.createElement("div");
        trackName.className = "track-name";
        trackName.id = "track-name";
        trackName.textContent = this.currentTrack ? this.currentTrack.title : "Loading...";
        trackRow.appendChild(trackName);

        playerUI.appendChild(trackRow);

        // Artist row
        const artistName = document.createElement("div");
        artistName.className = "artist-name";
        artistName.id = "artist-name";
        artistName.textContent = this.currentTrack ? this.currentTrack.user.username : "";
        playerUI.appendChild(artistName);

        // Progress bar
        const progressContainer = document.createElement("div");
        progressContainer.className = "progress-container";
        progressContainer.id = "progress-container";

        const progressBar = document.createElement("div");
        progressBar.className = "progress-bar";
        progressBar.id = "progress-bar";
        const progress = this.duration > 0 ? (this.currentPosition / this.duration) * 100 : 0;
        progressBar.style.width = progress + "%";
        progressContainer.appendChild(progressBar);

        this.setupSeekGesture(progressContainer);
        playerUI.appendChild(progressContainer);

        // Time display
        const timeRow = document.createElement("div");
        timeRow.className = "time-row";

        const currentTime = document.createElement("span");
        currentTime.id = "current-time";
        currentTime.textContent = this.formatTime(this.currentPosition);
        timeRow.appendChild(currentTime);

        const totalTime = document.createElement("span");
        totalTime.id = "total-time";
        totalTime.textContent = this.formatTime(this.duration);
        timeRow.appendChild(totalTime);

        playerUI.appendChild(timeRow);

        // Controls row
        const controlsRow = document.createElement("div");
        controlsRow.className = "controls-row";

        // Volume control (left side)
        const volumeWrapper = document.createElement("div");
        volumeWrapper.className = "volume-wrapper";

        const volumeControl = document.createElement("div");
        volumeControl.className = "volume-control";
        volumeControl.id = "volume-control";
        volumeControl.textContent = this.volume + "%";
        volumeControl.title = "Tap to adjust volume";
        volumeWrapper.appendChild(volumeControl);

        // Volume popup slider
        const volumePopup = document.createElement("div");
        volumePopup.className = "volume-popup";
        volumePopup.id = "volume-popup";

        const volumeSliderTrack = document.createElement("div");
        volumeSliderTrack.className = "volume-slider-track";

        const volumeSliderFill = document.createElement("div");
        volumeSliderFill.className = "volume-slider-fill";
        volumeSliderFill.id = "volume-slider-fill";
        volumeSliderFill.style.height = this.volume + "%";
        volumeSliderTrack.appendChild(volumeSliderFill);

        const volumeSliderThumb = document.createElement("div");
        volumeSliderThumb.className = "volume-slider-thumb";
        volumeSliderThumb.id = "volume-slider-thumb";
        volumeSliderThumb.style.bottom = this.volume + "%";
        volumeSliderTrack.appendChild(volumeSliderThumb);

        volumePopup.appendChild(volumeSliderTrack);

        const volumeValue = document.createElement("div");
        volumeValue.className = "volume-popup-value";
        volumeValue.id = "volume-popup-value";
        volumeValue.textContent = Math.round(this.volume) + "%";
        volumePopup.appendChild(volumeValue);

        volumeWrapper.appendChild(volumePopup);
        this.setupVolumePopup(volumeControl, volumePopup, volumeSliderTrack);
        controlsRow.appendChild(volumeWrapper);

        const prevBtn = document.createElement("button");
        prevBtn.className = "control-btn";
        prevBtn.innerHTML = "&#9664;&#9664;";
        prevBtn.onclick = () => this.prev();
        controlsRow.appendChild(prevBtn);

        const playBtn = document.createElement("button");
        playBtn.className = "control-btn play-btn";
        playBtn.id = "play-btn";
        playBtn.innerHTML = this.isPaused ? "&#9654;" : "&#10074;&#10074;";
        playBtn.onclick = () => this.toggle();
        controlsRow.appendChild(playBtn);

        const nextBtn = document.createElement("button");
        nextBtn.className = "control-btn";
        nextBtn.innerHTML = "&#9654;&#9654;";
        nextBtn.onclick = () => this.next();
        controlsRow.appendChild(nextBtn);

        // Shuffle button (right side)
        const shuffleBtn = document.createElement("button");
        shuffleBtn.className = "control-btn shuffle-btn" + (this.isShuffled ? " active" : "");
        shuffleBtn.id = "shuffle-btn";
        shuffleBtn.innerHTML = "&#8645;"; // Up-down arrows for shuffle
        shuffleBtn.title = "Shuffle";
        shuffleBtn.onclick = () => this.toggleShuffle();
        controlsRow.appendChild(shuffleBtn);

        playerUI.appendChild(controlsRow);

        wrapper.appendChild(playerUI);

        return wrapper;
    },

    formatTime: function (ms) {
        const seconds = Math.floor(ms / 1000);
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    notificationReceived: function (notification, payload, sender) {
        // Handle touch gestures from MMM-Touch
        if (notification === "TOUCH_SWIPE_LEFT") {
            this.next();
        } else if (notification === "TOUCH_SWIPE_RIGHT") {
            this.prev();
        }

        // Handle music control notifications (from LLM or other modules)
        switch (notification) {
            case "MUSIC_PLAY":
                this.play();
                break;
            case "MUSIC_PAUSE":
                this.pause();
                break;
            case "MUSIC_TOGGLE":
                this.toggle();
                break;
            case "MUSIC_NEXT":
                this.next();
                break;
            case "MUSIC_PREV":
                this.prev();
                break;
            case "MUSIC_SET_VOLUME":
                if (payload && typeof payload.volume === "number") {
                    this.setVolume(payload.volume);
                }
                break;
            case "MUSIC_LOWER_VOLUME":
                this.lowerVolume();
                break;
            case "MUSIC_RESTORE_VOLUME":
                this.restoreVolume();
                break;
            case "MUSIC_SEARCH_PLAY":
                Log.info("MMM-SoundCloud: Received MUSIC_SEARCH_PLAY, payload: " + JSON.stringify(payload));
                if (payload && payload.song_name) {
                    this.searchAndPlayTrack(payload.song_name);
                } else {
                    Log.warn("MMM-SoundCloud: MUSIC_SEARCH_PLAY missing song_name in payload");
                }
                break;
            case "DOM_OBJECTS_CREATED":
                this.initWidget();
                // Send config to node_helper for API access
                this.sendSocketNotification("SET_CONFIG", this.config);
                break;
        }
    },

    // Handle responses from node_helper (search results, etc.)
    socketNotificationReceived: function (notification, payload) {
        if (notification === "SEARCH_RESULT") {
            this.handleSearchResult(payload);
        }
    },

    initWidget: function () {
        // Load SoundCloud Widget API
        const script = document.createElement("script");
        script.src = "https://w.soundcloud.com/player/api.js";
        script.onload = () => {
            this.setupWidget();
        };
        document.head.appendChild(script);
    },

    setupWidget: function () {
        const iframe = document.getElementById("sc-widget");
        if (!iframe || typeof SC === "undefined") {
            Log.error("MMM-SoundCloud: Widget API not loaded");
            return;
        }

        this.widget = SC.Widget(iframe);

        this.widget.bind(SC.Widget.Events.READY, () => {
            Log.info("MMM-SoundCloud: Widget ready");
            this.widgetReady = true;
            this.setVolume(this.config.defaultVolume);
            this.updateTrackInfo();
        });

        this.widget.bind(SC.Widget.Events.PLAY, () => {
            this.isPaused = false;
            this.updatePlayStatus();
        });

        this.widget.bind(SC.Widget.Events.PAUSE, () => {
            this.isPaused = true;
            this.updatePlayStatus();
        });

        this.widget.bind(SC.Widget.Events.PLAY_PROGRESS, (data) => {
            // Update position and progress bar
            this.currentPosition = data.currentPosition;
            this.updateProgress();
            // Update track info periodically
            this.updateTrackInfo();
        });

        this.widget.bind(SC.Widget.Events.FINISH, () => {
            // Track finished
            if (this.isPlayingSearched) {
                // Was playing a searched song - return to previous position
                this.returnToSavedTrack();
            } else if (this.isShuffled) {
                // In shuffle mode, play a random track
                this.playRandomTrack();
            } else {
                // Normal mode - SoundCloud handles next track automatically
                this.isPaused = true;
                this.updatePlayStatus();
            }
        });
    },

    updateTrackInfo: function () {
        if (!this.widget) return;

        this.widget.getCurrentSound((sound) => {
            if (sound && (!this.currentTrack || this.currentTrack.id !== sound.id)) {
                this.currentTrack = sound;
                this.duration = sound.duration || 0;

                const trackNameEl = document.getElementById("track-name");
                const artistNameEl = document.getElementById("artist-name");
                const totalTimeEl = document.getElementById("total-time");

                if (trackNameEl) trackNameEl.textContent = sound.title || "Unknown";
                if (artistNameEl) artistNameEl.textContent = sound.user ? sound.user.username : "";
                if (totalTimeEl) totalTimeEl.textContent = this.formatTime(this.duration);

                // Broadcast track change
                this.sendNotification("MUSIC_TRACK_CHANGED", {
                    title: sound.title,
                    artist: sound.user ? sound.user.username : "",
                    artwork: sound.artwork_url
                });
            }
        });
    },

    updateProgress: function () {
        const progressBar = document.getElementById("progress-bar");
        const currentTimeEl = document.getElementById("current-time");

        if (progressBar && this.duration > 0) {
            const progress = (this.currentPosition / this.duration) * 100;
            progressBar.style.width = progress + "%";
        }
        if (currentTimeEl) {
            currentTimeEl.textContent = this.formatTime(this.currentPosition);
        }
    },

    updatePlayStatus: function () {
        const playBtn = document.getElementById("play-btn");
        if (playBtn) {
            playBtn.innerHTML = this.isPaused ? "&#9654;" : "&#10074;&#10074;";
        }

        this.sendNotification("MUSIC_STATE_CHANGED", {
            isPaused: this.isPaused,
            track: this.currentTrack
        });
    },

    // Control methods
    play: function () {
        if (this.widget && this.widgetReady) {
            this.widget.play();
        }
    },

    pause: function () {
        if (this.widget && this.widgetReady) {
            this.widget.pause();
        }
    },

    toggle: function () {
        if (this.widget && this.widgetReady) {
            this.widget.toggle();
        }
    },

    next: function () {
        if (this.widget && this.widgetReady) {
            if (this.isShuffled) {
                this.playRandomTrack();
            } else {
                this.widget.next();
            }
        }
    },

    prev: function () {
        if (this.widget && this.widgetReady) {
            this.widget.prev();
        }
    },

    seekTo: function (position) {
        if (this.widget && this.widgetReady && this.duration > 0) {
            const seekPosition = Math.max(0, Math.min(this.duration, position));
            this.widget.seekTo(seekPosition);
        }
    },

    setupSeekGesture: function (progressContainer) {
        let isDragging = false;

        const updateSeekFromPosition = (clientX) => {
            const rect = progressContainer.getBoundingClientRect();
            const x = clientX - rect.left;
            const percentage = Math.max(0, Math.min(1, x / rect.width));
            const seekPosition = percentage * this.duration;
            this.seekTo(seekPosition);
        };

        const onStart = (e) => {
            if (this.duration <= 0) return;
            isDragging = true;
            progressContainer.classList.add("seeking");
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            updateSeekFromPosition(clientX);
            e.preventDefault();
        };

        const onMove = (e) => {
            if (!isDragging) return;
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            updateSeekFromPosition(clientX);
            e.preventDefault();
        };

        const onEnd = () => {
            if (!isDragging) return;
            isDragging = false;
            progressContainer.classList.remove("seeking");
        };

        // Touch events
        progressContainer.addEventListener("touchstart", onStart, { passive: false });
        document.addEventListener("touchmove", onMove, { passive: false });
        document.addEventListener("touchend", onEnd);
        document.addEventListener("touchcancel", onEnd);

        // Mouse events
        progressContainer.addEventListener("mousedown", onStart);
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onEnd);
    },

    setVolume: function (level) {
        if (this.widget && this.widgetReady) {
            level = Math.max(0, Math.min(100, level));
            this.volume = level;
            this.widget.setVolume(level);
            this.updateVolumeDisplay();
        }
    },

    updateVolumeDisplay: function () {
        const volumeEl = document.getElementById("volume-control");
        const volumeFill = document.getElementById("volume-slider-fill");
        const volumeThumb = document.getElementById("volume-slider-thumb");
        const volumePopupValue = document.getElementById("volume-popup-value");
        const vol = Math.round(this.volume);

        if (volumeEl) volumeEl.textContent = vol + "%";
        if (volumeFill) volumeFill.style.height = vol + "%";
        if (volumeThumb) volumeThumb.style.bottom = vol + "%";
        if (volumePopupValue) volumePopupValue.textContent = vol + "%";
    },

    setupVolumePopup: function (trigger, popup, sliderTrack) {
        let isDragging = false;
        let startY = 0;
        let startVolume = 0;

        const showPopup = () => {
            popup.classList.add("visible");
        };

        const hidePopup = () => {
            popup.classList.remove("visible");
        };

        const onStart = (e) => {
            isDragging = true;
            startY = e.touches ? e.touches[0].clientY : e.clientY;
            startVolume = this.volume;
            showPopup();
            trigger.classList.add("dragging");
            e.preventDefault();
        };

        const onMove = (e) => {
            if (!isDragging) return;
            const currentY = e.touches ? e.touches[0].clientY : e.clientY;
            const deltaY = startY - currentY; // Up = positive = increase volume
            const volumeChange = deltaY * 0.5; // 0.5% per pixel
            const newVolume = Math.max(0, Math.min(100, startVolume + volumeChange));
            this.setVolume(newVolume);
            e.preventDefault();
        };

        const onEnd = () => {
            if (!isDragging) return;
            isDragging = false;
            hidePopup();
            trigger.classList.remove("dragging");
        };

        // Touch events on trigger
        trigger.addEventListener("touchstart", onStart, { passive: false });
        document.addEventListener("touchmove", onMove, { passive: false });
        document.addEventListener("touchend", onEnd);
        document.addEventListener("touchcancel", onEnd);

        // Mouse events on trigger
        trigger.addEventListener("mousedown", onStart);
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onEnd);
    },


    toggleShuffle: function () {
        if (!this.widget || !this.widgetReady) return;

        this.isShuffled = !this.isShuffled;

        // Update shuffle button appearance
        const shuffleBtn = document.getElementById("shuffle-btn");
        if (shuffleBtn) {
            if (this.isShuffled) {
                shuffleBtn.classList.add("active");
            } else {
                shuffleBtn.classList.remove("active");
            }
        }

        if (this.isShuffled) {
            // Reset and build shuffle queue
            this.shuffleQueue = [];
            this.widget.getSounds((sounds) => {
                if (!sounds || sounds.length === 0) return;

                this.totalTracks = sounds.length;

                // Get current track index to exclude from shuffle
                this.widget.getCurrentSoundIndex((currentIndex) => {
                    // Build queue excluding current track
                    for (let i = 0; i < sounds.length; i++) {
                        if (i !== currentIndex) {
                            this.shuffleQueue.push(i);
                        }
                    }
                    // Fisher-Yates shuffle
                    for (let i = this.shuffleQueue.length - 1; i > 0; i--) {
                        const j = Math.floor(Math.random() * (i + 1));
                        [this.shuffleQueue[i], this.shuffleQueue[j]] = [this.shuffleQueue[j], this.shuffleQueue[i]];
                    }

                    Log.info("MMM-SoundCloud: Shuffle ON - queue built with " + this.shuffleQueue.length + " tracks (excluding current)");
                });
            });
        } else {
            // Clear queue when shuffle is turned off
            this.shuffleQueue = [];
            Log.info("MMM-SoundCloud: Shuffle OFF");
        }

        this.sendNotification("MUSIC_SHUFFLE_CHANGED", { isShuffled: this.isShuffled });
    },

    playRandomTrack: function () {
        if (!this.widget || !this.widgetReady) return;

        this.widget.getSounds((sounds) => {
            if (!sounds || sounds.length === 0) return;

            this.totalTracks = sounds.length;

            // If queue is empty, refill it with all track indices
            if (this.shuffleQueue.length === 0) {
                this.shuffleQueue = [];
                for (let i = 0; i < sounds.length; i++) {
                    this.shuffleQueue.push(i);
                }
                // Shuffle the queue (Fisher-Yates)
                for (let i = this.shuffleQueue.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [this.shuffleQueue[i], this.shuffleQueue[j]] = [this.shuffleQueue[j], this.shuffleQueue[i]];
                }
                Log.info("MMM-SoundCloud: Shuffle queue refilled with " + sounds.length + " tracks");
            }

            // Get current track index to avoid playing same track
            this.widget.getCurrentSoundIndex((currentIndex) => {
                // Remove current track from queue if present
                const currentInQueue = this.shuffleQueue.indexOf(currentIndex);
                if (currentInQueue > -1 && this.shuffleQueue.length > 1) {
                    this.shuffleQueue.splice(currentInQueue, 1);
                }

                // Pick next track from queue
                const nextIndex = this.shuffleQueue.shift();

                if (nextIndex !== undefined) {
                    this.widget.skip(nextIndex);
                    Log.info("MMM-SoundCloud: Shuffle - playing track " + nextIndex + " (" + this.shuffleQueue.length + " remaining)");
                } else {
                    // Fallback: pick random
                    const randomIndex = Math.floor(Math.random() * sounds.length);
                    this.widget.skip(randomIndex);
                    Log.info("MMM-SoundCloud: Shuffle fallback - playing track " + randomIndex);
                }
            });
        });
    },

    lowerVolume: function () {
        // Store current volume and lower to 5%
        this.previousVolume = this.volume;
        this.setVolume(5);
        Log.info("MMM-SoundCloud: Volume lowered to 5%");
    },

    restoreVolume: function () {
        // Restore previous volume
        this.setVolume(this.previousVolume);
        Log.info("MMM-SoundCloud: Volume restored to " + this.previousVolume + "%");
    },

    // Search for a track by name and play it
    searchAndPlayTrack: function (query) {
        if (!this.widget || !this.widgetReady) {
            Log.error("MMM-SoundCloud: Widget not ready for search");
            return;
        }

        Log.info("MMM-SoundCloud: Searching for track: " + query);

        // Save current state before searching
        this.widget.getCurrentSoundIndex((currentIndex) => {
            const savedState = {
                trackIndex: currentIndex,
                position: this.currentPosition,
                isPaused: this.isPaused,
                playlistUrl: this.savedPlaylistUrl
            };

            Log.info("MMM-SoundCloud: Saved state - index: " + currentIndex + ", pos: " + savedState.position + ", paused: " + savedState.isPaused);

            // Check if SoundCloud API credentials are configured
            if (this.config.clientId && this.config.clientSecret) {
                Log.info("MMM-SoundCloud: Using SoundCloud API for global search");
                // Send search request to node_helper
                this.sendSocketNotification("SEARCH_TRACK", {
                    query: query,
                    savedState: savedState
                });
            } else {
                // Fallback to local playlist search
                Log.info("MMM-SoundCloud: No API credentials, searching in local playlist");
                this.searchInLocalPlaylist(query, savedState);
            }
        });
    },

    // Handle search results from node_helper (global SoundCloud search)
    handleSearchResult: function (payload) {
        Log.info("MMM-SoundCloud: Received search result: " + JSON.stringify(payload));

        if (payload.success && payload.track) {
            // Found a track via API - load it into widget
            const trackUrl = payload.track.permalink_url;
            Log.info("MMM-SoundCloud: Loading track: " + payload.track.title + " by " + payload.track.artist);
            Log.info("MMM-SoundCloud: Track URL: " + trackUrl);

            // Store saved state for returning later
            if (payload.savedState) {
                this.savedTrackIndex = payload.savedState.trackIndex;
                this.savedPosition = payload.savedState.position;
                this.savedIsPaused = payload.savedState.isPaused;
                this.savedPlaylistUrl = payload.savedState.playlistUrl;
            }

            this.isPlayingSearched = true;

            // Load the track into the widget
            this.widget.load(trackUrl, {
                auto_play: true,
                show_artwork: this.config.showArtwork,
                callback: () => {
                    Log.info("MMM-SoundCloud: External track loaded successfully");
                    // Set volume
                    this.widget.setVolume(this.volume);

                    // Send notification about found track
                    this.sendNotification("MUSIC_SEARCH_RESULT", {
                        found: true,
                        query: payload.query,
                        track: payload.track.title,
                        artist: payload.track.artist,
                        source: "global"
                    });
                }
            });
        } else {
            // API search failed - try local playlist search
            Log.warn("MMM-SoundCloud: Global search failed, trying local. Error: " + (payload.error || "Unknown"));
            if (payload.savedState) {
                this.searchInLocalPlaylist(payload.query, payload.savedState);
            } else {
                this.sendNotification("MUSIC_SEARCH_RESULT", {
                    found: false,
                    query: payload.query,
                    message: "Khong tim thay bai hat"
                });
            }
        }
    },

    // Search within the local playlist
    searchInLocalPlaylist: function (query, savedState) {
        const normalizedQuery = this.normalizeText(query);
        Log.info("MMM-SoundCloud: Searching in local playlist (normalized: " + normalizedQuery + ")");

        this.widget.getSounds((sounds) => {
            if (!sounds || sounds.length === 0) {
                Log.warn("MMM-SoundCloud: No tracks in playlist");
                return;
            }

            Log.info("MMM-SoundCloud: Searching in " + sounds.length + " tracks");

            // Search for matching track
            let candidates = [];
            const queryWords = normalizedQuery.split(/\s+/).filter(w => w.length > 0);

            for (let i = 0; i < sounds.length; i++) {
                const title = sounds[i].title || "";
                const normalizedTitle = this.normalizeText(title);
                let score = 0;
                let matchType = "";

                if (normalizedTitle === normalizedQuery) {
                    score = 100;
                    matchType = "exact";
                } else if (normalizedTitle.includes(normalizedQuery)) {
                    score = 50 + (normalizedQuery.length / normalizedTitle.length) * 40;
                    matchType = "substring";
                } else if (normalizedQuery.includes(normalizedTitle)) {
                    score = 40 + (normalizedTitle.length / normalizedQuery.length) * 30;
                    matchType = "reverse-substring";
                } else {
                    const titleWords = normalizedTitle.split(/\s+/).filter(w => w.length > 0);
                    let matchedWords = 0;
                    let matchedChars = 0;
                    for (const qw of queryWords) {
                        for (const tw of titleWords) {
                            if (tw.includes(qw) || qw.includes(tw)) {
                                matchedWords++;
                                matchedChars += Math.min(qw.length, tw.length);
                                break;
                            }
                        }
                    }
                    if (matchedWords > 0 && queryWords.length > 0) {
                        const wordRatio = matchedWords / queryWords.length;
                        score = wordRatio * 30 + (matchedChars / normalizedQuery.length) * 20;
                        matchType = "words(" + matchedWords + "/" + queryWords.length + ")";
                    }
                }

                if (score > 0) {
                    candidates.push({ index: i, title: title, score: score, matchType: matchType });
                }
            }

            candidates.sort((a, b) => b.score - a.score);

            Log.info("MMM-SoundCloud: Top candidates:");
            for (let j = 0; j < Math.min(3, candidates.length); j++) {
                const c = candidates[j];
                Log.info("  " + (j + 1) + ". [" + c.score.toFixed(1) + "] " + c.title + " (" + c.matchType + ")");
            }

            if (candidates.length > 0 && candidates[0].score >= 10) {
                const best = candidates[0];
                Log.info("MMM-SoundCloud: Selected track: " + best.title + " (score: " + best.score.toFixed(1) + ")");

                this.savedTrackIndex = savedState.trackIndex;
                this.savedPosition = savedState.position;
                this.savedIsPaused = savedState.isPaused;
                this.isPlayingSearched = true;
                this.widget.skip(best.index);

                this.sendNotification("MUSIC_SEARCH_RESULT", {
                    found: true,
                    query: query,
                    track: best.title,
                    artist: sounds[best.index].user ? sounds[best.index].user.username : "",
                    source: "local"
                });
            } else {
                Log.warn("MMM-SoundCloud: No track found for query: " + query);
                this.isPlayingSearched = false;
                this.savedTrackIndex = -1;

                this.sendNotification("MUSIC_SEARCH_RESULT", {
                    found: false,
                    query: query,
                    message: "Khong tim thay bai hat"
                });
            }
        });
    },

    // Normalize text for better matching (remove diacritics, lowercase)
    normalizeText: function (text) {
        if (!text) return "";

        // Vietnamese diacritics normalization
        return text
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")  // Remove diacritics
            .replace(/[đ]/g, "d")
            .replace(/[Đ]/g, "d")
            .replace(/[^a-z0-9\s]/g, " ")  // Keep only alphanumeric
            .replace(/\s+/g, " ")
            .trim();
    },

    // Return to saved track after searched song finishes
    returnToSavedTrack: function () {
        if (!this.widget || !this.widgetReady || this.savedTrackIndex < 0) {
            this.isPlayingSearched = false;
            return;
        }

        Log.info("MMM-SoundCloud: Returning to saved playlist and track");
        Log.info("MMM-SoundCloud: Saved index: " + this.savedTrackIndex + ", position: " + this.savedPosition);

        this.isPlayingSearched = false;

        const savedIndex = this.savedTrackIndex;
        const savedPos = this.savedPosition;
        const wasPaused = this.savedIsPaused;
        const playlistUrl = this.savedPlaylistUrl;

        // Reset saved state
        this.savedTrackIndex = -1;
        this.savedPosition = 0;
        this.savedIsPaused = true;

        // Check if we need to reload the original playlist (for global search)
        // We detect this by checking if the current widget is playing a single track
        this.widget.getSounds((sounds) => {
            const needReloadPlaylist = !sounds || sounds.length <= 1;

            if (needReloadPlaylist && playlistUrl) {
                // Load the original playlist
                Log.info("MMM-SoundCloud: Reloading original playlist: " + playlistUrl);
                this.widget.load(playlistUrl, {
                    auto_play: !wasPaused,
                    show_artwork: this.config.showArtwork,
                    callback: () => {
                        Log.info("MMM-SoundCloud: Playlist reloaded, skipping to track " + savedIndex);
                        // After playlist loads, skip to saved track
                        setTimeout(() => {
                            this.widget.skip(savedIndex);
                            setTimeout(() => {
                                if (savedPos > 0) {
                                    this.widget.seekTo(savedPos);
                                }
                                if (wasPaused) {
                                    this.widget.pause();
                                }
                                Log.info("MMM-SoundCloud: Restored to previous state");
                            }, 300);
                        }, 500);
                    }
                });
            } else {
                // Already on the playlist, just skip to the track
                this.widget.skip(savedIndex);
                setTimeout(() => {
                    if (savedPos > 0) {
                        this.widget.seekTo(savedPos);
                    }
                    if (wasPaused) {
                        this.widget.pause();
                    } else {
                        this.widget.play();
                    }
                    Log.info("MMM-SoundCloud: Restored to previous state");
                }, 500);
            }
        });
    },

    // Get current state for LLM
    getState: function () {
        return {
            isPaused: this.isPaused,
            volume: this.volume,
            isShuffled: this.isShuffled,
            track: this.currentTrack ? {
                title: this.currentTrack.title,
                artist: this.currentTrack.user ? this.currentTrack.user.username : ""
            } : null
        };
    }
});
