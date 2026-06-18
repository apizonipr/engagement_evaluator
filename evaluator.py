# engagement_evaluator
import streamlit as st
import re
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dateutil import parser as date_parser
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="YouTube Engagement Analyzer", layout="wide")

st.title("YouTube Engagement Analyzer")


@st.cache_data(show_spinner=False)
def extract_video_id(url: str) -> str | None:
    """Extract the YouTube video id from a URL."""
    parsed = urlparse(url)
    if parsed.netloc in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        return parse_qs(parsed.query).get("v", [None])[0]
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip("/")
    return None


def get_video_data(api_key: str, video_id: str):
    """Fetch video metadata from the YouTube Data API."""
    youtube = build("youtube", "v3", developerKey=api_key)
    request = youtube.videos().list(
        part="snippet,statistics",
        id=video_id,
    )
    response = request.execute()
    return response


def parse_video_stats(response: dict):
    """Parse useful statistics from a YouTube API response."""
    if not response.get("items"):
        return None
    item = response["items"][0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    return {
        "title": snippet.get("title", "Unknown title"),
        "channel_title": snippet.get("channelTitle", "Unknown channel"),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": int(stats.get("viewCount", 0) or 0),
        "like_count": int(stats.get("likeCount", 0) or 0),
        "comment_count": int(stats.get("commentCount", 0) or 0),
    }


def compute_engagement_metrics(stats: dict):
    """Compute engagement metrics and suggestions."""
    views = stats["view_count"]
    likes = stats["like_count"]
    comments = stats["comment_count"]

    like_rate = (likes / views * 100) if views else 0.0
    comment_rate = (comments / views * 100) if views else 0.0
    engagement_score = like_rate + comment_rate

    suggestions = []
    if like_rate < 2.0:
        suggestions.append("Consider adding a clear call-to-action asking viewers to like the video.")
    else:
        suggestions.append("Good like rate! Keep reinforcing your calls-to-action.")

    if comment_rate < 0.5:
        suggestions.append("Ask open-ended questions in the video or description to boost comments.")
    else:
        suggestions.append("Healthy comment rate! Keep engaging with your audience.")

    if views > 0 and (likes + comments) / views < 0.03:
        suggestions.append("Overall engagement is below 3%. Try improving hooks and content pacing.")
    else:
        suggestions.append("Overall engagement looks solid. Analyze top-performing moments to replicate success.")

    return {
        "like_rate": round(like_rate, 2),
        "comment_rate": round(comment_rate, 2),
        "engagement_score": round(engagement_score, 2),
        "suggestions": suggestions,
    }


def sanitize_api_key(value: str) -> str:
    """Return a non-empty, stripped API key or raise ValueError."""
    key = (value or "").strip()
    if not key:
        raise ValueError("API key is required.")
    # Avoid writing the raw key into internal state or logs.
    return key


with st.sidebar:
    st.header("Configuration")
    api_key_input = st.text_input(
        "YouTube Data API Key",
        type="password",
        placeholder="Paste your API key here",
        help="Your API key is used only for this request and is never logged or displayed.",
    )
    st.info("We intentionally avoid logging or storing your API key.")

st.header("Analyze a video")
video_url = st.text_input("YouTube video URL", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Analyze"):
    if not video_url.strip():
        st.error("Please provide a YouTube video URL.")
        st.stop()

    try:
        api_key = sanitize_api_key(api_key_input)
    except ValueError:
        st.error("Please provide a valid YouTube Data API key.")
        st.stop()

    video_id = extract_video_id(video_url)
    if not video_id:
        st.error("The URL does not appear to be a valid YouTube video link.")
        st.stop()

    with st.spinner("Fetching video data..."):
        try:
            response = get_video_data(api_key, video_id)
        except HttpError as e:
            # Leak-safe handling: only expose the status code; never the response body.
            status_code = e.resp.status if e.resp else "unknown"
            if status_code == 400:
                st.error("Invalid request. Please check the video URL and try again.")
            elif status_code == 403:
                st.error("Access denied. Verify your API key permissions and quota.")
            elif status_code == 404:
                st.error("Video not found. It may be private or removed.")
            else:
                st.error(f"A problem occurred while contacting YouTube (status {status_code}). Please try again later.")
            st.stop()
        except Exception:
            # Generic message without exposing the raw exception object or traceback.
            st.error("An unexpected error occurred while fetching video data. Please try again later.")
            st.stop()

    stats = parse_video_stats(response)
    if not stats:
        st.error("No video data was found for the provided URL.")
        st.stop()

    metrics = compute_engagement_metrics(stats)

    st.subheader(stats["title"])
    st.write(f"**Channel:** {stats['channel_title']}")
    try:
        published = date_parser.parse(stats["published_at"]).strftime("%Y-%m-%d %H:%M")
    except Exception:
        published = stats["published_at"]
    st.write(f"**Published at:** {published}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Views", f"{stats['view_count']:,}")
    col2.metric("Likes", f"{stats['like_count']:,}")
    col3.metric("Comments", f"{stats['comment_count']:,}")
    col4.metric("Engagement Score", f"{metrics['engagement_score']}%")

    st.divider()
    st.write(f"**Like Rate:** {metrics['like_rate']}%")
    st.write(f"**Comment Rate:** {metrics['comment_rate']}%")

    st.subheader("Suggestions")
    for suggestion in metrics["suggestions"]:
        st.write(f"- {suggestion}")
