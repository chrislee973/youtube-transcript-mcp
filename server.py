from mcp.server.fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi
from typing import Optional, List, Dict
import re
import requests
from urllib.parse import urlparse, parse_qs

# Create a FastMCP server
mcp = FastMCP("youtube-transcript-mcp")


# Helper functions (reused from your existing implementation)
def parse_video_id(url: str):
    """Extract YouTube video ID from various URL formats"""
    """
    Parses Youtube url and returns the video id as a string.
    Example:
      input : https://www.youtube.com/watch?v=dQw4w9WgXcQ
      returns: dQw4w9WgXcQ
    Can handle urls in 3 formats:
      - https://www.youtube.com/watch?v=dQw4w9WgXcQ
      - https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=4557s
      - https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLbG2RcJqc3nr7Ey0WY4UwFYju3ZhRhhef&index=6
      - https://www.youtube.com/live/USTG6sQlB6s (live streams)
    """
    parsed = urlparse(url)
    if "live" in parsed.path:
        return parsed.path.split("/")[-1]
    if parsed.query:
        return parse_qs(parsed.query)["v"][0]
    return url  # Assume it's already a video ID if not a URL


def get_video_title(video_url: str) -> str:
    """
    Returns the title of a youtube video given the url
    """
    vid_id = parse_video_id(video_url)
    vid_url = f"https://www.youtube.com/watch?v={vid_id}"
    request_url = "https://www.youtube.com/oembed" + f"?format=json&url={vid_url}"
    try:
        response = requests.get(request_url)
        if response.status_code == 200:
            return response.json()["title"]
        return f"Video {vid_id}"
    except Exception:
        # If we can't get the title, return the video ID
        return f"Video {vid_id}"


