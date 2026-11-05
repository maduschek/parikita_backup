#!/usr/bin/env python3
import io
import json
import re
import html
import mimetypes
from pathlib import Path
from datetime import date, timezone
from urllib.parse import urlparse

import requests
from PIL import Image, ExifTags
# from fontTools.misc.plistlib import start_dict

# Read the token
with open("mytoken.txt", "r", encoding="utf-8") as f:
    TOKEN = f.readlines()[-1].strip()

BASE = "https://apiparikita.nemborn.com"

# get profile data 
USER_ID = 0000000
CHILD_ID = 0000000
INSTITUTION_ID = 000000

APP_VERSION = "3.2.1140"
LANGUAGE = "de"
BUNDLE_ID = "dk.assemble.bnet.pari"
USER_AGENT = "okhttp/4.9.0"

OUTDIR = Path("parikita_backup")
TAKE = 100


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str, max_len: int = 180) -> str:
    name = name.strip().replace("\x00", "")
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len] or "unnamed"


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p\s*>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


metadata = {
    "platform": "Android",
    "app": "PariKita",
    "v": APP_VERSION,
    "language": LANGUAGE,
    "bundleId": BUNDLE_ID,
    "token": TOKEN,
}

HEADERS = {
    "User-Agent": USER_AGENT,
    "Assemble-Metadata": json.dumps(metadata, separators=(",", ":")),
}


session = requests.Session()
session.headers.update(HEADERS)


def get_text(url: str) -> str:
    r = session.get(url, timeout=60)
    print(f"{r.status_code} {url}")
    r.raise_for_status()
    return r.content.decode("utf-8-sig", errors="replace")


def get_json(url: str):
    text = get_text(url).strip()
    if not text:
        return None
    return json.loads(text)


