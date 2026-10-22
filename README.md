# SCHOTT ColdVision CV-LS

Python driver for the SCHOTT ColdVision CV-LS fiber-optic light
source.

The CV-LS is controlled over an ASCII: every command is a
string starting with `&` and ending with a carriage return `\r`, and the
unit echoes the command back with the requested value. This driver talks to
the unit over its Ethernet socket interface. See the SCHOTT ColdVision Light Source Programming Guide
(D20980.026) for the full command reference.

## Installation

```bash
pip install .
```

For development:

```bash
pip install -e ".[dev]"
python -m pytest
```

## Usage

```python
from coldvision import ColdVision

with ColdVision() as light:
    light.connect("192.168.0.2")  # default port 50811
    light.initialize()
    print(light.product_name, light.model, light.serial_number)

    light.set_power(500)      # common channel, 0-1000
    light.set_enabled(True)   # turn the output on

    print("LED temp:", light.get_led_temperature())
    print("Fan speed:", light.get_fan_speed())

    light.set_enabled(False)
    light.save_settings()
```

See [USAGE.md](USAGE.md) for more information.
