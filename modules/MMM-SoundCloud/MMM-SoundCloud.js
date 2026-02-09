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

        // Custom player info
        const playerInfo = document.createElement("div");
        playerInfo.className = "player-info";

        // Track info
        const trackInfo = document.createElement("div");
        trackInfo.className = "track-info";

        const trackName = document.createElement("div");
        trackName.className = "track-name";
        trackName.id = "track-name";
        trackName.textContent = this.currentTrack ? this.currentTrack.title : "Loading...";
        trackInfo.appendChild(trackName);

        const artistName = document.createElement("div");
        artistName.className = "artist-name";
        artistName.id = "artist-name";
        artistName.textContent = this.currentTrack ? this.currentTrack.user.username : "";
        trackInfo.appendChild(artistName);

        playerInfo.appendChild(trackInfo);

        // Status indicator
        const status = document.createElement("div");
        status.className = `play-status ${this.isPaused ? "paused" : "playing"}`;
        status.id = "play-status";
        playerInfo.appendChild(status);

        wrapper.appendChild(playerInfo);

        return wrapper;
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

        this.widget.bind(SC.Widget.Events.PLAY_PROGRESS, () => {
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
                const trackNameEl = document.getElementById("track-name");
                const artistNameEl = document.getElementById("artist-name");

                if (trackNameEl) trackNameEl.textContent = sound.title || "Unknown";
                if (artistNameEl) artistNameEl.textContent = sound.user ? sound.user.username : "";

                // Broadcast track change
                this.sendNotification("MUSIC_TRACK_CHANGED", {
                    title: sound.title,
                    artist: sound.user ? sound.user.username : "",
                    artwork: sound.artwork_url
                });
            }
        });
    },

    updatePlayStatus: function () {
        const statusEl = document.getElementById("play-status");
        if (statusEl) {
            statusEl.className = `play-status ${this.isPaused ? "paused" : "playing"}`;
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
        }
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
            track: this.currentTrack ? {
                title: this.currentTrack.title,
                artist: this.currentTrack.user ? this.currentTrack.user.username : ""
            } : null
        };
    }
});