class TranscriptDict:
    """
    A class to handle YouTube transcript operations.
    """

    def __init__(self, video_url: str):
        """
        Initialize with a YouTube video URL or ID.

        Args:
            video_url: YouTube video URL or ID
        """
        self.video_id = parse_video_id(video_url)
        self.video_url = video_url
        self.transcript_data = []
        self.has_transcript = True

        try:
            self.transcript_list = YouTubeTranscriptApi.list_transcripts(self.video_id)
            self.transcript = self.transcript_list.find_transcript(["en"])
            self.transcript_data = self.transcript.fetch()
        except Exception as _:
            self.has_transcript = False

    def get_query_usages(self, query: str) -> Dict[float, str]:
        """
        Find occurrences of a query in the transcript.

        Args:
            query: Search term to find

        Returns:
            Dictionary mapping timestamps to transcript sections
        """
        results = {}

        if not self.has_transcript:
            return results

        query = query.lower()

        for entry in self.transcript_data:
            if query in entry["text"].lower():
                results[entry["start"]] = entry["text"]

        return results

    def get_query_usages_with_context(
        self, query: str, context_window: int = 15
    ) -> List[Dict]:
        """
        Find occurrences of a query in the transcript with context before and after.
        Handles phrases that span across multiple transcript segments.

        Args:
            query: Search term to find
            context_window: Number of seconds of context to include before and after (default: 15)

        Returns:
            List of dictionaries containing match and context information
        """
        results = []

        if not self.has_transcript:
            return results

        query = query.lower()

        # First try the standard approach (exact matches within segments)
        matches = []
        for i, entry in enumerate(self.transcript_data):
            if query in entry["text"].lower():
                matches.append((i, entry))

        # If no matches found, try the sliding window approach for cross-segment matches
        if not matches:
            for i in range(len(self.transcript_data) - 1):
                # Create a window of 2 consecutive segments
                current_segment = self.transcript_data[i]["text"].lower()
                next_segment = self.transcript_data[i + 1]["text"].lower()

                # Join with a space to create a combined text
                combined_text = current_segment + " " + next_segment

                if query in combined_text:
                    # Both segments contribute to the match
                    matches.append((i, self.transcript_data[i]))
                    matches.append((i + 1, self.transcript_data[i + 1]))

        # For each match, collect context
        processed_indices = set()  # To avoid duplicate entries

        for match_index, match_entry in matches:
            # Skip if we've already processed this index (for cross-segment matches)
            if match_index in processed_indices:
                continue

            processed_indices.add(match_index)
            match_time = match_entry["start"]

            # Check if this is part of a cross-segment match
            is_cross_segment = False
            next_segment = None

            # Look for adjacent segments that might be part of the same match
            for other_index, other_entry in matches:
                if other_index == match_index + 1:
                    is_cross_segment = True
                    next_segment = other_entry
                    processed_indices.add(other_index)  # Mark as processed
                    break

            # Collect context before
            context_before = []
            before_time_limit = max(0, match_time - context_window)
            available_before = match_time - before_time_limit

            for entry in self.transcript_data:
                if before_time_limit <= entry["start"] < match_time:
                    context_before.append(entry)

            # Collect context after
            context_after = []
            after_time_limit = match_time + context_window

            # If this is a cross-segment match, adjust the after_time_limit
            if is_cross_segment and next_segment:
                after_time_limit = max(
                    after_time_limit, next_segment["start"] + context_window
                )

            # Find the last timestamp in the transcript to calculate available context after
            last_timestamp = (
                self.transcript_data[-1]["start"] if self.transcript_data else 0
            )
            available_after = min(after_time_limit, last_timestamp) - match_time

            for entry in self.transcript_data:
                if match_time < entry["start"] <= after_time_limit:
                    # Skip the next segment if it's part of the match (it will be included in the match)
                    if (
                        is_cross_segment
                        and next_segment
                        and entry["start"] == next_segment["start"]
                    ):
                        continue
                    context_after.append(entry)

            # Add to results
            results.append(
                {
                    "match": match_entry,
                    "is_cross_segment": is_cross_segment,
                    "next_segment": next_segment if is_cross_segment else None,
                    "context_before": {
                        "entries": context_before,
                        "available_seconds": available_before,
                    },
                    "context_after": {
                        "entries": context_after,
                        "available_seconds": available_after,
                    },
                }
            )

        return results

    def fetch_transcript(self, start_time: int, end_time: Optional[int] = 0) -> str:
        """
        Get a section of the transcript between start and end times.

        Args:
            start_time: Start time in seconds
            end_time: End time in seconds (0 for end of video)

        Returns:
            Formatted transcript section
        """
        if not self.has_transcript:
            title = get_video_title(self.video_url)
            return f"No transcript available for video: {title} (ID: {self.video_id})"

        section = ""
        for entry in self.transcript_data:
            if entry["start"] >= start_time and (
                end_time == 0 or entry["start"] <= end_time
            ):
                timestamp = format_timestamp(entry["start"])
                section += f"[{timestamp}] {entry['text']}\n\n"

        return section


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def generate_link(url: str, timestamp: int, title: Optional[str] = None) -> str:
    """Generate a clickable YouTube link with timestamp"""
    video_id = parse_video_id(url)
    timestamp_seconds = int(timestamp)

    # if title:
    #     return f"[{title}](https://www.youtube.com/watch?v={video_id}&t={timestamp_seconds}s)"
    # else:
    return f"https://www.youtube.com/watch?v={video_id}&t={timestamp_seconds}s"


# Tool versions of the resources
@mcp.tool()
def get_full_transcript(video_url: str) -> str:
    """
    Get the full transcript of a YouTube video.
    The transcript may be unpunctuated and unformatted when returned. When finally displaying the transcript text to the user, you must format it to be readable, adding punctuation and paragraphing where necessary, and remove unecessary filler words.

    Do not include any explanations, headers, or phrases like "Here is the transcript."

    Args:
        video_url: YouTube video URL or ID
    """
    try:
        video_id = parse_video_id(video_url)
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(["en"])
            transcript_data = transcript.fetch()

            # Format transcript with timestamps
            formatted_transcript = ""
            for entry in transcript_data:
                timestamp = format_timestamp(entry["start"])
                formatted_transcript += f"[{timestamp}] {entry['text']}\n\n"

            return formatted_transcript
        except Exception as e:
            # Handle case when no transcript exists
            title = get_video_title(video_url)

            return f"No transcript available for video: {title})"
    except Exception as e:
        title = get_video_title(video_url)
        return f"Error retrieving transcript: {str(e)}\nVideo: {title})"


