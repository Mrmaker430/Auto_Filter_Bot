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

def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int = 4) -> list[str]:
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

async def generate_movie_poster(details: dict, channel_username: str = "@cholochhitro") -> BytesIO | None:
    """
    Generates a 1280x720 landscape movie update poster matching the reference template.
    details dictionary expected keys:
        - title: str
        - rating: float/str
        - year: str/int
        - tag: str (e.g. '#MOVIE' or '#SERIES')
        - genres: str or list (e.g. 'Horror', 'Action' or ['Horror', 'Action'])
        - plot: str
        - poster_url: str
        - backdrop_url: str
    """
    try:
        width, height = 1280, 720
        canvas = Image.new("RGBA", (width, height), (10, 1, 2, 255))

        # 1. Fetch images asynchronously
        poster_url = details.get("poster_url")
        backdrop_url = details.get("backdrop_url") or poster_url
        logo_url = details.get("logo_url")

        poster_img, backdrop_img, logo_img = await asyncio.gather(
            _download_image(poster_url),
            _download_image(backdrop_url),
            _download_image(logo_url)
        )

        # 2. Draw Backdrop with Soft Red/Black Gradient (making background image more obvious)
        if backdrop_img:
            bg_aspect = backdrop_img.width / backdrop_img.height
            target_h = height
            target_w = int(height * bg_aspect)
            if target_w < width:
                target_w = width
                target_h = int(width / bg_aspect)

            resized_bg = backdrop_img.resize((target_w, target_h), Image.LANCZOS)
            bg_crop = resized_bg.crop((target_w - width, 0, target_w, height))
            canvas.paste(bg_crop, (0, 0))

        # Softer overlay gradient layer so backdrop is vibrant & obvious while keeping text legible
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_grad = ImageDraw.Draw(gradient)

        for x in range(width):
            if x < 400:
                alpha = 180
                r, g, b = 10, 1, 2
            elif x < 800:
                factor = (x - 400) / 400
                alpha = int(180 * (1 - factor ** 0.8))
                r, g, b = 10, 1, 2
            else:
                alpha = 0
                r, g, b = 0, 0, 0

            draw_grad.line([(x, 0), (x, height)], fill=(r, g, b, alpha))

        canvas = Image.alpha_composite(canvas, gradient)
        draw = ImageDraw.Draw(canvas)

        # 3. Draw Right Side Portrait Poster Card
        card_x, card_y = 815, 75
        card_w, card_h = 360, 560
        radius = 28
        border_width = 4
        border_color = (0, 245, 212, 255) # Cyan border

        if poster_img:
            # Resize poster to fit inside card
            p_resized = poster_img.resize((card_w, card_h), Image.LANCZOS)

            # Mask for rounded poster image
            mask = Image.new("L", (card_w, card_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle((0, 0, card_w, card_h), radius=radius, fill=255)

            canvas.paste(p_resized, (card_x, card_y), mask)

        # Draw outer rounded cyan border
        draw.rounded_rectangle(
            (card_x, card_y, card_x + card_w, card_y + card_h),
            radius=radius,
            outline=border_color,
            width=border_width
        )

        # 4. Left Side Text / Title Logo Elements
        title_text = str(details.get("title") or "Movie Update").upper().strip()
        start_x = 75

        # Font definitions
        font_rating_star = _get_font(SANS_BOLD_FONT_PATH, 24)
        font_rating_num = _get_font(SANS_BOLD_FONT_PATH, 24)
        font_badge_imdb = _get_font(SANS_BOLD_FONT_PATH, 16)
        font_badge_info = _get_font(SANS_BOLD_FONT_PATH, 16)
        font_badge_cat = _get_font(SANS_BOLD_FONT_PATH, 15)
        font_plot = _get_font(SANS_BOLD_FONT_PATH, 20) # Bold description font
        font_channel = _get_font(SANS_BOLD_FONT_PATH, 22)

        curr_y = 65

        if logo_img:
            # Fit title logo image in left region (max w: 680px, max h: 160px), left-aligned at start_x
            max_logo_w, max_logo_h = 680, 160
            logo_w, logo_h = logo_img.size
            ratio = min(max_logo_w / logo_w, max_logo_h / logo_h)
            new_logo_w = max(1, int(logo_w * ratio))
            new_logo_h = max(1, int(logo_h * ratio))

            logo_resized = logo_img.resize((new_logo_w, new_logo_h), Image.LANCZOS)
            logo_x = start_x
            logo_y = curr_y

            canvas.paste(logo_resized, (logo_x, logo_y), logo_resized)
            draw = ImageDraw.Draw(canvas)
            curr_y = logo_y + new_logo_h + 20
        else:
            # Fallback: draw title logo text using styled serief logo font left-aligned at start_x
            styled_title = Fonts.serief(title_text)

            title_lines = []
            words = styled_title.split()
            if len(words) > 1 and words[0].upper() in ("𝐓𝐇𝐄", "𝐀", "𝐀𝐍"):
                title_lines = [words[0], " ".join(words[1:])]
            elif len(words) > 2:
                mid = len(words) // 2
                title_lines = [" ".join(words[:mid]), " ".join(words[mid:])]
            else:
                title_lines = [styled_title]

            for idx, tline in enumerate(title_lines):
                if len(title_lines) > 1 and idx == 0 and len(tline) <= 4:
                    font_tl = _get_font(SERIF_BOLD_FONT_PATH, 52)
                else:
                    font_tl = _get_font(SERIF_BOLD_FONT_PATH, 72 if len(tline) <= 8 else 56)
                draw.text((start_x, curr_y), tline, font=font_tl, fill=(255, 255, 255, 255), anchor="lt")
                bbox = font_tl.getbbox(tline)
                line_h = bbox[3] - bbox[1]
                curr_y += max(line_h + 10, 65)

            curr_y += 10

        # 5. Rating & Badges Row
        row_y = curr_y

        # Star ★ 5.7
        rating_val = str(details.get("rating") or "N/A")
        draw.text((start_x, row_y), "★", font=font_rating_star, fill=(255, 204, 0, 255))
        draw.text((start_x + 24, row_y - 1), f" {rating_val}", font=font_rating_num, fill=(255, 255, 255, 255))

        # IMDb Pill Badge
        imdb_x = start_x + 105
        _draw_rounded_rectangle(draw, (imdb_x, row_y - 2, imdb_x + 65, row_y + 26), radius=12, fill=(245, 197, 24, 255))
        draw.text((imdb_x + 32, row_y + 12), "IMDb", font=font_badge_imdb, fill=(0, 0, 0, 255), anchor="mm")

        # Year Pill Badge
        year_str = str(details.get("year") or "").strip()
        if year_str:
            year_x = imdb_x + 80
            _draw_rounded_rectangle(draw, (year_x, row_y - 2, year_x + 65, row_y + 26), radius=12, outline=(255, 255, 255, 200), width=1)
            draw.text((year_x + 32, row_y + 12), year_str, font=font_badge_info, fill=(255, 255, 255, 255), anchor="mm")

        # Magenta Underline
        line_y = row_y + 38
        draw.line([(start_x, line_y), (start_x + 220, line_y)], fill=(235, 30, 110, 255), width=3)

        # 6. Category & Genre Badges Row
        badge_y = line_y + 22
        curr_badge_x = start_x

        # Tag Badge (MOVIE / SERIES)
        tag_val = str(details.get("tag") or "#MOVIE").replace("#", "").upper()
        tag_w = font_badge_cat.getbbox(tag_val)[2] + 28
        _draw_rounded_rectangle(draw, (curr_badge_x, badge_y, curr_badge_x + tag_w, badge_y + 32), radius=16, outline=(0, 245, 212, 255), width=2)
        draw.text((curr_badge_x + tag_w // 2, badge_y + 16), tag_val, font=font_badge_cat, fill=(0, 245, 212, 255), anchor="mm")
        curr_badge_x += tag_w + 14

        # Genres Badges
        genres_raw = details.get("genres") or []
        if isinstance(genres_raw, str):
            genres_list = [g.strip() for g in genres_raw.split(",") if g.strip() and g.strip() != "N/A"]
        else:
            genres_list = list(genres_raw)

        for g in genres_list[:3]: # Max 3 genre pills
            g_text = str(g).upper()
            g_w = font_badge_cat.getbbox(g_text)[2] + 28
            if curr_badge_x + g_w > 720:
                break
            _draw_rounded_rectangle(draw, (curr_badge_x, badge_y, curr_badge_x + g_w, badge_y + 32), radius=16, outline=(235, 30, 110, 255), width=2)
            draw.text((curr_badge_x + g_w // 2, badge_y + 16), g_text, font=font_badge_cat, fill=(235, 30, 110, 255), anchor="mm")
            curr_badge_x += g_w + 14

        # 7. Plot Overview Text (bold description text)
        plot_y = badge_y + 52
        plot_text = str(details.get("plot") or "").strip()
        if plot_text and plot_text != "N/A":
            wrapped_lines = _wrap_text(plot_text, font_plot, max_width=680, max_lines=4)
            for line in wrapped_lines:
                draw.text((start_x, plot_y), line, font=font_plot, fill=(255, 255, 255, 255))
                plot_y += 28

        # 8. Bottom Telegram Channel Pill Badge (placed under description, left-aligned at start_x in a straight line)
        ch_handle = channel_username
        if not ch_handle.startswith("@"):
            ch_handle = "@" + ch_handle.lstrip("@")

        handle_bbox = font_channel.getbbox(ch_handle)
        handle_w = handle_bbox[2] - handle_bbox[0]
        pill_w = max(240, handle_w + 70)
        pill_h = 52
        pill_x = start_x
        pill_y = max(plot_y + 20, 600)

        # Semi-transparent dark pill background matching reference image
        pill_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pill_draw = ImageDraw.Draw(pill_overlay)
        pill_draw.rounded_rectangle(
            (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
            radius=26,
            fill=(255, 255, 255, 35),
            outline=(255, 255, 255, 60),
            width=1
        )

        # Telegram Plane Icon inside circle
        icon_cx, icon_cy = pill_x + 26, pill_y + 26
        icon_r = 18
        pill_draw.ellipse((icon_cx - icon_r, icon_cy - icon_r, icon_cx + icon_r, icon_cy + icon_r), fill=(40, 168, 234, 255))

        # Simple paper plane icon drawing
        plane_pts = [
            (icon_cx - 9, icon_cy),
            (icon_cx + 10, icon_cy - 8),
            (icon_cx - 2, icon_cy + 9),
            (icon_cx + 1, icon_cy + 3)
        ]
        pill_draw.polygon(plane_pts, fill=(255, 255, 255, 255))

        canvas = Image.alpha_composite(canvas, pill_overlay)
        draw = ImageDraw.Draw(canvas)
        draw.text((pill_x + 55, pill_y + 26), ch_handle, font=font_channel, fill=(255, 255, 255, 255), anchor="lm")

        # Convert to BytesIO buffer
        output_buffer = BytesIO()
        canvas.convert("RGB").save(output_buffer, format="JPEG", quality=95)
        output_buffer.seek(0)
        return output_buffer

    except Exception as e:
        logger.exception(f"Failed to generate movie poster: {e}")
        return None
