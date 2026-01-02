#!/usr/bin/env python3
"""
Flipper Zero IR Control Module
Sends IR commands to the Flipper Zero via serial communication using RAW IR transmission.

Adapted from the reference voice-tv-remote implementation.
"""

import sys
import time
import glob
import logging
from typing import Optional, Tuple, Dict

import serial

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# IR signals from Remote.ir file (parsed for direct transmission)
# Format: command_name -> (frequency, duty_cycle, raw_data)
IR_SIGNALS: Dict[str, Tuple[int, int, str]] = {
    "Ok": (38000, 33, "8900 4461 499 4442 498 2215 498 2218 497 2217 496 4441 498 2218 496 2243 445 2244 496 2218 470 2243 497 2216 498 2217 497 2215 499 4442 498 4442 497 4443 497"),
    "Menu": (38000, 33, "8903 4461 473 4466 474 2240 475 2240 474 4464 475 4465 475 2240 474 2239 475 2239 475 2239 475 2241 473 2240 474 2239 475 2239 475 4466 474 4466 474 2240 473"),
    "Guide": (38000, 33, "8901 4460 473 2242 472 2241 473 2241 473 2240 474 4468 472 4466 474 2241 473 2240 474 2243 471 2242 472 2243 471 2242 472 4467 472 2241 473 4466 474 4466 473"),
    "Info": (38000, 33, "8901 4488 445 4468 472 4469 471 2240 474 2243 497 4442 472 4471 469 2241 472 2241 473 2241 473 2242 472 2241 473 2239 475 2241 473 4469 471 2241 473 4467 473"),
    "Exit": (38000, 33, "8902 4460 474 2241 473 4466 474 2241 473 2239 475 4465 474 2241 473 2241 473 2240 474 2240 474 2238 476 2240 474 2240 475 4465 474 2241 473 4467 473 4467 473"),
    "Left": (38000, 33, "8904 4460 474 2240 474 4466 474 4467 473 2240 474 4465 474 4466 475 2239 474 2240 474 2239 475 2240 474 2240 474 2240 474 4466 474 4465 475 4463 477 2239 475"),
    "Right": (38000, 33, "8901 4459 475 4465 475 4466 474 4466 474 2239 475 4467 473 4467 473 2240 474 2238 476 2241 473 2240 474 2241 473 2239 475 2240 474 4465 474 4470 470 2240 474"),
    "Up": (38000, 33, "8903 4463 471 2239 475 2240 474 4467 473 2239 475 4466 474 4464 476 2240 474 2240 474 2240 474 2241 473 2241 473 2239 475 4466 473 2239 475 2240 474 4469 471"),
    "Down": (38000, 33, "8901 4463 497 4443 497 2215 473 4468 497 2219 470 4466 473 4468 473 2239 474 2240 474 2239 475 2240 474 2242 473 2243 470 2242 472 2242 473 2242 472 4466 474"),
    "Channel_up": (38000, 33, "8903 4461 473 4466 474 4467 472 2240 474 4465 475 2241 473 2240 474 2240 474 2241 473 2242 472 2239 475 2239 475 2239 475 4493 447 2240 475 4465 474 2240 474"),
    "Channel_down": (38000, 33, "8903 4464 470 2239 475 2240 474 4467 473 4467 473 2240 474 2238 475 2240 474 2241 473 2239 475 2241 473 2238 476 2241 473 2240 474 2239 475 4466 473 2241 473"),
    "Power": (38000, 33, "8902 4460 474 4465 475 2241 474 2240 474 2239 475 2240 474 2239 475 2242 472 2240 474 2241 473 2239 476 2239 474 2240 474 4465 475 4466 474 4464 475 4465 475"),
    "1": (38000, 33, "8902 4460 474 4465 475 2241 474 2240 474 2239 475 2240 474 2239 475 2242 472 2240 474 2241 473 2239 476 2239 474 2240 474 4465 475 4466 474 4464 475 4465 475"),
    "2": (38000, 33, "8875 4463 471 2242 472 4466 474 2241 473 2240 474 2268 446 2240 474 2240 475 2241 473 2238 476 2241 473 2241 473 2242 472 2241 473 4468 472 4466 474 4466 474"),
    "3": (38000, 33, "8903 4460 474 4466 474 4468 472 2240 474 2241 474 2239 474 2239 475 2243 471 2241 473 2242 472 2241 473 2241 473 2239 475 4467 473 2241 473 4465 475 4467 472"),
    "4": (38000, 33, "8903 4461 499 2217 497 2216 498 4442 498 2215 473 2243 471 2243 471 2241 473 2243 471 2242 472 2269 446 2241 472 2240 474 2241 474 2241 473 4468 472 4467 473"),
    "5": (38000, 33, "8900 4461 473 4467 474 2242 472 4468 472 2242 473 2241 473 2241 473 2243 498 2216 498 2219 469 2242 472 2241 473 2242 472 4468 498 4442 498 2215 499 4441 499"),
    "6": (38000, 33, "8902 4461 473 2241 473 4467 474 4494 445 2242 473 2242 471 2241 473 2243 472 2241 473 2241 473 2242 472 2242 473 2241 473 2241 474 4466 473 2239 475 4467 473"),
    "7": (38000, 33, "8903 4462 472 4466 474 4468 472 4468 472 2242 472 2245 469 2243 471 2240 474 2242 472 2268 446 2242 472 2243 471 2243 471 4468 472 2243 471 2242 473 4466 474"),
    "8": (38000, 33, "8901 4464 470 2241 473 2241 473 2241 473 4466 474 2240 474 2241 473 2241 473 2241 473 2243 472 2243 472 2241 472 2241 473 2242 472 2242 472 2242 472 4468 472"),
    "9": (38000, 33, "8901 4461 575 2166 548 2138 576 2139 576 2165 548 2140 575 2138 576 4366 574 2139 575 2140 574 2139 575 2137 577 2139 575 2139 575 2139 575 4366 574 4365 575"),
    "0": (38000, 33, "8903 4463 471 2241 474 2243 471 2241 473 2241 473 2241 474 2241 474 2241 473 2241 473 2240 474 2240 474 2240 475 2243 471 2241 473 2241 474 2242 472 2240 474"),
    "Vol_up": (38000, 33, "8446 4251 501 1627 504 567 504 1626 505 565 505 566 504 1628 504 567 503 1626 506 567 504 1628 504 567 503 1627 505 1627 505 567 503 1628 503 567 503 567 504 1628 503 566 505 1627 505 568 502 566 504 567 504 567 504 1629 503 565 506 1627 505 566 504 1630 502 1628 503 1628 504 1626 579"),
    "Vol_down": (38000, 33, "8524 4173 577 1553 579 489 582 1551 580 490 581 489 582 1551 580 489 582 1551 580 490 580 1551 581 491 580 1551 581 1550 581 491 580 1551 581 489 582 1551 580 1551 580 490 581 1551 580 491 580 489 582 515 555 491 580 489 582 492 579 1551 581 490 581 1551 581 1550 582 1551 580 1551 580"),
    "Mute": (38000, 33, "8446 4251 501 1627 504 567 504 1626 505 565 505 566 504 1628 504 567 503 1626 506 567 504 1628 504 567 503 1627 505 1627 505 567 503 1628 503 1627 504 567 504 1627 504 567 504 1627 504 567 504 567 504 567 504 1628 503 566 505 1627 504 567 504 1627 504 1627 504 1627 504 1627 504"),
    "Play_pause": (38000, 33, "8902 4462 473 4467 474 4467 473 2242 473 4468 472 4468 472 2242 473 2243 471 2241 473 2242 472 2240 474 2242 472 2240 474 2244 470 2241 473 4467 473 2241 473"),
    "Ffwd": (38000, 33, "8902 4461 473 4467 474 2240 474 4465 475 4468 472 4467 473 2241 474 2239 475 2241 473 2239 475 2240 474 2241 473 2242 472 2241 473 4467 473 2242 472 2241 474"),
    "Rev": (38000, 33, "8904 4463 471 2243 472 4468 472 4468 472 4470 470 4467 473 2242 473 2242 472 2240 474 2241 473 2241 474 2241 473 2243 471 4467 473 2242 472 2242 473 2242 472"),
    "Stop": (38000, 33, "8902 4463 471 2241 473 2240 474 4466 474 4467 473 4467 473 2240 474 2240 474 2240 474 2241 473 2241 473 2241 473 2240 474 4466 474 4467 473 2240 474 2242 472"),
    "Rec": (38000, 33, "8900 4459 475 4466 474 2240 474 2239 475 2239 475 4463 477 4466 474 2241 473 2239 476 2238 475 2238 476 2239 476 2239 475 2242 472 2240 474 4466 474 4465 475"),
    "Last": (38000, 33, "8907 4461 472 4465 475 4468 473 2240 474 2243 471 4466 474 2240 475 2241 473 2241 473 2240 474 2241 473 2240 475 2241 473 2240 474 2242 472 4468 472 4468 472"),
    "Favorites": (38000, 33, "8904 4465 573 4366 574 2139 575 4366 574 2139 576 4365 574 2142 572 2140 574 2139 575 2140 574 2138 576 2139 575 2139 575 2140 574 4366 574 2143 571 4366 574"),
    "Input": (38000, 33, "8903 4460 474 2241 473 4466 474 2241 473 4466 474 4466 474 2240 474 2241 473 2241 473 2240 474 2241 473 2240 475 2241 473 4467 473 2241 473 4466 474 2241 473"),
}


