/* MMM-HandGesture
 * Virtual mouse cursor controlled by index finger via camera.
 * Uses MediaPipe Hand Landmarker for hand tracking.
 */

Module.register("MMM-HandGesture", {
    defaults: {
        smoothingFactor: 0.15,    // Lower = more responsive, higher = smoother
        pinchThreshold: 0.06,     // Normalized distance to detect pinch
        pinchReleaseThreshold: 0.08, // Must exceed this to release pinch (hysteresis)
        clickMaxDistance: 15,     // Max px movement to count as click (vs drag)
        cursorSize: 20,           // Cursor diameter in px
        hideDelay: 500,           // Ms before hiding cursor when no hand detected
        showCamera: false,        // Show small camera preview for debug
        flipX: true,              // Mirror camera horizontally
        cameraWidth: 640,
        cameraHeight: 480,
    },

    // Landmark indices
    LANDMARKS: {
        WRIST: 0,
        THUMB_TIP: 4,
        INDEX_MCP: 5,
        INDEX_PIP: 6,
        INDEX_TIP: 8,
        MIDDLE_TIP: 12,
        RING_TIP: 16,
        PINKY_TIP: 20,
        MIDDLE_MCP: 9,
        RING_MCP: 13,
        PINKY_MCP: 17,
    },

    // Gesture states
    STATE: {
        IDLE: "idle",
        POINTING: "pointing",
        PINCHING: "pinching",
        DRAGGING: "dragging",
    },

    getStyles: function () {
        return ["MMM-HandGesture.css"];
    },

    start: function () {
        Log.info("Starting module: " + this.name);

        // Cursor state
        this.cursorX = 0;
        this.cursorY = 0;
        this.smoothX = 0;
        this.smoothY = 0;
        this.gestureState = this.STATE.IDLE;
        this.cursorVisible = false;

        // Pinch tracking - freeze cursor position at pinch start
        this.pinchStartX = 0;
        this.pinchStartY = 0;
        this.pinchAnchorNormX = 0;  // Normalized wrist position at pinch start
        this.pinchAnchorNormY = 0;
        this.pinchMoveDistance = 0;

        // Timing
        this.lastHandTime = 0;
        this.hideTimer = null;

        // MediaPipe
        this.handLandmarker = null;
        this.videoElement = null;
        this.cursorElement = null;
        this.statusElement = null;
        this.detecting = false;

        // Drag target
        this.dragTarget = null;
    },

    getDom: function () {
        const wrapper = document.createElement("div");
        wrapper.className = "mmm-handgesture-wrapper";
        wrapper.innerHTML = "Hand Gesture";
        return wrapper;
    },

    notificationReceived: function (notification) {
        if (notification === "DOM_OBJECTS_CREATED") {
            this.createOverlayElements();
            this.initMediaPipe();
        }
    },

    // Create cursor and video elements on document.body
    createOverlayElements: function () {
        // Cursor
        this.cursorElement = document.createElement("div");
        this.cursorElement.className = "hand-cursor";
        this.cursorElement.style.width = this.config.cursorSize + "px";
        this.cursorElement.style.height = this.config.cursorSize + "px";
        document.body.appendChild(this.cursorElement);

        // Hidden video for camera feed
        this.videoElement = document.createElement("video");
        this.videoElement.className = "hand-gesture-video";
        this.videoElement.setAttribute("autoplay", "");
        this.videoElement.setAttribute("playsinline", "");
        this.videoElement.setAttribute("muted", "");
        if (this.config.showCamera) {
            this.videoElement.classList.add("debug");
        }
        document.body.appendChild(this.videoElement);

        // Status indicator
        this.statusElement = document.createElement("div");
        this.statusElement.className = "hand-gesture-status";
        this.statusElement.textContent = "Hand tracking loading...";
        this.statusElement.classList.add("visible");
        document.body.appendChild(this.statusElement);
    },

    // Load MediaPipe from CDN and initialize hand landmarker
    initMediaPipe: async function () {
        try {
            this.updateStatus("Loading MediaPipe...");

            // Dynamic import from CDN
            const vision = await this.loadVisionModule();
            const { HandLandmarker, FilesetResolver } = vision;

            this.updateStatus("Loading hand model...");

            const filesetResolver = await FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm"
            );

            this.handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
                baseOptions: {
                    modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
                    delegate: "GPU",
                },
                runningMode: "VIDEO",
                numHands: 1,
            });

            Log.info("MMM-HandGesture: Hand Landmarker initialized");
            this.updateStatus("Starting camera...");

            await this.startCamera();
            this.updateStatus("Hand tracking active");

            // Hide status after 3 seconds
            setTimeout(() => {
                if (this.statusElement) {
                    this.statusElement.classList.remove("visible");
                }
            }, 3000);

            // Start detection loop
            this.detecting = true;
            this.detectLoop();

        } catch (error) {
            Log.error("MMM-HandGesture: Failed to initialize: " + error.message);
            this.updateStatus("Error: " + error.message);
        }
    },

    // Load the vision module via dynamic script loading
    loadVisionModule: function () {
        return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.type = "module";

            // Create a module script to import and expose the vision module
            const moduleScript = document.createElement("script");
            moduleScript.type = "module";
            moduleScript.textContent = `
                import { HandLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/vision_bundle.mjs";
                window.__mediapipeVision = { HandLandmarker, FilesetResolver };
                window.dispatchEvent(new Event("mediapipe-loaded"));
            `;
            document.head.appendChild(moduleScript);

            const onLoaded = () => {
                window.removeEventListener("mediapipe-loaded", onLoaded);
                if (window.__mediapipeVision) {
                    resolve(window.__mediapipeVision);
                } else {
                    reject(new Error("Failed to load MediaPipe vision module"));
                }
            };

            window.addEventListener("mediapipe-loaded", onLoaded);

            // Timeout after 30 seconds
            setTimeout(() => {
                window.removeEventListener("mediapipe-loaded", onLoaded);
                reject(new Error("MediaPipe load timeout"));
            }, 30000);
        });
    },

    // Start camera
    startCamera: async function () {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: this.config.cameraWidth },
                height: { ideal: this.config.cameraHeight },
                facingMode: "user",
            },
            audio: false,
        });

        this.videoElement.srcObject = stream;

        return new Promise((resolve) => {
            this.videoElement.onloadedmetadata = () => {
                this.videoElement.play();
                resolve();
            };
        });
    },

    // Main detection loop
    detectLoop: function () {
        if (!this.detecting || !this.handLandmarker || !this.videoElement) return;

        if (this.videoElement.readyState >= 2) {
            const timestamp = performance.now();
            try {
                const results = this.handLandmarker.detectForVideo(this.videoElement, timestamp);
                this.processResults(results);
            } catch (e) {
                // Skip frame on error
            }
        }

        requestAnimationFrame(() => this.detectLoop());
    },

    // Process hand landmark results
    processResults: function (results) {
        if (!results || !results.landmarks || results.landmarks.length === 0) {
            this.onHandLost();
            return;
        }

        const landmarks = results.landmarks[0];
        this.lastHandTime = Date.now();

        // Clear hide timer
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
            this.hideTimer = null;
        }

        // Get key landmark positions
        const indexTip = landmarks[this.LANDMARKS.INDEX_TIP];
        const indexPip = landmarks[this.LANDMARKS.INDEX_PIP];
        const thumbTip = landmarks[this.LANDMARKS.THUMB_TIP];
        const indexMcp = landmarks[this.LANDMARKS.INDEX_MCP];
        const middleTip = landmarks[this.LANDMARKS.MIDDLE_TIP];
        const ringTip = landmarks[this.LANDMARKS.RING_TIP];
        const pinkyTip = landmarks[this.LANDMARKS.PINKY_TIP];
        const middleMcp = landmarks[this.LANDMARKS.MIDDLE_MCP];
        const ringMcp = landmarks[this.LANDMARKS.RING_MCP];
        const pinkyMcp = landmarks[this.LANDMARKS.PINKY_MCP];
        const wrist = landmarks[this.LANDMARKS.WRIST];

        // Calculate pinch distance (thumb tip to index tip)
        const pinchDist = this.distance(thumbTip, indexTip);

        // Hysteresis: use different thresholds for entering vs leaving pinch
        const wasPinching = this.gestureState === this.STATE.PINCHING || this.gestureState === this.STATE.DRAGGING;
        const isPinching = wasPinching
            ? pinchDist < this.config.pinchReleaseThreshold
            : pinchDist < this.config.pinchThreshold;

        // --- Cursor position logic ---
        // While pinching/dragging: freeze cursor at pinch start, offset by wrist movement
        // While pointing: track index PIP (more stable than fingertip)
        if (isPinching && (this.gestureState === this.STATE.PINCHING || this.gestureState === this.STATE.DRAGGING)) {
            // Track wrist movement relative to pinch start anchor
            let wristNormX = wrist.x;
            if (this.config.flipX) wristNormX = 1 - wristNormX;

            const driftX = (wristNormX - this.pinchAnchorNormX) * window.innerWidth;
            const driftY = (wrist.y - this.pinchAnchorNormY) * window.innerHeight;

            this.cursorX = Math.max(0, Math.min(window.innerWidth, this.pinchStartX + driftX));
            this.cursorY = Math.max(0, Math.min(window.innerHeight, this.pinchStartY + driftY));

            // Update smooth position to match (no lerp during pinch)
            this.smoothX = this.cursorX;
            this.smoothY = this.cursorY;
        } else {
            // Use INDEX_PIP (joint above fingertip) for more stable cursor positioning
            // It moves less when the finger curls for pinch
            let rawX = indexPip.x * window.innerWidth;
            let rawY = indexPip.y * window.innerHeight;

            if (this.config.flipX) {
                rawX = window.innerWidth - rawX;
            }

            // Exponential smoothing
            const alpha = 1 - this.config.smoothingFactor;
            this.smoothX = this.smoothX + (rawX - this.smoothX) * alpha;
            this.smoothY = this.smoothY + (rawY - this.smoothY) * alpha;

            this.cursorX = Math.max(0, Math.min(window.innerWidth, this.smoothX));
            this.cursorY = Math.max(0, Math.min(window.innerHeight, this.smoothY));
        }

        // Check if index finger is extended
        const indexExtended = indexTip.y < indexMcp.y;

        // Check if other fingers are folded
        const middleFolded = middleTip.y > middleMcp.y;
        const ringFolded = ringTip.y > ringMcp.y;

        // Determine if hand is in pointing pose
        const isPointing = indexExtended && (middleFolded || ringFolded);

        // Show cursor
        this.showCursor();

        // --- Gesture state machine ---
        if (!isPointing && !isPinching) {
            if (this.gestureState === this.STATE.DRAGGING) {
                this.endDrag();
            } else if (this.gestureState === this.STATE.PINCHING) {
                this.endPinch();
            }
            this.gestureState = this.STATE.IDLE;
            this.updateCursorClass();
            this.updateCursorPosition();
            return;
        }

        switch (this.gestureState) {
            case this.STATE.IDLE:
                if (isPointing && !isPinching) {
                    this.gestureState = this.STATE.POINTING;
                } else if (isPinching) {
                    this.startPinch(wrist);
                }
                break;

            case this.STATE.POINTING:
                if (isPinching) {
                    this.startPinch(wrist);
                } else if (!isPointing) {
                    this.gestureState = this.STATE.IDLE;
                }
                break;

            case this.STATE.PINCHING:
                if (!isPinching) {
                    this.endPinch();
                    this.gestureState = isPointing ? this.STATE.POINTING : this.STATE.IDLE;
                } else {
                    // Check if wrist moved enough to be a drag
                    const dx = this.cursorX - this.pinchStartX;
                    const dy = this.cursorY - this.pinchStartY;
                    this.pinchMoveDistance = Math.sqrt(dx * dx + dy * dy);

                    if (this.pinchMoveDistance > this.config.clickMaxDistance) {
                        this.gestureState = this.STATE.DRAGGING;
                        this.dispatchMouseEvent("mousedown", this.pinchStartX, this.pinchStartY);
                    }
                }
                break;

            case this.STATE.DRAGGING:
                if (!isPinching) {
                    this.endDrag();
                    this.gestureState = isPointing ? this.STATE.POINTING : this.STATE.IDLE;
                } else {
                    this.dispatchMouseEvent("mousemove", this.cursorX, this.cursorY);
                }
                break;
        }

        this.updateCursorClass();
        this.updateCursorPosition();
    },

    // Start pinch gesture - lock cursor and record wrist anchor
    startPinch: function (wrist) {
        this.gestureState = this.STATE.PINCHING;
        // Freeze cursor at current position
        this.pinchStartX = this.cursorX;
        this.pinchStartY = this.cursorY;
        this.pinchMoveDistance = 0;

        // Record wrist normalized position as anchor for drift tracking
        this.pinchAnchorNormX = this.config.flipX ? (1 - wrist.x) : wrist.x;
        this.pinchAnchorNormY = wrist.y;
    },

    // End pinch - determine if it was a click
    endPinch: function () {
        if (this.pinchMoveDistance < this.config.clickMaxDistance) {
            // Short pinch = click
            this.dispatchMouseEvent("mousedown", this.pinchStartX, this.pinchStartY);
            this.dispatchMouseEvent("mouseup", this.pinchStartX, this.pinchStartY);
            this.dispatchMouseEvent("click", this.pinchStartX, this.pinchStartY);
            Log.info("MMM-HandGesture: Click at (" + Math.round(this.pinchStartX) + ", " + Math.round(this.pinchStartY) + ")");
        }
    },

    // End drag gesture
    endDrag: function () {
        this.dispatchMouseEvent("mouseup", this.cursorX, this.cursorY);
        this.dragTarget = null;
        Log.info("MMM-HandGesture: Drag ended at (" + Math.round(this.cursorX) + ", " + Math.round(this.cursorY) + ")");
    },

    // Handle when hand disappears from view
    onHandLost: function () {
        if (this.hideTimer) return;

        this.hideTimer = setTimeout(() => {
            this.hideCursor();

            if (this.gestureState === this.STATE.DRAGGING) {
                this.endDrag();
            }
            this.gestureState = this.STATE.IDLE;
            this.updateCursorClass();
        }, this.config.hideDelay);
    },

    // Calculate distance between two landmarks
    distance: function (a, b) {
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        return Math.sqrt(dx * dx + dy * dy);
    },

    // Update cursor position using transform (GPU accelerated)
    updateCursorPosition: function () {
        if (this.cursorElement) {
            this.cursorElement.style.transform =
                "translate3d(" + this.cursorX + "px, " + this.cursorY + "px, 0) translate(-50%, -50%)";
        }
    },

    // Update cursor CSS class based on state
    updateCursorClass: function () {
        if (!this.cursorElement) return;
        this.cursorElement.classList.remove("pinching", "dragging");

        if (this.gestureState === this.STATE.PINCHING) {
            this.cursorElement.classList.add("pinching");
        } else if (this.gestureState === this.STATE.DRAGGING) {
            this.cursorElement.classList.add("dragging");
        }
    },

    // Show cursor
    showCursor: function () {
        if (!this.cursorVisible && this.cursorElement) {
            this.cursorElement.classList.add("visible");
            this.cursorVisible = true;
        }
    },

    // Hide cursor
    hideCursor: function () {
        if (this.cursorVisible && this.cursorElement) {
            this.cursorElement.classList.remove("visible");
            this.cursorVisible = false;
        }
    },

    // Dispatch synthetic mouse event on element under cursor
    dispatchMouseEvent: function (type, x, y) {
        const target = document.elementFromPoint(x, y);
        if (!target) return;

        if (type === "mousedown") {
            this.dragTarget = target;
        }

        const eventTarget = (type === "mousemove" || type === "mouseup") && this.dragTarget
            ? this.dragTarget
            : target;

        const event = new MouseEvent(type, {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: x,
            clientY: y,
            button: 0,
        });

        eventTarget.dispatchEvent(event);
    },

    // Update status text
    updateStatus: function (text) {
        if (this.statusElement) {
            this.statusElement.textContent = text;
        }
        Log.info("MMM-HandGesture: " + text);
    },

    // Cleanup on suspend
    suspend: function () {
        this.detecting = false;
        this.hideCursor();

        if (this.videoElement && this.videoElement.srcObject) {
            this.videoElement.srcObject.getTracks().forEach(track => track.stop());
        }
    },

    // Resume
    resume: function () {
        if (this.handLandmarker && !this.detecting) {
            this.startCamera().then(() => {
                this.detecting = true;
                this.detectLoop();
            });
        }
    },
});
