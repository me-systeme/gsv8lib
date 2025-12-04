"""
gsv8_readmultiple_thread.py
---------------------------

Simple test script for a GSV-8 amplifier using gsv86lib.

- Sets the GSV-8 transmission rate (sample_frequency)
- Starts a worker thread that periodically calls ReadMultiple()
  according to refresh_ms
- The thread runs for 10 seconds
- At the end, the total number of acquired measurement frames
  is printed

Requirements:
- gsv86lib installed: https://github.com/me-systeme/gsv86lib
- GSV-8 reachable via serial port
"""

import sys
import time
import threading

from gsv86lib import gsv86

# -----------------------------
# Configuration
# -----------------------------

# Adjust the serial port!
PORT = "COM3"          # e.g. "COM3" on Windows or "/dev/ttyACM0" on Linux
BAUDRATE = 115200

# Transmission frequency of the GSV-8 in Hz
sample_frequency = 6000.0     # the device sends sample_frequency frames per second (so one frame every 1000/sample_frequency ms)

# Sampling rate of the worker thread in milliseconds
# (time between two ReadMultiple() calls)
# could be greater than 1000/sample_frequency because otherwise there could be empty reads 
# if refresh_ms could be divided by 1000/sample_frequency: the thread reads refresh_ms*sample_frequency/1000 frames on every call 
refresh_ms = 10            

# Maximum number of frames to read per ReadMultiple() call
# must be greater than refresh_ms*sample_frequency/1000 because otherwise there are more frames than max_frames_per_call in the queue
max_frames_per_call = 1500   

# every second the threads reads max_frames_per_call * 1000/refresh_ms frames, must be greater than sample_frequency

# Total measurement duration in seconds
# after measurement_duration_s seconds the application must register measurement_duration_s * sample_frequency frames
#  example: after 10s the application must register 10 * sample_frequency frames
measurement_duration_s = 1.0     
 


# -----------------------------
# Worker thread
# -----------------------------
class ReadMultipleWorker(threading.Thread):
    """
    Worker thread that cyclically calls ReadMultiple() and counts
    the total number of acquired measurement frames.
    """

    def __init__(self, device: gsv86, refresh_ms: int, max_frames: int, stop_event: threading.Event):
        super().__init__(daemon=True)
        self._dev = device
        self._refresh_ms = refresh_ms
        self._max_frames = max_frames
        self._stop_event = stop_event
        self.total_samples = 0   # total number of acquired frames
        self._started_measuring = False
        self.t_start = None

    def run(self):
        refresh_s = self._refresh_ms / 1000.0

        while not self._stop_event.is_set():
            try:
                frames = self._dev.ReadMultiple(max_count=self._max_frames)
            except Exception as e:
                print(f"ReadMultiple() error: {e}", file=sys.stderr)
                frames = None

            if frames:
                # frames is a list of measurement frames -> count them
                
                if not self._started_measuring:
                    self.t_start = time.perf_counter()
                    #self.total_samples = 0
                    self._started_measuring = True
                self.total_samples += len(frames)

            # wait until the next ReadMultiple() call
            time.sleep(refresh_s)


# -----------------------------
# Device initialization
# -----------------------------
def init_device() -> gsv86:
    print(f"Connecting to GSV-8 on {PORT} @ {BAUDRATE} baud ...")
    dev = gsv86(PORT, BAUDRATE)

    # Set device transmission rate (if supported)
    try:
        dev.writeDataRate(sample_frequency)
        print(f"Requested sample frequency: {sample_frequency:.3f} Hz")
    except Exception as e:
        print(f"Warning: writeDataRate({sample_frequency}) failed: {e}", file=sys.stderr)

    # Start streaming
    try:
        dev.StartTransmission()
        print("StartTransmission() executed – device is now streaming.")
    except Exception as e:
        print(f"Error: StartTransmission() failed: {e}", file=sys.stderr)

    # small delay to allow internal buffering
    #time.sleep(0.5)

    return dev


# -----------------------------
# main
# -----------------------------
def main():
    dev = init_device()

    stop_event = threading.Event()
    worker = ReadMultipleWorker(
        device=dev,
        refresh_ms=refresh_ms,
        max_frames=max_frames_per_call,
        stop_event=stop_event
    )

    #print(f"Starting measurement for {measurement_duration_s} seconds ...")
    worker.start()
    
    # 1) Wait until first measuring value
    while worker.t_start is None:
        time.sleep(0.001)
    
    try:
        # main thread waits for measurement duration (or until Ctrl+C)
        while time.perf_counter() - worker.t_start < measurement_duration_s:
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nMeasurement cancelled by user.")

    # stop worker thread
    #print("Calling StopTransmission() ...", time.perf_counter() - device_start)
    stop_event.set()
    worker.join(timeout=2.0)

    # drain remaining frames before stopping transmission
    while True:
        frames = dev.ReadMultiple(max_frames_per_call)
        if not frames:
            break
        worker.total_samples += len(frames)

    elapsed = time.perf_counter() - worker.t_start
    print("Frames:", worker.total_samples)
    print("Time:", elapsed)
    print("Effective rate:", worker.total_samples / elapsed, "Hz")
    try:
        dev.StopTransmission()
    except Exception as e:
        print(f"Note: StopTransmission() reported: {e}", file=sys.stderr)



if __name__ == "__main__":
    main()