@mcp.tool()
def get_video_information(video_url: str) -> str:
    """
    Get information about a YouTube video including title, ID, and available transcript languages.

    Args:
        video_url: YouTube video URL or ID
    """
    video_id = parse_video_id(video_url)
    title = get_video_title(video_url)

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Get available languages
        available_languages = []
        for transcript in transcript_list:
            available_languages.append(transcript.language)

        return f"Title: {title}\nVideo ID: {video_id}\nAvailable transcript languages: {', '.join(available_languages)}"
    except Exception as _:
        return f"Title: {title}\nNo transcripts available for this video."


# Tools
@mcp.tool()
def search_transcript(video_url: str, query: str, context_window: int = 15) -> str:
    """
    Search for occurrences of a term in a YouTube video transcript. Returns transcript sections containing the query with timestamps,
    including context before and after each match.

    When finally returning and displaying the search results to the user, you must also prepend the timestamped links to each result.
    These timestamped links should be in the format [[HH:MM:SS]](https://www.youtube.com/watch?v=VIDEO_ID&t=XXs) where XXs refers to the timestamp in seconds.


    Args:
        video_url: YouTube video URL or ID
        query: Search term to find in the transcript
        context_window: Number of seconds of context to include before and after (default: 15)
    """
    title = get_video_title(video_url)

    # Get transcript and search
    try:
        transcript_dict = TranscriptDict(video_url)

        if not transcript_dict.has_transcript:
            return f"No transcript available for video: {title}"

        results = transcript_dict.get_query_usages_with_context(
            query.lower(), context_window
        )

        if not results:
            return f"No matches found for '{query}' in video: {title}"

        # Format results
        formatted_results = (
            f"Found {len(results)} matches for '{query}' in video: {title}\n\n"
        )

        for i, result in enumerate(results):
            match_entry = result["match"]
            context_before = result["context_before"]["entries"]
            context_after = result["context_after"]["entries"]
            available_before = result["context_before"]["available_seconds"]
            available_after = result["context_after"]["available_seconds"]
            is_cross_segment = result["is_cross_segment"]
            next_segment = result["next_segment"]

            # Add divider between multiple results
            if i > 0:
                formatted_results += "\n" + "-" * 50 + "\n\n"

            # Format context before
            formatted_results += (
                f"=== CONTEXT BEFORE (AVAILABLE: {int(available_before)}s) ===\n"
            )
            if context_before:
                for entry in context_before:
                    timestamp = format_timestamp(entry["start"])
                    formatted_results += f"[{timestamp}] {entry['text']}\n"
            else:
                formatted_results += (
                    "No context available before this match (beginning of video)\n"
                )

            # Format match
            formatted_results += f"\n=== QUERY MATCH ===\n"
            timestamp = format_timestamp(match_entry["start"])
            formatted_link = generate_link(video_url, int(match_entry["start"]), title)

            if is_cross_segment and next_segment:
                # For cross-segment matches, show both segments
                next_timestamp = format_timestamp(next_segment["start"])
                formatted_results += f"[{timestamp}] {match_entry['text']}\n"
                formatted_results += f"[{next_timestamp}] {next_segment['text']}\n"
                formatted_results += f"(Link: {formatted_link})\n"
            else:
                # For single segment matches
                formatted_results += (
                    f"[{timestamp}] {match_entry['text']} (Link: {formatted_link})\n"
                )

            # Format context after
            formatted_results += (
                f"\n=== CONTEXT AFTER (AVAILABLE: {int(available_after)}s) ===\n"
            )
            if context_after:
                for entry in context_after:
                    timestamp = format_timestamp(entry["start"])
                    formatted_results += f"[{timestamp}] {entry['text']}\n"
            else:
                formatted_results += (
                    "No context available after this match (end of video)\n"
                )

        return formatted_results
    except Exception as e:
        return f"Error processing transcript: {str(e)}"


