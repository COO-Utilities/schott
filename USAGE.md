# Using the ColdVision CV-LS driver

Task-oriented guide to `coldvision.py`. Section numbers (§) refer to the
SCHOTT ColdVision Light Source Programming Guide, D20980.026 Rev A.

- [Connect and identify](#connect-and-identify)
- [Power and output](#power-and-output)
- [Equalizer (closed loop)](#equalizer-closed-loop)
- [Gated mode, all channels on one input](#gated-mode-all-channels-on-one-input)
- [Triggered strobe](#triggered-strobe)
- [Status and diagnostics](#status-and-diagnostics)
- [Saving settings](#saving-settings)
- [Errors and troubleshooting](#errors-and-troubleshooting)
- [Quick reference](#quick-reference)

## Connect and identify

The unit listens on TCP port 50811 with a factory static IP of
`192.168.0.2` (§ Remote Operation).

```python
from coldvision import ColdVision

with ColdVision() as light:
    light.connect("192.168.0.2")          # port=50811, timeout=2.0 by default
    if not light.initialize():
        raise SystemExit("Unit did not identify itself")
    print(light.product_name, light.model, light.serial_number, light.firmware_revision)
```

- `connect()` raises `ConnectionError` if the socket can't be opened.
- `initialize()` returns `False` only if the product name query fails. Model,
  serial number and firmware are best-effort: if the unit rejects one of those
  queries, a warning is logged and the attribute is left as `None`.
- The `with` block disconnects on exit; it does not connect for you.
- Pass `ColdVision(log=False)` to silence logging.

## Power and output

Channel numbers: `0` = common (all channels), `1`-`4` = individual channels.

```python
light.set_power(500)               # common power limit, 0-1000
light.set_power(800, channel=2)    # one channel
light.set_enabled(True)            # LED on (same as the front button)
light.set_enabled(False, channel=3)

print(light.get_power(), light.get_enabled())
```

Setters return the value the unit acknowledged.

## Equalizer (closed loop)

The equalizer holds light output at a target using the internal light
feedback sensor (§3.4). Target, feedback and output are 0-4095; the driver
handles the hex encoding the unit uses.

```python
import time
from coldvision import EqualizerStatus

light.set_equalizer_enabled(True)
light.set_equalizer_target(2000)

for _ in range(20):
    status = light.get_equalizer_status()
    print(status)                       # e.g. EqualizerStatus.WAITING_FOR_DELAY
    if status == EqualizerStatus.LOCKED:
        break
    time.sleep(0.5)

print("feedback", light.get_equalizer_feedback(), "target", light.get_equalizer_target())
```

| `EqualizerStatus` | Code | Meaning |
|---|---|---|
| `NOT_STABLE` | 0 | Loop not yet stable |
| `LOCKED` | 1 | Locked and stable |
| `WAITING_FOR_DELAY` | 2 | Waiting for the start-up delay after power-on |
| `INTENSITY_LOW` | 4 | Output below target |
| `INTENSITY_HIGH` | 6 | Output above target |
| `OVER_RANGE` | 8 | Can't reach target: intensity too low |
| `UNDER_RANGE` | 10 | Can't reach target: intensity too high |

`OVER_RANGE` / `UNDER_RANGE` mean the target isn't reachable at the current
power limit; adjust `set_power()` or the target. If the unit reports a code
not in this table, `get_equalizer_status()` returns the raw `int` and logs a
warning.

`set_equalizer_delay()` sets the start-up delay (0-500). The programming
guide does not give a unit for it.

## Gated mode, all channels on one input

There is no dedicated method for this yet; send the commands directly. The
light stays on for as long as the gate input is held, on every channel.
Wire the gate signal to Multiport digital input 1.

```python
light._transact("RM0")      # continuous strobe off         (§3.2.1)
light._transact("PM0")      # triggered strobe off          (§3.3.1)
light._transact("J0,1")     # any digital input drives all channels (§3.1.2)
for ch in range(1, 5):
    light._transact(f"J{ch},0")   # 0 = active low (default)  (§3.1.5)
light.set_enabled(True)
```

Check polarity on the bench. The guide only says that with active low
(the default), pulling an input to GND turns that channel off. Swap `0` for
`1` if the logic comes out inverted.

## Triggered strobe

Each trigger edge fires one fixed-length pulse (§3.3). This is not gated
mode: the pulse length comes from the on time, not the input width.

```python
from coldvision import TriggerEdge

light.set_trigger_combined(True)          # one input triggers all channels
for ch in range(1, 5):
    light.set_trigger_edge(TriggerEdge.RISING, channel=ch)
    light.set_trigger_delay(0, channel=ch)       # microseconds
    light.set_trigger_on_time(500, channel=ch)   # microseconds
light.set_triggered_strobe_enabled(True)
```

- `channel` is required and must be 1-4 for delay, on time and edge.
- Delay and on time are 0-1,000,000 us. The unit adds a fixed 4-9 us system
  delay, and its timer has 5 us resolution.
- `set_trigger_single_channel(True)` makes the unit behave as a single
  channel device during triggered strobe; `False` is quad channel.

## Status and diagnostics

```python
from coldvision import ErrorFlags

print(light.get_led_temperature(), "C")     # LED PCB
print(light.get_board_temperature(), "C")   # main PCB
print(light.get_fan_speed(), "RPM")

flags = light.get_error_flags()
if flags:
    print("Faults:", flags)                 # e.g. ErrorFlags.FAN_ERROR
if ErrorFlags.LED_TEMP_ERROR in flags:
    ...
```

| `ErrorFlags` | Value |
|---|---|
| `NONE` | 0 |
| `FAN_ERROR` | 1 |
| `LED_TEMP_ERROR` | 2 |
| `ANY_FAULT` | 256 |

The guide describes the error flags as an 8 bit value but puts "Any Faults"
on bit 8, which doesn't fit in 8 bits. The driver follows the text (256). If a
faulted unit reports 128 instead, that is the real "any fault" bit; it will
show as `<ErrorFlags: 128>` rather than being dropped.

## Saving settings

Changes are lost on power-cycle unless saved.

```python
light.save_settings()      # store current settings to non-volatile memory
light.restore_settings()   # reload the stored settings
light.reboot()             # full reboot; the socket connection will drop
```

## Errors and troubleshooting

| Exception | Raised when |
|---|---|
| `ConnectionError` | `connect()` can't open the socket |
| `RuntimeError("ColdVision is not connected")` | A command is sent before `connect()` |
| `ColdVisionError` | Send failed, or no reply before the timeout |
| `ColdVisionNack` | The unit rejected the command (subclass of `ColdVisionError`) |
| `ValueError` | An argument is out of range; nothing is sent to the unit |

**Negative acknowledgements.** When the unit doesn't recognise a command or
parameter it replies with `&n` followed by the command. For example, the
unsupported query `&ZM?` came back as `&nzM`. The exception message includes
the unit's raw reply. The guide documents the format as `&nXpY`, but real
replies may not include the `p`.

**No reply / timeouts.** Check the IP address, and that nothing else is
connected to the legacy socket (it accepts one client at a time). The default
read timeout is 2 s; pass `connect(host, timeout=5.0)` for slow networks.

**Talking to the unit by hand.** Any terminal that speaks Telnet works on port
50811. From Python, `light._transact("<command>")` sends a raw command
without the leading `&` or trailing `\r` and returns the reply value.

## Quick reference

| Method | Command | § |
|---|---|---|
| `get_product_name()` | `Q` | 1.9.1 |
| `get_firmware_revision()` | `F?` | 1.9.2 |
| `get_serial_number()` | `Z?` | 1.9.3 |
| `get_model()` | `ZF?` | 1.9.4 |
| `get_power(ch)` / `set_power(v, ch)` | `I#,#` | 3.1.7.2 |
| `get_enabled(ch)` / `set_enabled(on, ch)` | `L#,#` | 3.1.6.2 |
| `get_equalizer_enabled()` / `set_equalizer_enabled(on)` | `E#` | 3.4.1 |
| `get_equalizer_delay()` / `set_equalizer_delay(v)` | `EI#` | 3.4.2 |
| `get_equalizer_target()` / `set_equalizer_target(v)` | `EE#` | 3.4.3 |
| `get_equalizer_feedback()` | `EV?` | 3.4.4 |
| `get_equalizer_output()` | `ED?` | 3.4.5 |
| `get_equalizer_status()` / `is_equalizer_locked()` | `ES?` | 1.4 |
| `get_triggered_strobe_enabled()` / `set_triggered_strobe_enabled(on)` | `PM#` | 3.3.1 |
| `get_trigger_combined()` / `set_trigger_combined(on)` | `PJ0,#` | 3.3.2 |
| `get_trigger_single_channel()` / `set_trigger_single_channel(single)` | `PB#` | 3.3.3 |
| `get_trigger_delay(ch)` / `set_trigger_delay(us, ch)` | `PD#,#` | 3.3.4.2 |
| `get_trigger_on_time(ch)` / `set_trigger_on_time(us, ch)` | `PO#,#` | 3.3.5.2 |
| `get_trigger_edge(ch)` / `set_trigger_edge(edge, ch)` | `PJ#,#` | 3.3.6 |
| `get_led_temperature()` | `?LT` | 1.1.2.2 |
| `get_board_temperature()` | `?BT` | 1.1.1 |
| `get_fan_speed()` | `?G` | 1.3 |
| `get_error_flags()` | `C?` | 1.7 |
| `save_settings()` | `S` | 2.1.1 |
| `restore_settings()` | `T` | 2.1.2 |
| `reboot()` | `O4` | 5.2 |
