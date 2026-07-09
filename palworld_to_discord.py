import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = os.getenv(
    "FEED_URL",
    "https://store.steampowered.com/feeds/news/app/1623730/?cc=CA&l=english"
)

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

STATE_FILE = ".state/palworld_last_seen_any_post.txt"

ONLY_PATCH_NOTES = os.getenv("ONLY_PATCH_NOTES", "true").lower() == "true"
SEND_ON_FIRST_RUN = os.getenv("SEND_ON_FIRST_RUN", "true").lower() == "true"

PATCH_KEYWORDS = [
    "patch",
    "patch notice",
    "hotfix",
    "bug fix",
    "bug fixes",
    "balance adjustment",
    "balance adjustments",
    "v0.",
    "v1.",
    "v2.",
]


def fetch_feed(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 Palworld Discord RSS Checker"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def get_child_text(item, tag):
    child = item.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def is_patch_note(title, description):
    if not ONLY_PATCH_NOTES:
        return True

    combined = f"{title} {description}".lower()

    if any(keyword in combined for keyword in PATCH_KEYWORDS):
        return True

    if re.search(r"\bv?\d+\.\d+(\.\d+)?\b", combined):
        return True

    return False


def load_last_seen():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return file.read().strip() or None


def save_last_seen(guid):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        file.write(guid)


def send_to_discord(title, link, description):
    description = clean_text(description)

    if len(description) > 1000:
        description = description[:997] + "..."

    payload = {
        "username": "Palworld Updates",
        "content": "📢 **New Palworld Steam update posted!**",
        "embeds": [
            {
                "title": title[:256],
                "url": link,
                "description": description or "Click to read the full Steam post.",
                "footer": {
                    "text": "Steam News • Palworld"
                }
            }
        ]
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord webhook failed with status {response.status}")


def main():
    feed_data = fetch_feed(FEED_URL)
    root = ET.fromstring(feed_data)

    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Could not find RSS channel.")

    items = channel.findall("item")
    if not items:
        print("No feed items found.")
        return

    parsed_items = []

    for item in items:
        title = clean_text(get_child_text(item, "title"))
        link = get_child_text(item, "link")
        guid = get_child_text(item, "guid") or link or title
        description = get_child_text(item, "description")

        parsed_items.append(
            {
                "title": title,
                "link": link,
                "guid": guid,
                "description": description,
            }
        )

    newest_any_guid = parsed_items[0]["guid"]
    last_seen = load_last_seen()

    if last_seen is None:
        if SEND_ON_FIRST_RUN:
            new_items = parsed_items
        else:
            new_items = []
    else:
        new_items = []

        for item in parsed_items:
            if item["guid"] == last_seen:
                break
            new_items.append(item)

    posted_count = 0

    for item in reversed(new_items[:10]):
        if is_patch_note(item["title"], item["description"]):
            print(f"Posting: {item['title']}")
            send_to_discord(item["title"], item["link"], item["description"])
            posted_count += 1
        else:
            print(f"Skipping non-patch item: {item['title']}")

    save_last_seen(newest_any_guid)

    print(f"Done. Posted {posted_count} item(s).")


if __name__ == "__main__":
    main()
