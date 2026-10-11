"""Choose cover art from collection timestamps, without using a song's release date."""
from datetime import datetime, timezone
import math


def latest_song_cover(songs: list[dict]) -> str:
    def added_time(song: dict) -> float:
        for key in ("addedAt", "added_at", "addedTime", "favTime", "fav_time", "collectTime", "collect_time"):
            value = song.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                timestamp = float(value)
                if math.isfinite(timestamp) and timestamp > 0:
                    return timestamp / 1000 if timestamp >= 1e12 else timestamp
            except (TypeError, ValueError):
                if isinstance(value, str):
                    try:
                        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
                    except ValueError:
                        pass
        return 0

    # sorted is stable: when the provider omits collection times, keep its order.
    for song in sorted((song for song in songs if isinstance(song, dict)), key=added_time, reverse=True):
        cover = song.get("coverUrl")
        if isinstance(cover, str) and cover.strip():
            cover = cover.strip()
            return f"https:{cover}" if cover.startswith("//") else cover
    return ""
