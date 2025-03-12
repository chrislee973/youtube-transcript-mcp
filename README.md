# YouTube Transcript MCP

A MCP server for accessing and interacting with Youtube transcripts. Raw transcripts from Youtube are by default unpunctuated, so this handles automatic formatting and punctuating for better readability.

## Tools

The server offers the following tools:

#### Transcript Tools

- `get_full_transcript`

  - Retrieve the complete transcript from a YouTube video
  - Input:
    - `video_url` (string): The YouTube video URL or ID
  - Returns: Complete transcript text with timestamps

- `search_transcript`

  - Search for specific terms within a video transcript
  - Input:
    - `video_url` (string): The YouTube video URL or ID
    - `search_term` (string): The term to search for
  - Returns: Matching transcript segments with timestamps

- `extract_transcript_section`
  - Extract a specific section of a transcript by timestamp range
  - Input:
    - `video_url` (string): The YouTube video URL or ID
    - `start_time` (number): Starting timestamp in seconds
    - `end_time` (number): Ending timestamp in seconds
  - Returns: Transcript section within the specified time range

## Example Queries

When using with Claude or other AI assistants:

```
Extract all questions asked by the interviewer in this YouTube video: https://www.youtube.com/watch?v=VIDEO_ID
```

```
"Find all mentions of 'climate change' in this video and create a timeline of when these topics are discussed: https://www.youtube.com/watch?v=VIDEO_ID"
```

```
"Create a study guide with key concepts and timestamps from this lecture: https://www.youtube.com/watch?v=VIDEO_ID"
```

```
Return the transcript from 2:30 to 5:45 in this video: https://www.youtube.com/watch?v=VIDEO_ID
```

## Local Installation

### Prerequisites

- Python 3.11 or higher
- uv (Python package manager)

### Installing Dependencies

Install the required dependencies:

```bash
git clone https://github.com/yourusername/youtube-transcript-mcp.git
cd youtube-transcript-mcp
uv venv && uv pip install -r pyproject.toml
```

### Setting Up the MCP Server

The following command will install the MCP server and automatically add it to your Claude Desktop configuration:

```bash
uv run mcp install -e . server.py
```

**Important:** After installing the server, restart Claude Desktop for the changes to take effect.
