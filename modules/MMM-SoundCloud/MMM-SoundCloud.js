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
        height: "166"
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
        this.originalOrder = [];
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

        const progressBar = document.createElement("div");
        progressBar.className = "progress-bar";
        progressBar.id = "progress-bar";
        const progress = this.duration > 0 ? (this.currentPosition / this.duration) * 100 : 0;
        progressBar.style.width = progress + "%";
        progressContainer.appendChild(progressBar);

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
            case "DOM_OBJECTS_CREATED":
                this.initWidget();
                break;
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
            // Track finished, next will auto-play in playlist
            this.isPaused = true;
            this.updatePlayStatus();
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
            this.widget.next();
        }
    },

    prev: function () {
        if (this.widget && this.widgetReady) {
            this.widget.prev();
        }
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

        // Get all sounds and shuffle
        this.widget.getSounds((sounds) => {
            if (!sounds || sounds.length === 0) return;

            if (this.isShuffled) {
                // Store original order
                this.originalOrder = sounds.map((s, i) => i);

                // Pick a random track to play
                const randomIndex = Math.floor(Math.random() * sounds.length);
                this.widget.skip(randomIndex);
                Log.info("MMM-SoundCloud: Shuffle ON - playing random track");
            } else {
                Log.info("MMM-SoundCloud: Shuffle OFF");
            }
        });

        this.sendNotification("MUSIC_SHUFFLE_CHANGED", { isShuffled: this.isShuffled });
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