def save_json(data, path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(text: str, path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def download_binary(url: str, path: Path) -> bool:
    try:
        r = session.get(url, timeout=120, stream=True)
        print(f"{r.status_code} {url}")
        if r.status_code != 200:
            return False

        content_type = (r.headers.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            return False

        ensure_dir(path.parent)
        with path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Download failed: {url} -> {e}")
        return False


def paginated_mails(folder_id: int) -> list:
    items = []
    page = 1
    while True:
        url = f"{BASE}/mails?mailfolder={folder_id}&pagenumber={page}&pagesize=100"
        page_items = get_json(url)
        if not page_items or not isinstance(page_items, list):
            break
        items.extend(page_items)
        print(f"Fetched {len(page_items)} mails from folder {folder_id}, total {len(items)}")
        if len(page_items) < 100:
            break
        page += 1
    return items


def paginated_feed(user_id: int, take: int = 100) -> list:
    items = []
    skip = 0
    while True:
        url = f"{BASE}/users/{user_id}/feed?skip={skip}&take={take}"
        text = get_text(url).strip()

        if not text or text == "null":
            break

        page = json.loads(text)
        if not page:
            break
        if not isinstance(page, list):
            raise RuntimeError(f"Unexpected feed response type: {type(page)}")

        items.extend(page)
        print(f"Fetched {len(page)} feed items, total {len(items)}")

        if len(page) < take:
            break
        skip += take

    return items


def split_feed(feed: list) -> dict:
    posts = [x for x in feed if x.get("Type") == "News" and x.get("SubType") == "Post"]
    gallery = [x for x in feed if x.get("Type") == "MediaAlbum"]
    activities = [x for x in feed if x.get("Type") == "Activity"]
    mealplans = [x for x in feed if x.get("Type") == "MealPlan"]
    other = [
        x for x in feed
        if x not in posts and x not in gallery and x not in activities and x not in mealplans
    ]

    images = []
    attachments = []

    for item in gallery:
        for media in item.get("Media") or []:
            if media.get("Type") == "Image":
                images.append({
                    "album_date": item.get("PublishDate"),
                    "description": media.get("Description"),
                    "title": media.get("Title"),
                    "filename": media.get("Filename"),
                    "upload_date": media.get("UploadDate"),
                    "image_url": media.get("ImageUrl"),
                    "thumbnail_url": media.get("ThumbnailUrl"),
                })

    for item in posts:
        for att in item.get("Attachments") or []:
            attachments.append({
                "feed_item_id": item.get("FeedItemId"),
                "post_title": item.get("Title"),
                "attachment_id": att.get("Id"),
                "title": att.get("Title"),
                "file_name": att.get("FileName"),
                "publish_date": item.get("PublishDate"),
            })

    return {
        "posts": posts,
        "gallery": gallery,
        "activities": activities,
        "mealplans": mealplans,
        "other": other,
        "images": images,
        "attachments": attachments,
    }


def save_posts_as_text(posts: list, path: Path) -> None:
    chunks = []
    for i, post in enumerate(posts, 1):
        chunks.append(f"# {i}. {post.get('Title') or '(untitled)'}")
        chunks.append(f"FeedItemId: {post.get('FeedItemId')}")
        chunks.append(f"PublishDate: {post.get('PublishDate')}")
        chunks.append(f"NewsDate: {post.get('NewsDate')}")
        chunks.append("")
        teaser = html_to_text(post.get("Teaser"))
        content = html_to_text(post.get("Content"))
        if teaser:
            chunks.append("Teaser:")
            chunks.append(teaser)
            chunks.append("")
        if content:
            chunks.append("Content:")
            chunks.append(content)
            chunks.append("")
        atts = post.get("Attachments") or []
        if atts:
            chunks.append("Attachments:")
            for att in atts:
                chunks.append(f"- {att.get('FileName') or att.get('Title')} (Id={att.get('Id')})")
            chunks.append("")
        chunks.append("=" * 80)
        chunks.append("")
    save_text("\n".join(chunks), path)


def save_mails_as_text(mails: list, path: Path) -> None:
    chunks = []
    for i, mail in enumerate(mails, 1):
        chunks.append(f"# {i}. {mail.get('Subject') or '(no subject)'}")
        chunks.append(f"MailId: {mail.get('Id')}")
        chunks.append(f"From: {mail.get('From')}")
        chunks.append(f"Date: {mail.get('SendDate')}")
        chunks.append("")
        content = html_to_text(mail.get("Content"))
        if content:
            chunks.append(content)
            chunks.append("")
        atts = mail.get("Attachments") or []
        if atts:
            chunks.append("Attachments:")
            for att in atts:
                chunks.append(f"- {att.get('Filename')} (Id={att.get('Id')})")
            chunks.append("")
        chunks.append("=" * 80)
        chunks.append("")
    save_text("\n".join(chunks), path)


def file_extension_from_url_or_type(url: str, content_type: str | None = None) -> str:
    p = Path(urlparse(url).path)
    if p.suffix:
        return p.suffix
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext
    return ""


def download_images(images: list, outdir: Path) -> None:
    ensure_dir(outdir)
    for idx, img in enumerate(images, 1):
        url = img.get("image_url") or img.get("ImageUrl")
        if not url:
            continue

        # Use upload_date for subdirectory (YYYY-MM-DD)
        upload_date_raw = img.get("upload_date") or img.get("UploadDate")
        if upload_date_raw:
            # "2026-03-25T10:47:09" -> "2026-03-25"
            date_folder = upload_date_raw[:10]
        else:
            date_folder = "unknown_date"

        # Folder structure: outdir / YYYY-MM-DD / filename
        target_dir = outdir / date_folder
        ensure_dir(target_dir)

        # Filename from JSON or title or generic fallback
        title = img.get("filename") or img.get("FileName") or img.get("title") or img.get("Title") or f"image_{idx}"
        ext = Path(urlparse(url).path).suffix or Path(title).suffix or ".jpg"
        filename = sanitize_filename(Path(title).stem) + ext
        path = target_dir / filename

        if path.exists():
            continue

        description = img.get("description") or img.get("Description")
        img_title = img.get("title") or img.get("Title")

        try:
            r = session.get(url, timeout=120)
            print(f"{r.status_code} {url}")
            if r.status_code != 200:
                print(f"Could not download image: {url}")
                continue

            content_type = (r.headers.get("Content-Type") or "").lower()
            if "application/json" in content_type:
                print(f"Could not download image: {url}")
                continue

            saved = False
            if description or img_title:
                try:
                    image = Image.open(io.BytesIO(r.content))
                    exif = image.getexif()
                    if description:
                        exif[ExifTags.Base.ImageDescription] = str(description)
                        exif[ExifTags.Base.XPComment] = str(description).encode("utf-16le")
                        exif[ExifTags.Base.UserComment] = str(description)
                    if img_title:
                        exif[ExifTags.Base.XPTitle] = str(img_title).encode("utf-16le")
                        exif[ExifTags.Base.DocumentName] = str(img_title)

                    save_kwargs = {"exif": exif}
                    if image.format:
                        save_kwargs["format"] = image.format
                    if image.format == "JPEG":
                        save_kwargs["quality"] = "keep"

                    image.save(path, **save_kwargs)
                    saved = True
                except Exception as e:
                    print(f"Failed to write EXIF data for {path.name}: {e}")

            if not saved:
                path.write_bytes(r.content)
        except Exception as e:
            print(f"Download failed: {url} -> {e}")


def try_download_attachment(att: dict, outdir: Path) -> dict:
    """
    Attachment download URL is not fully confirmed from the source snippets,
    so this tries a few likely patterns and reports what worked.
    """
    att_id = att.get("attachment_id")
    if not att_id:
        return {**att, "downloaded": False, "download_url": None}

    raw_name = att.get("file_name") or att.get("title") or f"attachment_{att_id}"
    filename = sanitize_filename(raw_name)
    target = outdir / filename

    if target.exists():
        return {**att, "downloaded": True, "download_url": "already_exists", "saved_as": str(target)}

    candidates = [
        f"{BASE}/attachment/{att_id}",
        f"{BASE}/attachment?id={att_id}",
        f"{BASE}/mailattachments?id={att_id}",
    ]

    for url in candidates:
        if download_binary(url, target):
            return {**att, "downloaded": True, "download_url": url, "saved_as": str(target)}

    return {**att, "downloaded": False, "download_url": None, "saved_as": None}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic", ".heif", ".svg"
}


def download_bulletin_attachments(bulletin: list, outdir: Path) -> dict:
    """
    Downloads all attachments found across bulletin posts before saving bulletin_all.json.
    - Image attachments are saved into outdir/downloads/images/<YYYY-MM-DD>/<filename>
    - Non-image attachments are saved into outdir/downloads/attachments/<filename>
    - Skips existing files with a terminal message.
    - Outputs file-based status statements in the terminal.
    """
    images_dir = outdir / "downloads" / "images"
    attachments_dir = outdir / "downloads" / "attachments"
    ensure_dir(images_dir)
    ensure_dir(attachments_dir)

    results = []
    saved_count = 0
    skipped_count = 0
    failed_count = 0

    for post in bulletin:
        attachments = post.get("Attachments") or []
        if not attachments:
            continue

        date_raw = post.get("NewsDate") or post.get("PublishDate") or post.get("DateToSortBy") or ""
        date_folder = date_raw[:10] if date_raw and len(date_raw) >= 10 else "unknown_date"

        for att in attachments:
            att_id = att.get("Id") or att.get("id") or att.get("attachment_id")
            if not att_id:
                continue

            raw_name = att.get("FileName") or att.get("fileName") or att.get("Title") or att.get("title") or f"attachment_{att_id}"
            filename = sanitize_filename(raw_name)
            ext = Path(filename).suffix.lower()

            if ext in IMAGE_EXTENSIONS:
                target_dir = images_dir / date_folder
                target_path = target_dir / filename
                is_image = True
            else:
                target_dir = attachments_dir
                target_path = target_dir / filename
                is_image = False

            if target_path.exists():
                print(f"[SKIP] Existing file: {target_path}")
                skipped_count += 1
                results.append({
                    "attachment_id": att_id,
                    "filename": filename,
                    "target": str(target_path),
                    "status": "skipped_exists",
                    "is_image": is_image,
                })
                continue

            ensure_dir(target_dir)
            print(f"[DOWNLOADING] {filename} (ID: {att_id}) -> {target_path}")

            candidates = [
                f"{BASE}/attachment/{att_id}",
                f"{BASE}/attachment?id={att_id}",
                f"{BASE}/mailattachments?id={att_id}",
            ]

            downloaded = False
            for url in candidates:
                if download_binary(url, target_path):
                    downloaded = True
                    break

            if downloaded:
                print(f"[SAVED] {target_path}")
                saved_count += 1
                results.append({
                    "attachment_id": att_id,
                    "filename": filename,
                    "target": str(target_path),
                    "status": "saved",
                    "is_image": is_image,
                })
            else:
                print(f"[FAILED] Could not download {filename} (ID: {att_id}) to {target_path}")
                failed_count += 1
                results.append({
                    "attachment_id": att_id,
                    "filename": filename,
                    "target": str(target_path),
                    "status": "failed",
                    "is_image": is_image,
                })

    print(f"\nBulletin attachments processing finished: {saved_count} saved, {skipped_count} skipped, {failed_count} failed\n")
    return {
        "saved": saved_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "details": results,
    }


def get_all_bulletin_posts(user_id, child_id=None, take=100):
    all_items = []
    skip = 0

    while True:
        url = (
            f"{BASE}/users/{user_id}/bulletin"
            f"?skip={skip}&take={take}"
        )

        if child_id is not None:
            url += f"&limitToUser={child_id}"

        r = session.get(url, timeout=60)

        print(f"{r.status_code} {url}")
        r.raise_for_status()

        text = r.content.decode(
            "utf-8-sig",
            errors="replace"
        ).strip()

        if not text or text == "null":
            break

        data = json.loads(text)

        if not data:
            break

        print(f"  received {len(data)} items")

        all_items.extend(data)

        if len(data) < take:
            break

        skip += take

    return all_items


def main():
    ensure_dir(OUTDIR)
    ensure_dir(OUTDIR / "json")
    ensure_dir(OUTDIR / "downloads" / "images")
    ensure_dir(OUTDIR / "downloads" / "attachments")
    ensure_dir(OUTDIR / "text")

    # Core profile/bootstrap
    me = get_json(f"{BASE}/users/me")
    save_json(me, OUTDIR / "json" / "users_me.json")

    print(f"Name: {me['Name']} \n"
          f"Username: {me['Username']}\n"
          f"Email: {me['Email']}\n"
          f"MobilePhone: {me['MobilePhone']}\n"
          f"UserID: {me['Id']}")

    global USER_ID
    USER_ID = int(me["Id"])

    # Optional useful endpoints you already validated
    contactbook = get_json(f"{BASE}/ContactBook/GetLatestMessagesForProxyChildrenAndGroups")
    save_json(contactbook, OUTDIR / "json" / "contactbook_latest.json")

    vacationperiods = get_json(f"{BASE}/users/{USER_ID}/vacationperiods")
    save_json(vacationperiods, OUTDIR / "json" / "vacationperiods.json")

    # save gallery images in date subfolders and with original file names
    gallery_images = get_json(f"{BASE}/users/{USER_ID}/media?skip=0&take=10000")
    download_images(gallery_images, OUTDIR / "downloads" / "images")

    # save activities
    activities = get_json(f"{BASE}/users/{USER_ID}/activities?skip=0&take=10000")
    save_json(activities, OUTDIR / "json" / "activities.json")

    # save Calendar Entries
    start_date = "2020-01-01"
    end_date = date.today().isoformat()
    calendar_entries = get_json(f"{BASE}/calendar/calendaritems/{start_date}/{end_date}")
    save_json(calendar_entries, OUTDIR / "json" / "calendar_entries.json")

    # save messages
    chats = get_json(f"{BASE}/ContactBook/GetLatestMessagesForProxyChildrenAndGroups")
    for chat in chats:
        chat_id = chat.get("ChatId")
        if not chat_id:
            continue
        messages = get_json(f"{BASE}/ContactBook/GetContactBookByChatId?institutionId={INSTITUTION_ID}&chatid={chat_id}")
        save_json(messages, OUTDIR / "json" / f"messages_{chat_id}.json")

    # save diary entries
    diary_entries = get_json(f"{BASE}/users/{USER_ID}/diary?skip=0/take=10000")
    save_json(diary_entries, OUTDIR / "json" / "diary_entries.json")

    # save posts (mails)
    all_mails = []
    for folder_id in [1, 2, 3, 4, 5]:  # Inbox, Sent, Trash, Drafts, Archive
        folder_mails = paginated_mails(folder_id)
        save_json(folder_mails, OUTDIR / "json" / f"mails_folder_{folder_id}.json")
        all_mails.extend(folder_mails)
    save_mails_as_text(all_mails, OUTDIR / "text" / "mails_readable.txt")

    # Download mail attachments
    ensure_dir(OUTDIR / "downloads" / "mail_attachments")
    for mail in all_mails:
        for att in mail.get("Attachments") or []:
            att_info = {
                "attachment_id": att.get("Id"),
                "file_name": att.get("Filename"),
                "title": att.get("Filename")
            }
            try_download_attachment(att_info, OUTDIR / "downloads" / "mail_attachments")

    # save shared contacts
    shared_contacts = get_json(f"{BASE}/contact/{INSTITUTION_ID}")
    save_json(shared_contacts, OUTDIR / "json" / "shared_contacts.json")

    # save mealplans from calendar entries
    mealplans = []
    for entry in calendar_entries or []:
        for item in entry.get("CalendarItems") or []:
            if item.get("ItemType") == "MealPlan":
                mealplans.append(item)
    save_json(mealplans, OUTDIR / "json" / "mealplans.json")

    # save contact info (index card)
    contact_info = get_json(f"{BASE}/users/{USER_ID}/contactinfo")
    save_json(contact_info, OUTDIR / "json" / "contact_info.json")

    # save playdates
    try:
        playdates = get_json(f"{BASE}/users/{USER_ID}/playdate")
        save_json(playdates, OUTDIR / "json" / "playdates.json")
    except Exception as e:
        print(f"Error fetching playdates: {e}")

    # save check-in messages (daily message)
    try:
        daily_messages = get_json(f"{BASE}/users/{USER_ID}/dailymessage")
        save_json(daily_messages, OUTDIR / "json" / "daily_messages.json")
    except Exception as e:
        print(f"Error fetching daily messages: {e}")

    # save holiday bookings
    holidays = get_json(f"{BASE}/users/{USER_ID}/holidayperiods")
    save_json(holidays, OUTDIR / "json" / "holiday_periods.json")

    # save permissions
    permissions = get_json(f"{BASE}/users/{USER_ID}/AcceptedConditionsOfUse")
    save_json(permissions, OUTDIR / "json" / "permissions.json")

    # save portfolio
    try:
        portfolio = get_json(f"{BASE}/Portfolio/GetPublishedPortfolioBooks/{USER_ID}")
        save_json(portfolio, OUTDIR / "json" / "portfolio.json")
    except Exception as e:
        print(f"Error fetching portfolio: {e}")

    # save my contact info (profile)
    try:
        profile = get_json(f"{BASE}/users/{USER_ID}/profile")
        save_json(profile, OUTDIR / "json" / "profile.json")
    except Exception as e:
        print(f"Error fetching profile: {e}")

    # Feed
    feed = paginated_feed(USER_ID, TAKE)
    save_json(feed, OUTDIR / "json" / "feed_all.json")

    split = split_feed(feed)
    for key, value in split.items():
        save_json(value, OUTDIR / "json" / f"{key}.json")

    save_posts_as_text(split["posts"], OUTDIR / "text" / "posts_readable.txt")

    # Download gallery images
    download_images(split["images"], OUTDIR / "downloads" / "images")



    # TESTBED
    # "%s/users/%d/childreport
    '''for feed_item in range(2438409, 2440458):
        testCollection = get_json(f"{BASE}/users/{USER_ID}/initfeed?feedItemId={feed_item}")
        if testCollection["FeedItems"] is None:
            print(f"No feed items for {feed_item}")
        else:
            save_json(testCollection, OUTDIR / "json" / f"out_{feed_item}.json")'''

    # TODO:
    # - POSTS!!!!

    bulletin = get_all_bulletin_posts(
        USER_ID,
        child_id=CHILD_ID
    )

    # Save all attachments before dumping bulletin_all.json
    download_bulletin_attachments(bulletin, OUTDIR)

    save_json(bulletin, OUTDIR / "json" / "bulletin_all.json")
    with open(
            "parikita_backup/json/bulletin_all.json",
            "w",
            encoding="utf-8"
    ) as f:
        json.dump(
            bulletin,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Downloaded {len(bulletin)} bulletin items")



    # Try downloading attachments
    attachment_results = []
    for att in split["attachments"]:
        attachment_results.append(
            try_download_attachment(att, OUTDIR / "downloads" / "attachments")
        )
    save_json(attachment_results, OUTDIR / "json" / "attachments_download_report.json")

    # Attendance/checkin: raw save even if 204
    checkin_url = (
        f"{BASE}/users/{CHILD_ID}/nemtjekind/GetCheckInTimes"
        f"?institutionId={INSTITUTION_ID}"
        f"&startDate=2020-01-01"
        f"&endDate={date.today().isoformat()}"
        f"&includeWeekend=true"
    )
    r = session.get(checkin_url, timeout=60)
    print(f"{r.status_code} {checkin_url}")
    save_text(r.content.decode("utf-8-sig", errors="replace"), OUTDIR / "json" / "checkin_times_raw.json")

    print(f"\nBackup written to: {OUTDIR.resolve()}")


if __name__ == "__main__":
    main()
