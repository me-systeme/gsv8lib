"""
gsv8_readmultiple_thread_dll.py
-------------------------------

Simple test script for a GSV-8 amplifier using MEGSV86 (Windows DLL).

- Activates the GSV-8 via COM port
- Sets the GSV-8 transmission rate (sample_frequency)
- Starts a worker thread that periodically calls GSV86readMultiple()
  according to refresh_ms
- The thread runs for measurement_duration_s seconds
- At the end, the total number of acquired measurement *frames*
  is printed

Requirements:
- MEGSV86x64.dll (or 32-bit variant) in the same directory as this script
- GSV-8 reachable via the given COM port
"""

import sys
import time
import threading
from pathlib import Path
from ctypes import (
    WinDLL, byref,
    c_int, c_double, c_char_p, POINTER
)
import ctypes as C

# -----------------------------
# Configuration
# -----------------------------

# Name of the DLL file (adapt to your system)
DLL_NAME = "MEGSV86x64.dll"   # e.g. "MEGSV86w32.dll" or your exact DLL name

# COM port number used by the device
# Example: COM3 -> COM_PORT = 3
COM_PORT = 3

# Transmission frequency of the GSV-8 in Hz
sample_frequency = 6000.0
# Device sends sample_frequency frames per second
# (so one frame every 1000/sample_frequency ms)

# Number of mapped value objects (channels)
# For a standard GSV-8 with all 8 channels mapped, this is 8.
# If you have a different mapping, adjust accordingly.
NUM_OBJECTS = 8

# Sampling rate of the worker thread in milliseconds
# (time between two GSV86readMultiple() calls)
refresh_ms = 10

# Maximum number of *frames* we want to read per call
# Internally we pass frames * NUM_OBJECTS as "count" to the DLL.
max_frames_per_call = 1500

# Total measurement duration in seconds
measurement_duration_s = 1.0

# -----------------------------
# Load DLL + declare signatures
# -----------------------------

dll_path = Path(__file__).with_name(DLL_NAME)
if not dll_path.exists():
    raise FileNotFoundError(f"'{DLL_NAME}' was not found next to {__file__}")

MEGSV = WinDLL(str(dll_path))

# Function signatures we use
MEGSV.GSV86actExt.argtypes = [c_int]
MEGSV.GSV86actExt.restype = c_int

MEGSV.GSV86release.argtypes = [c_int]
MEGSV.GSV86release.restype = c_int

MEGSV.GSV86startTX.argtypes = [c_int]
MEGSV.GSV86startTX.restype = c_int

MEGSV.GSV86stopTX.argtypes = [c_int]
MEGSV.GSV86stopTX.restype = c_int

MEGSV.GSV86setFrequency.argtypes = [c_int, c_double]
MEGSV.GSV86setFrequency.restype = c_int

MEGSV.GSV86getFrequency.argtypes = [c_int]
MEGSV.GSV86getFrequency.restype = c_double

MEGSV.GSV86getDataRateRange.argtypes = [c_int, POINTER(c_double), POINTER(c_double)]
MEGSV.GSV86getDataRateRange.restype = c_int

MEGSV.GSV86clearDeviceBuf.argtypes = [c_int]
MEGSV.GSV86clearDeviceBuf.restype = c_int

MEGSV.GSV86clearDLLbuffer.argtypes = [c_int]
MEGSV.GSV86clearDLLbuffer.restype = c_int

MEGSV.GSV86readMultiple.argtypes = [
    c_int,               # ComNo
    c_int,               # Chan (0 = all objects)
    POINTER(c_double),   # out
    c_int,               # count (max number of values)
    POINTER(c_int),      # valsread
    POINTER(c_int),      # ErrFlags
]
MEGSV.GSV86readMultiple.restype = c_int

MEGSV.GSV86getLastErrorText.argtypes = [c_int, c_char_p]
MEGSV.GSV86getLastErrorText.restype = c_int

def dll_error_text(com: int) -> str:
    """Return last error text from DLL for the given COM port."""
    buf = C.create_string_buffer(256)
    try:
        MEGSV.GSV86getLastErrorText(com, buf)
        return buf.value.decode(errors="ignore")
    except Exception:
        return ""
    
def check(retcode: int, func_name: str, com: int = COM_PORT):
    """
    Helper: raise RuntimeError if a DLL function failed.

    For most functions, GSV_OK (0) is success and GSV_ERROR (-1) is failure.
    """
    if retcode < 0:
        msg = dll_error_text(com)
        raise RuntimeError(
            f"{func_name} failed (rc={retcode})" + (f": {msg}" if msg else "")
        )

# -----------------------------
# Worker thread
# -----------------------------

