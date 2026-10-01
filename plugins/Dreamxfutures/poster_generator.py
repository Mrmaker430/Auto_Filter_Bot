import os
import math
import logging
import asyncio
from io import BytesIO
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from info import UPDATE_CHNL_LNK
from plugins.Dreamxfutures.fotnt_string import Fonts

logger = logging.getLogger(__name__)

# Font paths (using system fonts available on Linux)
SERIF_BOLD_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SERIF_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SANS_BOLD_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

_session: aiohttp.ClientSession | None = None

async def _get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    return _session

async def _download_image(source) -> Image.Image | None:
    if not source:
        return None
    try:
        if isinstance(source, Image.Image):
            return source.convert("RGBA")
        if isinstance(source, BytesIO):
            source.seek(0)
            return Image.open(source).convert("RGBA")
        if isinstance(source, bytes):
            return Image.open(BytesIO(source)).convert("RGBA")
        if isinstance(source, str):
            if os.path.isfile(source):
                return Image.open(source).convert("RGBA")
            if source.startswith("http://") or source.startswith("https://"):
                session = await _get_session()
                async with session.get(source) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        return Image.open(BytesIO(data)).convert("RGBA")
                return None
            try:
                from dreamxbotz.Bot import dreamxbotz
                dl = await asyncio.wait_for(dreamxbotz.download_media(source, in_memory=True), timeout=5.0)
                if dl and isinstance(dl, BytesIO):
                    dl.seek(0)
                    return Image.open(dl).convert("RGBA")
            except Exception as e:
                logger.warning(f"Failed downloading telegram file_id thumbnail: {e}")
                return None
    except Exception as e:
        logger.error(f"Error loading image from source: {e}")
    return None

def _get_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def _draw_rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def _draw_telegram_watermark_badge(draw: ImageDraw.ImageDraw, x: int, y: int, username: str, font: ImageFont.ImageFont) -> int:
    wm_text = username if username.startswith("@") else f"@{username.lstrip('@')}"
    bbox = font.getbbox(wm_text)
    text_w = bbox[2] - bbox[0]

    padding_right = 36
    circle_radius = 36
    circle_margin = 15
    badge_w = circle_margin + (circle_radius * 2) + 18 + text_w + padding_right

    # Dark rounded pill background
    _draw_rounded_rectangle(draw, (x, y - 6, x + badge_w, y + 84), radius=45, fill=(35, 35, 40, 245))

    # Blue Telegram circle
    circle_cx = x + circle_margin + circle_radius
    circle_cy = y + 39
    draw.ellipse(
        (circle_cx - circle_radius, circle_cy - circle_radius, circle_cx + circle_radius, circle_cy + circle_radius),
        fill=(40, 168, 233, 255)
    )

    # Paper plane icon inside blue circle
    wing1 = [(circle_cx + 18, circle_cy - 18), (circle_cx - 18, circle_cy - 3), (circle_cx, circle_cy + 3)]
    wing2 = [(circle_cx + 18, circle_cy - 18), (circle_cx, circle_cy + 3), (circle_cx - 3, circle_cy + 18)]
    draw.polygon(wing1, fill=(255, 255, 255, 255))
    draw.polygon(wing2, fill=(215, 235, 250, 255))

    # Username text inside pill
    text_x = circle_cx + circle_radius + 18
    draw.text((text_x, y + 39), wm_text, font=font, fill=(255, 255, 255, 255), anchor="lm")

    return badge_w

def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int = 3) -> list[str]:
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = font.getbbox(test_line)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            if len(lines) == max_lines - 1:
                break

    if current_line and len(lines) < max_lines:
        lines.append(" ".join(current_line))

    # Truncate last line if there are remaining words
    if len(lines) == max_lines:
        last_line = lines[-1]
        while last_line and (font.getbbox(last_line + "...")[2] - font.getbbox(last_line + "...")[0]) > max_width:
            words_in_last = last_line.split()
            if len(words_in_last) <= 1:
                break
            last_line = " ".join(words_in_last[:-1])
        lines[-1] = last_line.rstrip(".,;!") + "..."

    return lines

