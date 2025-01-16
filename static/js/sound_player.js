class SoundPlayer {
    constructor() {
        this.sounds = new Map();
        this.currentSound = null;
        this.audioContext = null;
        this.initialize();
    }

    async initialize() {
        try {
            // Initialize Web Audio API
            this.initializeAudioContext();
            
            const response = await fetch('/sound/api/list_sounds');
            const data = await response.json();
            if (data.sounds) {
                await this.createSoundButtons(data.sounds);
            }
        } catch (error) {
            console.error('Error initializing sound player:', error);
        }
    }

    initializeAudioContext() {
        try {
            // Create AudioContext only on user interaction to comply with browser policies
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!this.audioContext && AudioContext) {
                this.audioContext = new AudioContext();
            }
        } catch (error) {
            console.error('Web Audio API not supported:', error);
        }
    }

    async createSoundButtons(soundFiles) {
        const container = document.getElementById('soundButtonsContainer');
        if (!container) return;

        container.innerHTML = '';
        const grid = document.createElement('div');
        grid.className = 'grid grid-cols-3 gap-2';

        for (const sound of soundFiles) {
            const button = document.createElement('button');
            button.className = 'px-3 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 text-sm';
            button.textContent = sound.filename.replace(/\.[^/.]+$/, ""); // Remove file extension

            // Create audio element with explicit type
            const audio = new Audio();
            audio.preload = 'auto';
            const sourceElement = document.createElement('source');
            sourceElement.src = `/sound/api/sounds/${sound.filename}`;
            sourceElement.type = sound.mime_type;
            audio.appendChild(sourceElement);

            // Add error handling
            audio.onerror = (e) => {
                console.error('Error loading sound:', e);
                button.classList.add('bg-red-500');
                button.disabled = true;
            };

            this.sounds.set(sound.filename, audio);

            button.addEventListener('click', () => {
                this.initializeAudioContext(); // Ensure AudioContext is initialized
                this.playSound(sound.filename);
            });
            grid.appendChild(button);
        }

        container.appendChild(grid);

        // Add a stop all sounds button
        const stopButton = document.createElement('button');
        stopButton.className = 'mt-2 px-3 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm';
        stopButton.textContent = 'Stop All Sounds';
        stopButton.addEventListener('click', () => this.stopAllSounds());
        container.appendChild(stopButton);
    }

    async playSound(filename) {
        try {
            // Stop currently playing sound if any
            if (this.currentSound) {
                this.currentSound.pause();
                this.currentSound.currentTime = 0;
            }

            const audio = this.sounds.get(filename);
            if (audio) {
                // Reset the audio to beginning if it was previously played
                audio.currentTime = 0;
                
                this.currentSound = audio;
                // Using both play promise and onended event for better compatibility
                const playPromise = audio.play();
                if (playPromise !== undefined) {
                    playPromise.catch(error => {
                        console.error('Error playing sound:', error);
                        this.currentSound = null;
                    });
                }

                audio.onended = () => {
                    this.currentSound = null;
                };
            }
        } catch (error) {
            console.error('Error in playSound:', error);
        }
    }

    stopAllSounds() {
        this.sounds.forEach(audio => {
            audio.pause();
            audio.currentTime = 0;
        });
        this.currentSound = null;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.soundPlayer = new SoundPlayer();
});