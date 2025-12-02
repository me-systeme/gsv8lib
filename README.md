# gsv86lib

`gsv86lib` is a Python package that provides a convenient interface to the  
**ME-Systeme GSV-8** measurement amplifier via serial communication.

It is based on the original ME-Systeme Python library (`gsv8pypi_python3`) and
repackages it as a modern Python package with a proper module namespace and
relative imports, so it can be installed and reused across multiple projects.

Typical use cases:

- Reading strain gauge data from a GSV-8
- Continuous streaming with `StartTransmission()`
- Triggering digital I/O based on thresholds
- Building custom GUIs or data logging tools

---

## Features

- Pure Python, no platform-specific DLLs required
- Serial communication (USB-CDC, virtual COM port)
- Access to the full GSV-8 feature set:
  - Measurement values for up to 8 channels
  - Data rate configuration
  - Start/Stop transmission
  - Digital I/O configuration
  - Thresholds and trigger functions
  - CSV recording helpers (from original library)
- Usable on Windows and Linux

---

## Installation

`gsv86lib` is not published on PyPI.  
Install it directly from the Git repository:

```bash
pip install git+https://github.com/me-systeme/gsv86lib.git
```

## Requirements

- Python 3.8+
- `pyserial` (installed automatically as dependency)

## Basic Usage

```python
from gsv86lib import gsv86

# Open GSV-8 device on given serial port
# Example: "COM5" on Windows, "/dev/ttyACM0" on Linux
dev = gsv86("COM5", 230400)

# Optional: configure data rate (Hz)
dev.writeDataRate(50.0)

# Start continuous transmission
dev.StartTransmission()

# Read a single measurement frame
measurement = dev.ReadValue()

# Access individual channels (1..8)
ch1 = measurement.getChannel1()
ch2 = measurement.getChannel2()

print("Channel 1:", ch1)
print("Channel 2:", ch2)

# Stop transmission when done
dev.StopTransmission()
``` 

You can build more complex applications on top of this, such as real-time
visualization, logging, or integration into test benches.


## API Overview

`gsv86lib` exposes the original ME-Systeme API, including (non-exhaustive):

- Measurement
  - `ReadValue()`
  - `ReadMultiple()`
  - `writeDataRate(frequency)`
  - `StartTransmission()`
  - `StopTransmission()`
- Digital I/O
  - `getDIOdirection()`, `setDIOdirection()`
  - `getDIOlevel()`, `setDIOlevel()`
  - `setDIOtype()`, `setInputToTaraInputForChannel()`, …
- Thresholds / Trigger
  - `readDIOthreshold()`, `writeDIOthreshold()`
  - `setOutputHighByThreshold()`, `setOutputHighIfInsideWindow()`, …
- Scaling and sensor configuration
  - `setUserScaleBySensor()`
  - Input type configuration (bridge, single-ended, temperature, …)

For a more detailed API reference, see the original ME-Systeme documentation
(e.g. `gsv86.html` / GSV-8PyPi 1.0.0 documentation or `documentation.pdf`) or the docstrings in the
source files.

## Project Structure

Typical layout of this package:

```text
gsv86lib/
├─ pyproject.toml
├─ README.md
├─ LICENSE
└─ src/
   └─ gsv86lib/
      ├─ __init__.py
      ├─ gsv86.py
      ├─ CSVwriter.py
      ├─ GSV_BasicMeasurement.py
      ├─ GSV_Exceptions.py
      ├─ GSV6_AnfrageCodes.py
      ├─ GSV6_BasicFrameType.py
      ├─ GSV6_ErrorCodes.py
      ├─ GSV6_FrameRouter.py
      ├─ GSV6_MessFrameHandler.py
      ├─ GSV6_Protocol.py
      ├─ GSV6_SeriallLib.py
      ├─ GSV6_UnitCodes.py
      └─ ThreadSafeVar.py
```
The public entry point for user code is `gsv86lib.gsv86`.

## License

This package is derived from the original ME-Systeme GSV-8 Python library.
Please refer to the license information provided by ME-Systeme and add your
own license information here as appropriate for your project.