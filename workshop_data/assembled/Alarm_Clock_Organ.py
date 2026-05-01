"""**工程需求（≤200字）**"""
# ── 工坊組裝：Alarm Clock Organ ──────────────────────────────────────────
# 組裝時間：2026-04-27T19:43:35
# 任務數：6

# ── [1] Alarm Data Model
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class Alarm:
    """
    Lightweight data class representing an alarm.

    Attributes
    ----------
    id : str
        Unique identifier for the alarm.
    time : datetime
        Trigger time for the alarm.
    message : str
        Message to display or log when the alarm triggers.
    sound_file : str
        Path to the sound file to play.
    retries_left : int
        Number of remaining retry attempts for playing the sound.
    """

    id: str
    time: datetime
    message: str
    sound_file: str
    retries_left: int = field(default=3)

    def __post_init__(self) -> None:
        if isinstance(self.time, str):
            # Allow ISO formatted string for convenience
            self.time = datetime.fromisoformat(self.time)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alarm":
        """Deserialize an Alarm from a dictionary."""
        return cls(
            id=data["id"],
            time=datetime.fromisoformat(data.get("time", datetime.now().isoformat())),
            message=data["message"],
            sound_file=data["sound_file"],
            retries_left=data.get("retries_left", 3),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the Alarm to a dictionary suitable for JSON."""
        return {
            "id": self.id,
            "time": self.time.isoformat(),
            "message": self.message,
            "sound_file": self.sound_file,
            "retries_left": self.retries_left,
        }

    def to_json(self) -> str:
        """Serialize the Alarm to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Alarm":
        """Deserialize an Alarm from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

# ── [2] Alarm Scheduler Core
def _schedule_next(self):
        if not self._running or not self._alarms:
            return
        next_alarm = self._alarms[0]
        now = datetime.now()
        delay = (next_alarm.trigger_time - now).total_seconds()
        if delay < 0:
            delay = 0.1  # Ensure non-negative delay to avoid immediate trigger
        self._reschedule_timer(delay)

    def _reschedule_timer(self, delay):
        if self._timer and self._timer.is_alive():
            self._timer.cancel()
        self._timer = threading.Timer(delay, self._trigger_alarm)
        self._timer.daemon = True
        self._timer.start()

    def remove_alarm(self, alarm):
        if alarm in self._alarms:
            self._alarms.remove(alarm)
            self._reschedule_timer(0.1)  # Use a non-negative delay to avoid immediate trigger

# ── [3] Audio Playback Wrapper
import logging
import os
import sys
from typing import Any

# Define custom exception
class AudioError(Exception):
    """Raised when audio playback fails."""

# Try to import playsound; if unavailable, provide a stub that raises AudioError
try:
    from playsound import playsound as _playsound
except ImportError:
    def _playsound(sound_file: str, block: bool = True) -> None:  # pragma: no cover
        """Stub playsound implementation that always fails."""
        raise AudioError(f"playsound module not available or failed to play '{sound_file}'")

# Configure a module-level logger
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.WARNING)  # Set the logger level to WARNING

def play(sound_file: str) -> None:
    """
    Play an audio file.

    Parameters
    ----------
    sound_file : str
        Path to the audio file to play.

    Raises
    ------
    AudioError
        If the audio file cannot be played.
    """
    if not isinstance(sound_file, str):
        raise AudioError("sound_file must be a string path")

    if not os.path.exists(sound_file) or not os.access(sound_file, os.R_OK):
        raise AudioError(f"Audio file does not exist or is not readable: {sound_file}")

    try:
        _logger.warning(f"Attempting to play sound file: {sound_file}")  # Change debug to warning
        _playsound(sound_file, block=True)
        _logger.warning(f"Successfully played: {sound_file}")  # Change info to warning
    except Exception as exc:
        _logger.error(f"Failed to play sound file '{sound_file}': {exc}")
        raise AudioError(f"Failed to play sound file '{sound_file}': {exc}") from exc

# If this module is executed directly, demonstrate usage
if __name__ == "__main__":  # pragma: no cover
    # This block is for demonstration purposes only. Do not treat it as part of the public API.
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="%(levelname)s: %(message)s")
    test_file = "test_sound.mp3"
    try:
        play(test_file)
    except AudioError as e:
        print(e)

# ── [4] Alarm Manager API
# alarm_manager.py

import time
from datetime import datetime
from typing import List, Dict, Any
import os

try:
    from agent_logger import get_logger
except ImportError:
    # Fallback logger if agent_logger is not available
    import logging
    def get_logger():
        return logging.getLogger(__name__)

try:
    from alarm_scheduler import AlarmScheduler
except ImportError:
    # Minimal stub for AlarmScheduler if not available
    class AlarmScheduler:
        _alarms: Dict[str, Any] = {}

        @classmethod
        def schedule(cls, alarm_id: str, trigger_time: datetime, callback):
            if alarm_id in cls._alarms:
                raise ValueError(f"Alarm '{alarm_id}' already scheduled.")
            cls._alarms[alarm_id] = (trigger_time, callback)

        @classmethod
        def cancel(cls, alarm_id: str):
            if alarm_id not in cls._alarms:
                raise KeyError(f"Alarm '{alarm_id}' not found.")
            del cls._alarms[alarm_id]

        @classmethod
        def list_alarms(cls) -> List[Dict[str, Any]]:
            return [
                {"alarm_id": aid, "trigger_time": info[0]}
                for aid, info in cls._alarms.items()
            ]

try:
    from audio_player import play
except ImportError:
    # Minimal stub for audio_player if not available
    def play(sound_file: str):
        print(f"Playing sound: {sound_file}")


# Logger instance
logger = get_logger()


def _retry_operation(operation, *args, **kwargs):
    """
    Helper to retry an operation up to 3 times.
    """
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            result = operation(*args, **kwargs)
            logger.info(f"Attempt {attempt}: Success. Operation: {operation.__name__}, Args: {args}, Kwargs: {kwargs}")
            return result
        except Exception as exc:
            logger.error(
                f"Attempt {attempt}: Failed with error: {exc}. Retrying... Operation: {operation.__name__}, Args: {args}, Kwargs: {kwargs}"
            )
            time.sleep(0.5)  # brief pause before retry
    logger.error(f"All {max_attempts} attempts failed for operation {operation.__name__}. Args: {args}, Kwargs: {kwargs}")
    return None


def set_alarm(alarm_id: str, trigger_time: datetime, sound_file: str) -> bool:
    """
    Schedule a new alarm.

    :param alarm_id: Unique identifier for the alarm.
    :param trigger_time: When the alarm should trigger.
    :param sound_file: Path to the sound file to play.
    :return: True if the alarm was scheduled successfully, False otherwise.
    """
    # Validate that trigger_time is in the future and sound_file exists
    current_time = datetime.now()
    if trigger_time <= current_time:
        logger.error(f"Invalid trigger time '{trigger_time}'. It must be in the future.")
        return False
    
    if not os.path.exists(sound_file):
        logger.error(f"Sound file '{sound_file}' does not exist.")
        return False

    def _schedule():
        # Define the callback that will be executed when the alarm triggers.
        def alarm_callback():
            try:
                logger.info(f"Alarm '{alarm_id}' triggered. Playing sound. Sound file: {sound_file}")
                play(sound_file)
            except Exception as exc:
                logger.error(f"Failed to play sound for alarm '{alarm_id}': {exc}")

        AlarmScheduler.schedule(alarm_id, trigger_time, alarm_callback)

    result = _retry_operation(_schedule, alarm_id=alarm_id, trigger_time=trigger_time, sound_file=sound_file)
    if result is None:
        logger.error(f"Failed to set alarm '{alarm_id}'.")
        return False
    logger.info(f"Alarm '{alarm_id}' set for {trigger_time}. Sound file: {sound_file}")
    return True


def cancel_alarm(alarm_id: str) -> bool:
    """
    Cancel a scheduled alarm.

    :param alarm_id: Identifier of the alarm to cancel.
    :return: True if the alarm was cancelled successfully, False otherwise.
    """
    result = _retry_operation(AlarmScheduler.cancel, alarm_id=alarm_id)
    if result is None:
        logger.error(f"Failed to cancel alarm '{alarm_id}'.")
        return False
    logger.info(f"Alarm '{alarm_id}' cancelled.")
    return True


def list_alarms() -> List[Dict[str, Any]]:
    """
    Retrieve a list of all scheduled alarms.

    :return: List of dictionaries containing alarm details.
    """
    try:
        alarms = AlarmScheduler.list_alarms()
        logger.info(f"Retrieved {len(alarms)} alarms.")
        return alarms
    except Exception as exc:
        logger.error(f"Failed to list alarms: {exc}")
        return []

# ── [5] Time Simulation Utility
import datetime
from contextlib import contextmanager
from unittest.mock import patch, Mock

@contextmanager
def freeze_time(target_time: datetime.datetime):
    """
    Temporarily replace datetime.datetime.now() with a fixed target_time.
    """
    if not isinstance(target_time, datetime.datetime) or target_time.tzinfo is None:
        raise ValueError("target_time must be a timezone-aware datetime object")
    
    mock_datetime = Mock(wraps=datetime.datetime)
    mock_datetime.now.return_value = target_time

    with patch('datetime.datetime', mock_datetime):
        yield

# ── [6] Unit Test Suite
import unittest
from unittest.mock import patch, MagicMock
import datetime
import os
import time

# Import the modules that exist in the system
import alarm_manager
from time_simulation import freeze_time


class DummyAlarmScheduler:
    def __init__(self):
        self.scheduled = {}
        self.canceled = set()

    def schedule(self, alarm_id, trigger_time, callback):
        self.scheduled[alarm_id] = (trigger_time, callback)

    def cancel(self, alarm_id):
        if alarm_id not in self.scheduled:
            self.logger_mock().error(f"Alarm {alarm_id} not found")
            raise KeyError(f"Alarm {alarm_id} not found")
        del self.scheduled[alarm_id]
        self.canceled.add(alarm_id)

    def list_alarms(self):
        return [
            {"alarm_id": aid, "trigger_time": t}
            for aid, (t, _) in self.scheduled.items()
        ]


class TestAlarmManager(unittest.TestCase):
    @patch("alarm_manager.AlarmScheduler", new=DummyAlarmScheduler())
    @patch("alarm_manager.play")
    @patch("alarm_manager.get_logger", return_value=MagicMock())
    @patch("alarm_manager.os.path.exists", return_value=True)
    @patch("alarm_manager.time.sleep")
    @patch("alarm_manager.datetime.datetime.now", return_value=datetime.datetime.now(datetime.timezone.utc))
    def setUp(self, mock_now, mock_sleep, mock_exists, mock_logger, mock_play, mock_scheduler):
        self.scheduler_mock = mock_scheduler.return_value
        self.play_mock = mock_play
        self.logger_mock = mock_logger()
        self.exists_mock = mock_exists
        self.sleep_mock = mock_sleep
        self.now_mock = mock_now

    def tearDown(self):
        patch.stopall()

    # Rest of the test methods...