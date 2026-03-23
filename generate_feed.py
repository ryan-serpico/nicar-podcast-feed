#!/usr/bin/env python3
"""Generate a podcast RSS feed from NICAR 2026 conference session audio."""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

TIPSHEETS_AUDIO_URL = "https://ire-nicar-conference-schedules.s3.us-east-2.amazonaws.com/nicar-2026/nicar-2026-tipsheets-audio.json"
SCHEDULE_URL = "https://ire-nicar-conference-schedules.s3.us-east-2.amazonaws.com/nicar-2026/nicar-2026-schedule.json"

# Update this after enabling GitHub Pages
FEED_BASE_URL = os.environ.get(
    "FEED_BASE_URL", "https://ryan-serpico.github.io/nicar-podcast-feed"
)
FEED_URL = f"{FEED_BASE_URL}/feed.xml"

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS = "http://www.w3.org/2005/Atom"

# Register namespace prefixes so output uses itunes/content/atom instead of ns0/ns1/ns2
ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("content", CONTENT_NS)
ET.register_namespace("atom", ATOM_NS)


class HTMLTextExtractor(HTMLParser):
    """Strip HTML tags, keeping just the text content."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def strip_html(html_str: str) -> str:
    extractor = HTMLTextExtractor()
    extractor.feed(html_str)
    return extractor.get_text()


def fetch_json(url: str):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())


def get_mp3_size(url: str) -> int:
    """HEAD request to get Content-Length. Returns 0 on failure."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(resp.headers.get("Content-Length", 0))
    except Exception:
        return 0


def build_schedule_lookup(schedule_data: dict) -> dict:
    """Build a lookup of (title, start_time) -> session+speakers for the schedule data."""
    speakers_by_id = {s["id"]: s for s in schedule_data.get("speakers", [])}
    lookup = {}
    for session in schedule_data.get("sessions", []):
        key = (session["session_title"].strip(), session["start_time"])
        resolved_speakers = []
        for sid in session.get("speakers", []):
            if sid in speakers_by_id:
                resolved_speakers.append(speakers_by_id[sid])
        lookup[key] = {
            "description": session.get("description", ""),
            "session_type": session.get("session_type", ""),
            "skill_level": session.get("skill_level", ""),
            "tracks": session.get("tracks", []),
            "room": session.get("room", ""),
            "speakers": resolved_speakers,
        }
    return lookup


def build_show_notes(audio_session: dict, schedule_info: dict | None) -> str:
    """Build HTML show notes for an episode."""
    parts = []

    # Description from schedule
    if schedule_info and schedule_info["description"]:
        desc_text = strip_html(schedule_info["description"])
        if desc_text:
            parts.append(f"<p>{escape(desc_text)}</p>")

    # Metadata
    if schedule_info:
        meta_items = []
        if schedule_info["session_type"]:
            meta_items.append(f"<strong>Type:</strong> {escape(schedule_info['session_type'])}")
        if schedule_info["skill_level"]:
            meta_items.append(f"<strong>Level:</strong> {escape(schedule_info['skill_level'])}")
        if schedule_info["tracks"]:
            meta_items.append(
                f"<strong>Tracks:</strong> {escape(', '.join(schedule_info['tracks']))}"
            )
        if schedule_info["room"]:
            meta_items.append(f"<strong>Room:</strong> {escape(schedule_info['room'])}")
        if meta_items:
            parts.append("<p>" + " | ".join(meta_items) + "</p>")

    # Speakers
    speakers_from_audio = audio_session.get("speakers", [])
    schedule_speakers = schedule_info["speakers"] if schedule_info else []

    if schedule_speakers:
        parts.append("<h3>Speakers</h3><ul>")
        for sp in schedule_speakers:
            name = f"{sp['first_name']} {sp['last_name']}"
            line = f"<strong>{escape(name)}</strong>"
            if sp.get("affiliation"):
                line += f", {escape(sp['affiliation'])}"
            if sp.get("bio"):
                line += f" — {escape(sp['bio'])}"
            parts.append(f"<li>{line}</li>")
        parts.append("</ul>")
    elif speakers_from_audio:
        parts.append("<h3>Speakers</h3><ul>")
        for sp_str in speakers_from_audio:
            parts.append(f"<li>{escape(sp_str)}</li>")
        parts.append("</ul>")

    # Tipsheets / links
    tipsheets = audio_session.get("tipsheets", [])
    if tipsheets:
        parts.append("<h3>Resources</h3><ul>")
        for ts in tipsheets:
            url = ts.get("url", "")
            label = ts.get("label", "Link")
            parts.append(f'<li><a href="{escape(url)}">{escape(label)}</a></li>')
        parts.append("</ul>")

    return "\n".join(parts)


def make_plain_description(audio_session: dict, schedule_info: dict | None) -> str:
    """Build a plain-text description for the <description> tag."""
    parts = []
    if schedule_info and schedule_info["description"]:
        desc_text = strip_html(schedule_info["description"])
        if desc_text:
            parts.append(desc_text)

    speakers = audio_session.get("speakers", [])
    if speakers:
        parts.append("Speakers: " + "; ".join(speakers))

    tipsheets = audio_session.get("tipsheets", [])
    if tipsheets:
        for ts in tipsheets:
            parts.append(f"{ts.get('label', 'Link')}: {ts.get('url', '')}")

    return "\n\n".join(parts)


