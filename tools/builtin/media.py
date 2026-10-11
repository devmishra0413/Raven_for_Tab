"""
Built-in tools: Media control
"""

import subprocess
from pathlib import Path

from tools.sandbox import safe_path, WORKSPACE
from tools.router import ToolResult, termux_api_available


async def play_song(query: str) -> ToolResult:
    """
    Play a song from workspace or open YouTube search.
    
    Args:
        query: Song name or search query
    """
    if not query or not query.strip():
        return ToolResult(
            tool_name="play_song",
            success=False,
            output="",
            error="Song query cannot be empty"
        )
    
    query = query.strip()
    
    if not termux_api_available():
        return ToolResult(
            tool_name="play_song",
            success=False,
            output="",
            error="Termux:API not available"
        )
    
    try:
        # Search for song in workspace/music/
        music_dir = WORKSPACE / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        
        matches = []
        if music_dir.exists():
            for ext in ['.mp3', '.m4a', '.ogg', '.flac', '.wav']:
                for path in music_dir.rglob(f"*{ext}"):
                    if query.lower() in path.name.lower():
                        matches.append(path)
        
        if matches:
            # Play first match
            song_path = matches[0]
            subprocess.run(
                ["termux-media-player", "play", str(song_path)],
                check=True,
                capture_output=True,
                timeout=5
            )
            return ToolResult(
                tool_name="play_song",
                success=True,
                output=f"Playing: {song_path.name}",
                error=None
            )
        else:
            # No local file found - open YouTube search
            youtube_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            subprocess.run(
                ["termux-open", youtube_url],
                check=True,
                capture_output=True,
                timeout=5
            )
            return ToolResult(
                tool_name="play_song",
                success=True,
                output=f"No local file found. Opening YouTube search for: {query}",
                error=None
            )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_name="play_song",
            success=False,
            output="",
            error="Media command timed out"
        )
    except subprocess.CalledProcessError:
        return ToolResult(
            tool_name="play_song",
            success=False,
            output="",
            error="Failed to play media"
        )
    except Exception:
        return ToolResult(
            tool_name="play_song",
            success=False,
            output="",
            error="Media playback failed"
        )


async def pause_media() -> ToolResult:
    """Pause currently playing media."""
    if not termux_api_available():
        return ToolResult(
            tool_name="pause_media",
            success=False,
            output="",
            error="Termux:API not available"
        )
    
    try:
        subprocess.run(
            ["termux-media-player", "pause"],
            check=True,
            capture_output=True,
            timeout=5
        )
        return ToolResult(
            tool_name="pause_media",
            success=True,
            output="Media paused",
            error=None
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_name="pause_media",
            success=False,
            output="",
            error="Command timed out"
        )
    except subprocess.CalledProcessError:
        return ToolResult(
            tool_name="pause_media",
            success=False,
            output="",
            error="Failed to pause media"
        )
    except Exception:
        return ToolResult(
            tool_name="pause_media",
            success=False,
            output="",
            error="Pause command failed"
        )


async def next_track() -> ToolResult:
    """Skip to next track in media player."""
    if not termux_api_available():
        return ToolResult(
            tool_name="next_track",
            success=False,
            output="",
            error="Termux:API not available"
        )
    
    try:
        subprocess.run(
            ["termux-media-player", "next"],
            check=True,
            capture_output=True,
            timeout=5
        )
        return ToolResult(
            tool_name="next_track",
            success=True,
            output="Skipped to next track",
            error=None
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_name="next_track",
            success=False,
            output="",
            error="Command timed out"
        )
    except subprocess.CalledProcessError:
        return ToolResult(
            tool_name="next_track",
            success=False,
            output="",
            error="Failed to skip track"
        )
    except Exception:
        return ToolResult(
            tool_name="next_track",
            success=False,
            output="",
            error="Next track command failed"
        )


async def set_volume(level: int, stream: str = "music") -> ToolResult:
    """
    Set volume level for a stream.
    
    Args:
        level: Volume level 0-100
        stream: Audio stream (music, notification, ring)
    """
    if not (0 <= level <= 100):
        return ToolResult(
            tool_name="set_volume",
            success=False,
            output="",
            error="Volume level must be between 0 and 100"
        )
    
    if stream not in ["music", "notification", "ring"]:
        stream = "music"
    
    if not termux_api_available():
        return ToolResult(
            tool_name="set_volume",
            success=False,
            output="",
            error="Termux:API not available"
        )
    
    try:
        subprocess.run(
            ["termux-volume", stream, str(level)],
            check=True,
            capture_output=True,
            timeout=5
        )
        return ToolResult(
            tool_name="set_volume",
            success=True,
            output=f"Volume set to {level}% for {stream}",
            error=None
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_name="set_volume",
            success=False,
            output="",
            error="Volume command timed out"
        )
    except subprocess.CalledProcessError:
        return ToolResult(
            tool_name="set_volume",
            success=False,
            output="",
            error="Failed to set volume"
        )
    except Exception:
        return ToolResult(
            tool_name="set_volume",
            success=False,
            output="",
            error="Volume command failed"
        )
