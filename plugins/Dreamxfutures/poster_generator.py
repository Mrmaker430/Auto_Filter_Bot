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

async def _download_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        session = await _get_session()
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return Image.open(BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.error(f"Error downloading image from {url}: {e}")
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

    padding_right = 12
    circle_radius = 12
    circle_margin = 5
    badge_w = circle_margin + (circle_radius * 2) + 6 + text_w + padding_right

    # Dark rounded pill background
    _draw_rounded_rectangle(draw, (x, y - 2, x + badge_w, y + 28), radius=15, fill=(35, 35, 40, 245))

    # Blue Telegram circle
    circle_cx = x + circle_margin + circle_radius
    circle_cy = y + 13
    draw.ellipse(
        (circle_cx - circle_radius, circle_cy - circle_radius, circle_cx + circle_radius, circle_cy + circle_radius),
        fill=(40, 168, 233, 255)
    )

    # Paper plane icon inside blue circle
    wing1 = [(circle_cx + 6, circle_cy - 6), (circle_cx - 6, circle_cy - 1), (circle_cx, circle_cy + 1)]
    wing2 = [(circle_cx + 6, circle_cy - 6), (circle_cx, circle_cy + 1), (circle_cx - 1, circle_cy + 6)]
    draw.polygon(wing1, fill=(255, 255, 255, 255))
    draw.polygon(wing2, fill=(215, 235, 250, 255))

    # Username text inside pill
    text_x = circle_cx + circle_radius + 6
    draw.text((text_x, y + 13), wm_text, font=font, fill=(255, 255, 255, 255), anchor="lm")

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
    Generates a 1280x720 landscape movie update poster matching the reference template (IMG_20260910_142802_592.jpg).
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
    """
    try:
        width, height = 1280, 720
        canvas = Image.new("RGBA", (width, height), (15, 15, 20, 255))

        # 1. Fetch images asynchronously
        poster_url = details.get("poster_url")
        backdrop_url = details.get("backdrop_url") or poster_url
        logo_url = details.get("logo_url")

        poster_img, backdrop_img, logo_img = await asyncio.gather(
            _download_image(poster_url),
            _download_image(backdrop_url),
            _download_image(logo_url)
        )

        # 2. Draw Backdrop with custom gradient so background image is prominent and legible
        if backdrop_img:
            bg_aspect = backdrop_img.width / backdrop_img.height
            target_h = height
            target_w = int(height * bg_aspect)
            if target_w < width:
                target_w = width
                target_h = int(width / bg_aspect)

            resized_bg = backdrop_img.resize((target_w, target_h), Image.LANCZOS)
            bg_crop = resized_bg.crop(((target_w - width) // 2, 0, (target_w + width) // 2, height))
            canvas.paste(bg_crop, (0, 0))

        # Soft overlay gradient: Darker towards bottom where text/cards are placed, lighter top
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_grad = ImageDraw.Draw(gradient)

        for y in range(height):
            if y < 200:
                alpha = int(80 * (y / 200))
            elif y < 400:
                alpha = int(80 + 100 * ((y - 200) / 200))
            else:
                alpha = int(180 + 55 * ((y - 400) / 320))
            draw_grad.line([(0, y), (width, y)], fill=(5, 5, 10, min(235, alpha)))

        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # Fonts
        font_rating_star = _get_font(SANS_BOLD_FONT_PATH, 26)
        font_rating_num = _get_font(SANS_BOLD_FONT_PATH, 26)
        font_badge = _get_font(SANS_BOLD_FONT_PATH, 18)
        font_plot = _get_font(SANS_FONT_PATH, 21)

        # 3. Bottom Left Portrait Poster Card
        card_x, card_y = 55, 330
        card_w, card_h = 230, 345
        card_radius = 18

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
            width=3
        )

        # 4. Main Title Logo / Title Text Area (Right of Poster Card)
        start_right_x = 310
        curr_y = 350

        title_text = str(details.get("title") or "").upper().strip()

        if logo_img:
            max_logo_w, max_logo_h = 520, 130
            logo_w, logo_h = logo_img.size
            ratio = min(max_logo_w / logo_w, max_logo_h / logo_h)
            new_logo_w = max(1, int(logo_w * ratio))
            new_logo_h = max(1, int(logo_h * ratio))

            logo_resized = logo_img.resize((new_logo_w, new_logo_h), Image.LANCZOS)
            canvas.paste(logo_resized, (start_right_x, curr_y), logo_resized)
            draw = ImageDraw.Draw(canvas)
            curr_y += new_logo_h + 15
        else:
            styled_title = Fonts.serief(title_text) if title_text else "MOVIE UPDATE"
            font_title_main = _get_font(SERIF_BOLD_FONT_PATH, 54 if len(styled_title) <= 12 else 42)
            draw.text((start_right_x + 2, curr_y + 2), styled_title, font=font_title_main, fill=(0, 0, 0, 180), anchor="lt")
            draw.text((start_right_x, curr_y), styled_title, font=font_title_main, fill=(255, 255, 255, 255), anchor="lt")
            bbox = font_title_main.getbbox(styled_title)
            curr_y += (bbox[3] - bbox[1]) + 15

        # White Accent Underline
        line_w = 160
        draw.line([(start_right_x, curr_y), (start_right_x + line_w, curr_y)], fill=(255, 255, 255, 220), width=4)
        curr_y += 20

        # 5. Rating & Badges Row
        row_y = curr_y
        curr_badge_x = start_right_x

        # Star ★ Rating
        rating_val = str(details.get("rating") or "N/A")
        draw.text((curr_badge_x, row_y - 2), "★", font=font_rating_star, fill=(255, 204, 0, 255))
        draw.text((curr_badge_x + 28, row_y - 3), f" {rating_val}", font=font_rating_num, fill=(255, 255, 255, 255))
        curr_badge_x += 95

        # IMDb Badge
        _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 2, curr_badge_x + 70, row_y + 28), radius=12, fill=(245, 197, 24, 255))
        draw.text((curr_badge_x + 35, row_y + 13), "IMDb", font=font_badge, fill=(0, 0, 0, 255), anchor="mm")
        curr_badge_x += 80

        # Year Badge
        year_str = str(details.get("year") or "").strip()
        if year_str:
            _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 2, curr_badge_x + 70, row_y + 28), radius=12, fill=(225, 75, 50, 255))
            draw.text((curr_badge_x + 35, row_y + 13), year_str, font=font_badge, fill=(255, 255, 255, 255), anchor="mm")
            curr_badge_x += 80

        # Runtime Badge
        runtime_fmt = _format_runtime(details.get("runtime"))
        if runtime_fmt:
            rt_bbox = font_badge.getbbox(runtime_fmt)
            rt_w = (rt_bbox[2] - rt_bbox[0]) + 24
            _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 2, curr_badge_x + rt_w, row_y + 28), radius=12, fill=(45, 140, 180, 255))
            draw.text((curr_badge_x + rt_w // 2, row_y + 13), runtime_fmt, font=font_badge, fill=(255, 255, 255, 255), anchor="mm")
            curr_badge_x += rt_w + 10

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
            g_w = (g_bbox[2] - g_bbox[0]) + 26
            if curr_badge_x + g_w > width - 200:
                break
            bg_col = badge_colors[idx % len(badge_colors)]
            _draw_rounded_rectangle(draw, (curr_badge_x, row_y - 2, curr_badge_x + g_w, row_y + 28), radius=12, fill=bg_col)
            draw.text((curr_badge_x + g_w // 2, row_y + 13), g_text, font=font_badge, fill=(255, 255, 255, 255), anchor="mm")
            curr_badge_x += g_w + 10

        # Watermark Pill Badge (Placed besides the genres)
        if channel_username:
            wm_badge_w = _draw_telegram_watermark_badge(draw, curr_badge_x, row_y, channel_username, font_badge)
            curr_badge_x += wm_badge_w + 10

        # 6. Plot Description Area
        plot_y = row_y + 42
        plot_text = str(details.get("plot") or "").strip()
        if plot_text and plot_text != "N/A":
            max_plot_w = width - start_right_x - 30
            wrapped_lines = _wrap_text(plot_text, font_plot, max_width=max_plot_w, max_lines=3)
            for line in wrapped_lines:
                draw.text((start_right_x + 1, plot_y + 1), line, font=font_plot, fill=(0, 0, 0, 160))
                draw.text((start_right_x, plot_y), line, font=font_plot, fill=(230, 230, 230, 255))
                plot_y += 28

        # Convert to BytesIO buffer
        output_buffer = BytesIO()
        canvas.convert("RGB").save(output_buffer, format="JPEG", quality=95)
        output_buffer.seek(0)
        return output_buffer

    except Exception as e:
        logger.exception(f"Failed to generate movie poster: {e}")
        return None