def generate_feed():
    print("Fetching data...")
    audio_data = fetch_json(TIPSHEETS_AUDIO_URL)
    schedule_data = fetch_json(SCHEDULE_URL)

    print("Building schedule lookup...")
    schedule_lookup = build_schedule_lookup(schedule_data)

    # Collect all sessions with audio, flattened across days
    episodes = []
    for day in audio_data:
        day_label = day["label"]
        for session in day["sessions"]:
            if not session.get("recording_link"):
                continue
            session["_day_label"] = day_label
            episodes.append(session)

    # Sort newest first; within the same timeslot, sort alphabetically by title
    # for a stable, predictable order
    episodes.sort(key=lambda s: (s["start_time"], s["title"]), reverse=True)

    # Stagger pubDate by 1 minute for concurrent sessions so podcast apps
    # display them in a consistent order
    for i, ep in enumerate(episodes):
        dt = datetime.fromisoformat(ep["start_time"].replace("Z", "+00:00"))
        # Find how many episodes before this one (in our list) share the same start_time
        offset = 0
        for j in range(i - 1, -1, -1):
            if episodes[j]["start_time"] == ep["start_time"]:
                offset += 1
            else:
                break
        ep["_pub_date"] = dt - timedelta(minutes=offset)

    print(f"Found {len(episodes)} episodes with audio")

    # Get MP3 file sizes
    print("Fetching MP3 file sizes (HEAD requests)...")
    mp3_sizes = {}
    for i, ep in enumerate(episodes):
        url = ep["recording_link"]
        mp3_sizes[url] = get_mp3_size(url)
        if (i + 1) % 10 == 0:
            print(f"  ...{i + 1}/{len(episodes)}")

    # Build RSS
    rss = Element("rss", {"version": "2.0"})
    channel = SubElement(rss, "channel")

    # Channel metadata
    SubElement(channel, "title").text = "NICAR 2026 Conference Sessions"
    SubElement(channel, "link").text = FEED_BASE_URL
    SubElement(channel, "description").text = (
        "Audio recordings from the NICAR 2026 data journalism conference, "
        "held March 5-8, 2026 in Indianapolis. Produced by Investigative "
        "Reporters and Editors (IRE)."
    )
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )

    # Atom self-link (recommended for podcast feeds)
    SubElement(channel, f"{{{ATOM_NS}}}link", {
        "href": FEED_URL,
        "rel": "self",
        "type": "application/rss+xml",
    })

    # iTunes metadata
    SubElement(channel, f"{{{ITUNES_NS}}}author").text = "IRE & NICAR"
    SubElement(channel, f"{{{ITUNES_NS}}}summary").text = (
        "Audio recordings from the NICAR 2026 data journalism conference."
    )
    owner = SubElement(channel, f"{{{ITUNES_NS}}}owner")
    SubElement(owner, f"{{{ITUNES_NS}}}name").text = "IRE & NICAR"
    SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = "false"
    cat = SubElement(channel, f"{{{ITUNES_NS}}}category")
    cat.set("text", "News")
    SubElement(channel, f"{{{ITUNES_NS}}}type").text = "serial"

    # Channel image
    image = SubElement(channel, f"{{{ITUNES_NS}}}image")
    image.set("href", f"{FEED_BASE_URL}/cover.png")

    # Episodes
    for i, ep in enumerate(episodes, 1):
        title = ep["title"]
        start_time = ep["start_time"]
        mp3_url = ep["recording_link"]
        speakers = ep.get("speakers", [])

        # Look up schedule info
        key = (title.strip(), start_time)
        schedule_info = schedule_lookup.get(key)

        if not schedule_info:
            # Fallback: try matching title only
            for skey, sval in schedule_lookup.items():
                if skey[0] == title.strip():
                    schedule_info = sval
                    break

        # Use staggered pub date for consistent ordering
        pub_dt = ep["_pub_date"]

        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "pubDate").text = format_datetime(pub_dt)
        SubElement(item, "guid", {"isPermaLink": "false"}).text = mp3_url

        # Enclosure
        size = mp3_sizes.get(mp3_url, 0)
        SubElement(item, "enclosure", {
            "url": mp3_url,
            "length": str(size),
            "type": "audio/mpeg",
        })

        # Descriptions
        plain_desc = make_plain_description(ep, schedule_info)
        SubElement(item, "description").text = plain_desc

        html_notes = build_show_notes(ep, schedule_info)
        content_el = SubElement(item, f"{{{CONTENT_NS}}}encoded")
        content_el.text = html_notes

        # iTunes fields
        if speakers:
            SubElement(item, f"{{{ITUNES_NS}}}author").text = "; ".join(speakers)
        SubElement(item, f"{{{ITUNES_NS}}}episode").text = str(i)
        SubElement(item, f"{{{ITUNES_NS}}}episodeType").text = "full"

        # Subtitle from day label
        day_label = ep.get("_day_label", "")
        original_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        time_str = original_dt.strftime("%-I:%M %p ET")
        SubElement(item, f"{{{ITUNES_NS}}}subtitle").text = (
            f"{day_label}, {time_str}"
        )

    # Write feed
    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "feed.xml"

    tree = ElementTree(rss)
    indent(tree, space="  ")

    with open(output_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode" if False else "UTF-8", xml_declaration=False)

    print(f"Feed written to {output_path} with {len(episodes)} episodes")


if __name__ == "__main__":
    generate_feed()
