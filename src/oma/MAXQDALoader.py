import pandas as pd
import logging

from OMAConfig import OMAConfig
# ---------------------------------------------------------------------
# Data loading and preprocessing
# ---------------------------------------------------------------------


class MaxQDALoader:
    def __init__(self, config: OMAConfig):
        self.config = config

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.config.input_path)

        required = {
            self.config.id_col,
            self.config.code_col,
            self.config.start_col,
            self.config.end_col,
        }

        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        df = df.copy()
        df["start_s"] = df[self.config.start_col].apply(self._parse_timestamp)
        df["end_s"] = df[self.config.end_col].apply(self._parse_timestamp)

        invalid = df[df["end_s"] <= df["start_s"]]
        if not invalid.empty:
            logging.warning(
                "Found %s rows where end <= start. They will be removed.",
                len(invalid),
            )
            df = df[df["end_s"] > df["start_s"]].copy()

        df[self.config.code_col] = df[self.config.code_col].astype(str).str.strip()
        df[self.config.id_col] = df[self.config.id_col].astype(str).str.strip()

        return df

    @staticmethod
    def _parse_timestamp(value: str) -> float:
        """
        Parses timestamps like:
        "0:00:31,6" -> 31.6 seconds
        "0:01:05,2" -> 65.2 seconds
        "1:02:03,4" -> 3723.4 seconds
        """
        if pd.isna(value):
            raise ValueError("Timestamp is missing")

        value = str(value).strip().replace(",", ".")
        parts = value.split(":")

        if len(parts) != 3:
            raise ValueError(f"Unexpected timestamp format: {value}")

        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])

        return hours * 3600 + minutes * 60 + seconds