def find_flipper_port() -> Optional[str]:
    """Find the Flipper Zero serial port."""
    patterns = [
        '/dev/tty.usbmodemflip_*',
        '/dev/tty.usbmodem*',
        '/dev/cu.usbmodemflip_*',
        '/dev/cu.usbmodem*',
        '/dev/ttyACM*',
        '/dev/ttyUSB*',
    ]

    for pattern in patterns:
        ports = glob.glob(pattern)
        for port in ports:
            if 'flip' in port.lower() or 'usbmodem' in port.lower() or 'ACM' in port:
                logger.info(f"Found Flipper Zero at: {port}")
                return port

    return None


class FlipperZero:
    """Class to communicate with Flipper Zero over serial."""

    def __init__(self, port: Optional[str] = None, baudrate: int = 230400, timeout: int = 5):
        self.port = port or find_flipper_port()
        if not self.port:
            raise RuntimeError("Could not find Flipper Zero. Is it connected via USB?")

        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None

    def connect(self) -> bool:
        """Open serial connection to Flipper Zero."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            time.sleep(0.5)
            self._flush()

            # Exit any open apps first
            self._send_command("input send back short")
            time.sleep(0.2)
            self._send_command("input send back short")
            time.sleep(0.2)

            logger.info(f"Connected to Flipper Zero on {self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Flipper Zero: {e}")
            return False

    def disconnect(self) -> None:
        """Close serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info("Disconnected from Flipper Zero")

    def _flush(self) -> None:
        """Flush serial buffers."""
        if self.serial:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

    def _send_command(self, command: str) -> str:
        """Send a command to Flipper Zero CLI and return response."""
        if not self.serial or not self.serial.is_open:
            raise RuntimeError("Not connected to Flipper Zero")

        cmd = f"{command}\r\n"
        self.serial.write(cmd.encode())
        self.serial.flush()

        time.sleep(0.3)
        response = ""
        while self.serial.in_waiting:
            response += self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
            time.sleep(0.1)

        return response

    def send_ir_raw(self, frequency: int, duty_cycle: int, raw_data: str) -> bool:
        """Send raw IR signal."""
        cmd = f"ir tx RAW F:{frequency} DC:{duty_cycle} {raw_data}"
        logger.info(f"Sending raw IR: F:{frequency} DC:{duty_cycle}")

        response = self._send_command(cmd)
        logger.debug(f"Response: {response}")

        if "error" in response.lower() or "wrong" in response.lower():
            logger.error(f"IR command failed: {response}")
            return False

        return True

    def send_ir(self, command_name: str) -> bool:
        """Send an IR command by name."""
        if command_name not in IR_SIGNALS:
            logger.error(f"Unknown IR command: {command_name}")
            logger.info(f"Available commands: {', '.join(sorted(IR_SIGNALS.keys()))}")
            return False

        freq, duty, data = IR_SIGNALS[command_name]
        logger.info(f"Sending IR command: {command_name}")
        return self.send_ir_raw(freq, duty, data)


def send_ir_command(command_name: str, port: Optional[str] = None) -> bool:
    """Convenience function to send a single IR command."""
    flipper = FlipperZero(port=port)

    try:
        if not flipper.connect():
            return False

        result = flipper.send_ir(command_name)
        return result

    finally:
        flipper.disconnect()


def tune_channel(channel_number: int, port: Optional[str] = None) -> bool:
    """Tune to a specific channel by sending digit commands."""
    flipper = FlipperZero(port=port)

    try:
        if not flipper.connect():
            return False

        channel_str = str(int(channel_number))

        for digit in channel_str:
            logger.info(f"Sending digit: {digit}")

            if not flipper.send_ir(digit):
                logger.error(f"Failed to send digit {digit}")
                return False

            time.sleep(0.5)  # Delay between digits

        logger.info(f"Successfully tuned to channel {channel_number}")
        return True

    finally:
        flipper.disconnect()


def get_available_commands() -> list:
    """Return list of available IR command names."""
    return sorted(IR_SIGNALS.keys())

