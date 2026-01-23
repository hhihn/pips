from typing import Optional


class TimeConverter:
    """Utility class for time format conversions."""

    @staticmethod
    def time_string_to_milliseconds(time_str: str) -> Optional[int]:
        """
        Convert time string (H:MM:SS,mmm or H:MM:SS.mmm) to milliseconds.

        Args:
            time_str (str): Time string in format H:MM:SS,mmm or H:MM:SS.mmm

        Returns:
            int: Time in milliseconds, or None if conversion fails
        """
        try:
            # Handle both comma and dot as decimal separator
            normalized_time = str(time_str).replace(",", ".")

            # Split by colons
            parts = normalized_time.split(":")
            hours = int(parts[0])
            minutes = int(parts[1])

            # Split seconds and milliseconds
            seconds_parts = parts[2].split(".")
            seconds = int(seconds_parts[0])

            # Handle milliseconds (pad or truncate to 3 digits)
            if len(seconds_parts) > 1:
                millis_str = seconds_parts[1].ljust(3, '0')[:3]  # Ensure exactly 3 digits
                milliseconds = int(millis_str)
            else:
                milliseconds = 0

            return (hours * 3600000) + (minutes * 60000) + (seconds * 1000) + milliseconds

        except (ValueError, IndexError):
            return None

    @staticmethod
    def milliseconds_to_time_string(ms: int, use_comma: bool = True) -> str:
        """
        Convert milliseconds back to time string format.

        Args:
            ms (int): Time in milliseconds
            use_comma (bool): Use comma as decimal separator (default: True)

        Returns:
            str: Time string in format H:MM:SS,mmm
        """
        hours = ms // 3600000
        remaining = ms % 3600000
        minutes = remaining // 60000
        remaining = remaining % 60000
        seconds = remaining // 1000
        milliseconds = remaining % 1000

        separator = "," if use_comma else "."
        return f"{hours}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"