@mcp.tool()
def get_transcript_section(
    video_url: str, start_time: int, end_time: Optional[int] = 0
) -> str:
    """
    Get a specific section of a YouTube video transcript.
    The transcript may be unpunctuated and unformatted when returned. When finally displaying the transcript text to the user, you must format it to be readable, adding punctuation and paragraphing where necessary, and remove unnecessary filler words. Additionally, each paragraph should be preceded by a markdown-formatted timestamp link in the format [[HH:MM:SS]](https://www.youtube.com/watch?v=VIDEO_ID&t=XXs) where XXs refers to the timestamp in seconds. This allows users to click directly to that point in the video when reading the transcript.

    Do not include any explanations, headers, or phrases like "Here is the transcript."

    <example-tool-response>
    Transcript section from 00:00 to 05:00:

    Timestamped link: https://www.youtube.com/watch?v=LGDa3pO23Wc&t=0s

    [00:02] [Music]

    [00:25] so thank you for that introduction every

    [00:27] time I speak at another event I always

    [00:29] ask if there'll be lasers but somehow no

    [00:31] one else has Managed IT um now I've

    [00:34] asked was asked to come and say

    [00:36] insightful sensible clever things about

    [00:38] Ai and explain everything that's

    [00:41] happening in Ai and not talk too fast

    [00:44] and and only take half an hour um I'll

    [00:47] probably manage two of those things

    [00:48] possibly one but I'll see what I can do

    [00:51] I think a good place to start in

    [00:53] thinking where we are with AI today is

    [00:56] this quote from Bill Gates from 18

    [00:58] months ago saying that in his whole

    [01:00] career he'd seen two things that were

    [01:01] revolutionary the graphical user

    [01:03] interface and chat GPT which is a pretty

    [01:06] big statement
    </example-tool-response>

    <example-output-to-user>
    [[00:00:25]](https://www.youtube.com/watch?v=LGDa3pO23Wc&t=25s)
    Thank you for that introduction. Every time I speak at another event, I always ask if there'll be lasers, but somehow no one else has managed it.

    [[00:00:34]](https://www.youtube.com/watch?v=LGDa3pO23Wc&t=34s)
    Now I was asked to come and say insightful, sensible, clever things about AI and explain everything that's happening in AI, and not talk too fast, and only take half an hour. I'll probably manage two of those things, possibly one, but I'll see what I can do.

    [[00:00:51]](https://www.youtube.com/watch?v=LGDa3pO23Wc&t=51s)
    I think a good place to start in thinking where we are with AI today is this quote from Bill Gates from 18 months ago saying that in his whole career he'd seen two things that were revolutionary: the graphical user interface and ChatGPT, which is a pretty big statement.
    </example-output-to-user>

    Args:
        video_url: YouTube video URL or ID
        start_time: Start time in seconds
        end_time: End time in seconds (0 for end of video)
    """
    try:
        transcript_dict = TranscriptDict(video_url)
        section_text = transcript_dict.fetch_transcript(start_time, end_time)

        # If no transcript is available, the fetch_transcript method will return an error message
        if not transcript_dict.has_transcript:
            return section_text

        formatted_link = generate_link(video_url, start_time)
        return f"Transcript section from {format_timestamp(start_time)} to {format_timestamp(end_time or 999999)}:\n\nTimestamped link: {formatted_link}\n\n{section_text}\n\nWhen displaying this to the user, you must also include the timestamped links to the sections that contain the query so that the user can directly click on them in the client. Also, make sure to format the transcript text to be readable, adding punctuation and paragraphing where necessary, and remove unnecessary filler words."
    except Exception as e:
        title = get_video_title(video_url)
        return f"Error retrieving transcript section: {str(e)}\nVideo: {title}"


def run_server():
    """Run the MCP server"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