OTT_BRAND_STYLES = {
    "NETFLIX": {"bg": (229, 9, 20, 255), "text": (255, 255, 255, 255), "label": "NETFLIX"},
    "AMAZON PRIME VIDEO": {"bg": (0, 168, 225, 255), "text": (255, 255, 255, 255), "label": "prime video"},
    "PRIME VIDEO": {"bg": (0, 168, 225, 255), "text": (255, 255, 255, 255), "label": "prime video"},
    "PRIME": {"bg": (0, 168, 225, 255), "text": (255, 255, 255, 255), "label": "prime video"},
    "DISNEY+ HOTSTAR": {"bg": (0, 20, 49, 255), "text": (255, 255, 255, 255), "label": "Disney+ hotstar", "border": (255, 215, 0, 255)},
    "HOTSTAR": {"bg": (0, 20, 49, 255), "text": (255, 255, 255, 255), "label": "Disney+ hotstar", "border": (255, 215, 0, 255)},
    "JIOHOTSTAR": {"bg": (0, 20, 49, 255), "text": (255, 255, 255, 255), "label": "JioHotstar", "border": (255, 215, 0, 255)},
    "SONYLIV": {"bg": (26, 16, 47, 255), "text": (255, 255, 255, 255), "label": "SonyLIV", "border": (255, 102, 0, 255)},
    "SONY": {"bg": (26, 16, 47, 255), "text": (255, 255, 255, 255), "label": "SonyLIV", "border": (255, 102, 0, 255)},
    "ZEE5": {"bg": (130, 36, 227, 255), "text": (255, 255, 255, 255), "label": "ZEE5"},
    "JIOCINEMA": {"bg": (225, 0, 120, 255), "text": (255, 255, 255, 255), "label": "JioCinema"},
    "AHA": {"bg": (255, 82, 0, 255), "text": (255, 255, 255, 255), "label": "aha"},
    "APPLE TV+": {"bg": (20, 20, 20, 255), "text": (255, 255, 255, 255), "label": "tv+", "border": (200, 200, 200, 255)},
    "APPLE": {"bg": (20, 20, 20, 255), "text": (255, 255, 255, 255), "label": "tv+", "border": (200, 200, 200, 255)},
    "HBO MAX": {"bg": (88, 34, 180, 255), "text": (255, 255, 255, 255), "label": "MAX"},
    "HBO": {"bg": (88, 34, 180, 255), "text": (255, 255, 255, 255), "label": "MAX"},
    "MAX": {"bg": (88, 34, 180, 255), "text": (255, 255, 255, 255), "label": "MAX"},
    "PARAMOUNT+": {"bg": (0, 100, 255, 255), "text": (255, 255, 255, 255), "label": "Paramount+"},
    "PARAMOUNT": {"bg": (0, 100, 255, 255), "text": (255, 255, 255, 255), "label": "Paramount+"},
    "HULU": {"bg": (28, 231, 131, 255), "text": (0, 0, 0, 255), "label": "hulu"},
    "PEACOCK": {"bg": (0, 0, 0, 255), "text": (255, 255, 255, 255), "label": "peacock", "border": (0, 200, 200, 255)},
    "HOICHOI": {"bg": (255, 204, 0, 255), "text": (200, 0, 0, 255), "label": "hoichoi"},
    "SUN NXT": {"bg": (237, 28, 36, 255), "text": (255, 255, 255, 255), "label": "SUN NXT"},
    "SUNNXT": {"bg": (237, 28, 36, 255), "text": (255, 255, 255, 255), "label": "SUN NXT"},
    "ALTBALAJI": {"bg": (153, 0, 0, 255), "text": (255, 255, 255, 255), "label": "ALTBalaji"},
    "EROS NOW": {"bg": (216, 0, 95, 255), "text": (255, 255, 255, 255), "label": "EROS NOW"},
    "VOOT": {"bg": (100, 40, 145, 255), "text": (255, 255, 255, 255), "label": "voot"},
    "CRUNCHYROLL": {"bg": (255, 102, 0, 255), "text": (255, 255, 255, 255), "label": "crunchyroll"},
    "VIKI": {"bg": (0, 174, 239, 255), "text": (255, 255, 255, 255), "label": "Viki"},
    "YOUTUBE PREMIUM": {"bg": (255, 0, 0, 255), "text": (255, 255, 255, 255), "label": "YouTube"}
}

def _extract_ott_list(details: dict) -> list[str]:
    raw = (
        details.get("ott_platform")
        or details.get("ott")
        or details.get("otts")
        or details.get("custom_otts")
        or details.get("ott_platforms")
    )
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        import re
        items = re.split(r"[|,\n]+", str(raw))

    result = []
    for item in items:
        clean = str(item).strip()
        if clean and clean.upper() not in ("N/A", "NONE"):
            result.append(clean)
    return result