class ReadMultipleWorker(threading.Thread):
    """
    Worker thread that cyclically calls GSV86readMultiple() and counts
    the total number of acquired measurement frames.
    """

    def __init__(
        self,
        refresh_ms: int,
        max_frames: int,
        num_objects: int,
        stop_event: threading.Event,
    ):
        super().__init__(daemon=True)
        self._refresh_ms = refresh_ms
        self._max_frames = max_frames
        self._num_objects = num_objects
        self._stop_event = stop_event

        # Total number of acquired frames
        self.total_samples = 0

        # Timestamp when the first values are received
        self._started_measuring = False
        self.t_start: float | None = None

        # Buffer for DLL call
        self._buffer_len = self._max_frames * self._num_objects
        self._out = (c_double * self._buffer_len)()
        self._valsread = c_int(0)
        self._errflags = c_int(0)

    def run(self):
        refresh_s = self._refresh_ms / 1000.0

        while not self._stop_event.is_set():
            try:
                rc = MEGSV.GSV86readMultiple(
                    COM_PORT,
                    0,  # Chan = 0 -> all mapped objects
                    self._out,
                    self._buffer_len,
                    byref(self._valsread),
                    byref(self._errflags),
                )
            except Exception as e:
                print(f"GSV86readMultiple() error: {e}", file=sys.stderr)
                rc = -1

            # rc meanings (according to DLL manual):
            #  GSV_TRUE (1): values were read, *valsread > 0
            #  GSV_OK   (0): no values available / buffer empty
            #  GSV_ERROR(-1): error
            if rc < 0:
                # Internal error -> we break the loop
                msg = dll_error_text(COM_PORT)
                print(f"GSV86readMultiple() failed: {msg}", file=sys.stderr)
                break

            if rc == 1 and self._valsread.value > 0:
                # Number of values returned by DLL
                values_read = self._valsread.value
                if values_read % self._num_objects != 0:
                    print("WARN: valsread =", values_read, "is not divisible by NUM_OBJECTS =", self._num_objects)
                # Each "frame" consists of num_objects values
                frames = values_read // self._num_objects

                if frames > 0:
                    if not self._started_measuring:
                        self.t_start = time.perf_counter()
                        self._started_measuring = True
                    self.total_samples += frames

            # Wait until the next read
            time.sleep(refresh_s)

# -----------------------------
# Device initialization
# -----------------------------

def init_device():
    print(f"Connecting to GSV-8 via MEGSV86 on COM{COM_PORT} ...")

    # Activate device on given COM port
    check(MEGSV.GSV86actExt(COM_PORT), "GSV86actExt")

    MEGSV.GSV86stopTX(COM_PORT)
    # Get allowed data rate range from device
    dmax = c_double(0.0)
    dmin = c_double(0.0)
    check(
        MEGSV.GSV86getDataRateRange(COM_PORT, byref(dmax), byref(dmin)),
        "GSV86getDataRateRange",
    )
    print(f"Device data rate range: {dmin.value:.3f} .. {dmax.value:.3f} Hz")

    # Clip requested frequency to allowed range
    target = float(sample_frequency)
    if target < dmin.value or target > dmax.value:
        print(
            f"Requested frequency {sample_frequency} Hz out of range, "
            f"using clipped value {max(min(target, dmax.value), dmin.value):.6g} Hz."
        )
        target = max(min(target, dmax.value), dmin.value)

    check(MEGSV.GSV86setFrequency(COM_PORT, target), "GSV86setFrequency")

    # Start transmission
    check(MEGSV.GSV86startTX(COM_PORT), "GSV86startTX")
    eff = MEGSV.GSV86getFrequency(COM_PORT)
    print(f"Actual device frequency: {eff:.3f} Hz")

    # Clear device and DLL buffers
    MEGSV.GSV86clearDeviceBuf(COM_PORT)
    MEGSV.GSV86clearDLLbuffer(COM_PORT)

    print("Transmission started.\n")

# -----------------------------
# main
# -----------------------------

def main():
    init_device()

    stop_event = threading.Event()
    worker = ReadMultipleWorker(
        refresh_ms=refresh_ms,
        max_frames=max_frames_per_call,
        num_objects=NUM_OBJECTS,
        stop_event=stop_event,
    )

    worker.start()

    # 1) Wait until first measuring value arrives (worker sets t_start)
    while worker.t_start is None:
        time.sleep(0.001)

    try:
        # Main thread waits for measurement duration (or until Ctrl+C)
        while time.perf_counter() - worker.t_start < measurement_duration_s:
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nMeasurement cancelled by user.")

    # Stop worker thread
    stop_event.set()
    worker.join(timeout=2.0)

    # Drain remaining values from DLL buffer
    buffer_len = max_frames_per_call * NUM_OBJECTS
    out_buf = (c_double * buffer_len)()
    valsread = c_int(0)
    errflags = c_int(0)

    while True:
        rc = MEGSV.GSV86readMultiple(
            COM_PORT,
            0,
            out_buf,
            buffer_len,
            byref(valsread),
            byref(errflags),
        )

        if rc < 0:
            msg = dll_error_text(COM_PORT)
            print(f"Final drain: GSV86readMultiple() failed: {msg}", file=sys.stderr)
            break

        if rc != 1 or valsread.value <= 0:
            # No more values available
            break

        values_read = valsread.value
        frames = values_read // NUM_OBJECTS
        worker.total_samples += frames

    elapsed = time.perf_counter() - worker.t_start
    print("Frames:", worker.total_samples)
    print("Time:", elapsed)
    print("Effective rate:", worker.total_samples / elapsed, "Hz")

    # Stop transmission and release device
    try:
        check(MEGSV.GSV86stopTX(COM_PORT), "GSV86stopTX")
    except RuntimeError as e:
        print(f"Note: stopTX reported: {e}", file=sys.stderr)

    try:
        check(MEGSV.GSV86release(COM_PORT), "GSV86release")
    except RuntimeError as e:
        print(f"Note: release reported: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()