def _draw_ott_badges(draw: ImageDraw.ImageDraw, ott_list: list[str], canvas_w: int, font: ImageFont.ImageFont):
    if not ott_list:
        return

    curr_x = canvas_w - 75  # Top right corner right margin
    y = 75                  # Top right corner y position
    badge_h = 96
    radius = 36

    for ott in ott_list:
        key = ott.upper().strip()
        style = OTT_BRAND_STYLES.get(key)
        if not style:
            # Try to match substring key in OTT_BRAND_STYLES
            for k, v in OTT_BRAND_STYLES.items():
                if k in key or key in k:
                    style = v
                    break

        if not style:
            style = {
                "bg": (25, 25, 30, 240),
                "text": (255, 255, 255, 255),
                "label": ott.upper()
            }

        label_text = style.get("label", ott)
        bg_col = style.get("bg", (25, 25, 30, 240))
        text_col = style.get("text", (255, 255, 255, 255))
        border_col = style.get("border")

        bbox = font.getbbox(label_text)
        text_w = bbox[2] - bbox[0]
        padding_h = 42
        badge_w = max(165, text_w + (padding_h * 2))

        box_x1 = curr_x - badge_w
        box_y1 = y
        box_x2 = curr_x
        box_y2 = y + badge_h

        if box_x1 < 750:
            break

        _draw_rounded_rectangle(
            draw,
            (box_x1, box_y1, box_x2, box_y2),
            radius=radius,
            fill=bg_col,
            outline=border_col,
            width=6 if border_col else 3
        )

        draw.text(
            (box_x1 + badge_w // 2, box_y1 + badge_h // 2),
            label_text,
            font=font,
            fill=text_col,
            anchor="mm"
        )

        curr_x = box_x1 - 30  # Move left for next OTT badge

def _format_runtime(runtime_val) -> str:
    if not runtime_val or str(runtime_val).upper() in ("N/A", "NONE"):
        return ""
    rt_str = str(runtime_val).lower().strip()
    if 'h' in rt_str or 'm' in rt_str and not 'min' in rt_str:
        return str(runtime_val).upper().strip()
    digits = "".join(c for c in rt_str if c.isdigit())
    if digits and digits.isdigit():
        mins = int(digits)
        if mins > 0:
            h = mins // 60
            m = mins % 60
            if h > 0 and m > 0:
                return f"{h}H {m}M"
            elif h > 0:
                return f"{h}H"
            else:
                return f"{m}M"
    return str(runtime_val).upper().strip()

async def generate_movie_poster(details: dict, channel_username: str = "@cholochhitro") -> BytesIO | None:
    """
    Generates a 4K resolution (3840x2160) landscape movie update poster.
    details dictionary expected keys:
        - title: str
        - localized_title: str
        - rating: float/str
        - year: str/int
        - tag: str (e.g. '#MOVIE' or '#SERIES')
        - genres: str or list (e.g. 'Horror', 'Action' or ['Horror', 'Action'])
        - plot: str
        - poster_url: str
        - backdrop_url: str
        - logo_url: str
        - runtime: str/int
        - ott_platform: str / list
    """
    try:
        width, height = 3840, 2160
        canvas = Image.new("RGBA", (width, height), (15, 15, 20, 255))

        # 1. Fetch images asynchronously (including primary_thumb fallback)
        primary_thumb = details.get("primary_thumb")
        poster_url = details.get("poster_url")
        backdrop_url = details.get("backdrop_url") or poster_url
        logo_url = details.get("logo_url")

        poster_img, backdrop_img, logo_img = await asyncio.gather(
            _download_image(poster_url or primary_thumb),
            _download_image(backdrop_url or poster_url or primary_thumb),
            _download_image(logo_url)
        )
        if not poster_img and primary_thumb:
            poster_img = await _download_image(primary_thumb)
        if not backdrop_img:
            backdrop_img = poster_img

        # 2. Draw Backdrop: render TMDB widescreen backdrop clean/unblurred
        is_same_as_poster = (
            poster_img and backdrop_img and
            (backdrop_url == poster_url or backdrop_img is poster_img or backdrop_img.size == poster_img.size)
        )

        if backdrop_img:
            if is_same_as_poster:
                # Apply Gaussian blur only if backdrop is identical to vertical mini poster
                blurred_bg = backdrop_img.filter(ImageFilter.GaussianBlur(50))
                bg_aspect = blurred_bg.width / blurred_bg.height
                target_h = height
                target_w = int(height * bg_aspect)
                if target_w < width:
                    target_w = width
                    target_h = int(width / bg_aspect)

                resized_bg = blurred_bg.resize((target_w, target_h), Image.LANCZOS)
                bg_crop = resized_bg.crop(((target_w - width) // 2, (target_h - height) // 2, (target_w + width) // 2, (target_h + height) // 2))
                canvas.paste(bg_crop, (0, 0))
            else:
                # Render widescreen TMDB backdrop image unblurred and clear
                bg_aspect = backdrop_img.width / backdrop_img.height
                target_h = height
                target_w = int(height * bg_aspect)
                if target_w < width:
                    target_w = width
                    target_h = int(width / bg_aspect)

                resized_bg = backdrop_img.resize((target_w, target_h), Image.LANCZOS)
                bg_crop = resized_bg.crop(((target_w - width) // 2, 0, (target_w + width) // 2, height))
                canvas.paste(bg_crop, (0, 0))

        # Soft overlay gradient so backdrop photo is clearly visible top-to-bottom and right-to-left
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_grad = ImageDraw.Draw(gradient)

        for y_i in range(height):
            if y_i < 600:
                alpha = int(25 * (y_i / 600))
            elif y_i < 1200:
                alpha = int(25 + 45 * ((y_i - 600) / 600))
            else:
                alpha = int(70 + 55 * ((y_i - 1200) / 960))
            draw_grad.line([(0, y_i), (width, y_i)], fill=(5, 5, 10, alpha))

        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # Fonts for 4K
        font_rating_star = _get_font(SANS_BOLD_FONT_PATH, 78)
        font_rating_num = _get_font(SANS_BOLD_FONT_PATH, 78)
        font_badge = _get_font(SANS_BOLD_FONT_PATH, 54)
        font_ott_badge = _get_font(SANS_BOLD_FONT_PATH, 48)
        font_plot = _get_font(SANS_BOLD_FONT_PATH, 63)  # Bold plot font

        # Draw OTT Badges at Top-Right Corner
        ott_list = _extract_ott_list(details)
        _draw_ott_badges(draw, ott_list, width, font_ott_badge)

        # 3. Bottom Left Portrait Poster Card
        card_x, card_y = 165, 990
        card_w, card_h = 690, 1035
        card_radius = 54

        if poster_img:
            p_resized = poster_img.resize((card_w, card_h), Image.LANCZOS)
            mask = Image.new("L", (card_w, card_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle((0, 0, card_w, card_h), radius=card_radius, fill=255)
            canvas.paste(p_resized, (card_x, card_y), mask)

        # Outer rounded white border
        draw.rounded_rectangle(
            (card_x, card_y, card_x + card_w, card_y + card_h),
            radius=card_radius,
            outline=(255, 255, 255, 240),
            width=9
        )

        # 4. Main Title Logo / Title Text Area (Right of Poster Card)
        start_right_x = 930
        curr_y = 1050

        title_text = str(details.get("title") or "").upper().strip()

        if logo_img:
            max_logo_w, max_logo_h = 1560, 390
            logo_w, logo_h = logo_img.size
            ratio = min(max_logo_w / logo_w, max_logo_h / logo_h)
            new_logo_w = max(1, int(logo_w * ratio))
            new_logo_h = max(1, int(logo_h * ratio))

            logo_resized = logo_img.resize((new_logo_w, new_logo_h), Image.LANCZOS)
            canvas.paste(logo_resized, (start_right_x, curr_y), logo_resized)
            draw = ImageDraw.Draw(canvas)
            curr_y += new_logo_h + 45
        else:
            styled_title = Fonts.serief(title_text) if title_text else "MOVIE UPDATE"
            font_title_main = _get_font(SERIF_BOLD_FONT_PATH, 162 if len(styled_title) <= 12 else 126)
            draw.text((start_right_x + 6, curr_y + 6), styled_title, font=font_title_main, fill=(0, 0, 0, 180), anchor="lt")
            draw.text((start_right_x, curr_y), styled_title, font=font_title_main, fill=(255, 255, 255, 255), anchor="lt")
            bbox = font_title_main.getbbox(styled_title)
            curr_y += (bbox[3] - bbox[1]) + 45

        # White Accent Underline
        line_w = 480
        draw.line([(start_right_x, curr_y), (start_right_x + line_w, curr_y)], fill=(255, 255, 255, 220), width=12)
        curr_y += 60

        # 5. Rating & Badges Row
        row_y = curr_y
        curr_badge_x = start_right_x

        # Star ★ Rating
        rating_val = str(details.get("rating") or "N/A")
        draw.text((curr_badge_x, row_y - 6), "★", font=font_rating_star, fill=(255, 204, 0, 255))
        draw.text((curr_badge_x + 84, row_y - 9), f" {rating_val}", font=font_rating_num, fill=(255, 255, 255, 255))
        curr_badge_x += 285

        # IMDb Badge
        _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 6, curr_badge_x + 210, row_y + 84), radius=36, fill=(245, 197, 24, 255))
        draw.text((curr_badge_x + 105, row_y + 39), "IMDb", font=font_badge, fill=(0, 0, 0, 255), anchor="mm")
        curr_badge_x += 240

        # Year Badge
        year_str = str(details.get("year") or "").strip()
        if year_str:
            _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 6, curr_badge_x + 210, row_y + 84), radius=36, fill=(225, 75, 50, 255))
            draw.text((curr_badge_x + 105, row_y + 39), year_str, font=font_badge, fill=(255, 255, 255, 255), anchor="mm")
            curr_badge_x += 240

        # Runtime Badge
        runtime_fmt = _format_runtime(details.get("runtime"))
        if runtime_fmt:
            rt_bbox = font_badge.getbbox(runtime_fmt)
            rt_w = (rt_bbox[2] - rt_bbox[0]) + 72
            _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 6, curr_badge_x + rt_w, row_y + 84), radius=36, fill=(45, 140, 180, 255))
            draw.text((curr_badge_x + rt_w // 2, row_y + 39), runtime_fmt, font=font_badge, fill=(255, 255, 255, 255), anchor="mm")
            curr_badge_x += rt_w + 30

        # Genre / Category Badges
        genres_raw = details.get("genres") or []
        if isinstance(genres_raw, str):
            genres_list = [g.strip() for g in genres_raw.split(",") if g.strip() and g.strip() != "N/A"]
        else:
            genres_list = list(genres_raw)

        badge_colors = [(200, 110, 30, 255), (105, 55, 175, 255), (60, 140, 90, 255)]
        for idx, g in enumerate(genres_list[:2]):
            g_text = str(g).upper()
            g_bbox = font_badge.getbbox(g_text)
            g_w = (g_bbox[2] - g_bbox[0]) + 78
            if curr_badge_x + g_w > width - 600:
                break
            bg_col = badge_colors[idx % len(badge_colors)]
            _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 6, curr_badge_x + g_w, row_y + 84), radius=36, fill=bg_col)
            draw.text((curr_badge_x + g_w // 2, row_y + 39), g_text, font=font_badge, fill=(255, 255, 255, 255), anchor="mm")
            curr_badge_x += g_w + 30

        # Watermark Pill Badge (Placed besides the genres)
        if channel_username:
            wm_badge_w = _draw_telegram_watermark_badge(draw, curr_badge_x, row_y, channel_username, font_badge)
            curr_badge_x += wm_badge_w + 30

        # 6. Plot Description Area (Bold text with shadow)
        plot_y = row_y + 126
        plot_text = str(details.get("plot") or "").strip()
        if plot_text and plot_text != "N/A":
            max_plot_w = width - start_right_x - 90
            wrapped_lines = _wrap_text(plot_text, font_plot, max_width=max_plot_w, max_lines=3)
            for line in wrapped_lines:
                draw.text((start_right_x + 3, plot_y + 3), line, font=font_plot, fill=(0, 0, 0, 200))
                draw.text((start_right_x, plot_y), line, font=font_plot, fill=(255, 255, 255, 255))
                plot_y += 84

        # Convert to BytesIO buffer
        output_buffer = BytesIO()
        canvas.convert("RGB").save(output_buffer, format="JPEG", quality=95)
        output_buffer.seek(0)
        return output_buffer

    except Exception as e:
        logger.exception(f"Failed to generate movie poster: {e}")
        return None
