import os
import io
import re
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from collections import OrderedDict

logger = logging.getLogger(__name__)

# LRU Cache for generated posters
_POSTER_CACHE: OrderedDict[str, bytes] = OrderedDict()
MAX_CACHE_SIZE = 50

# Font paths with fallbacks
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

REGULAR_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

def get_font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    paths = FONT_PATHS if bold else REGULAR_FONT_PATHS
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

async def fetch_image_bytes(url: str, timeout: int = 3) -> Optional[bytes]:
    if not url or not url.startswith("http"):
        return None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        logger.warning(f"Failed to download image from {url}: {e}")
    return None

def add_rounded_corners(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new('L', im.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), im.size], radius, fill=255)
    result = im.copy()
    result.putalpha(mask)
    return result

def draw_pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    bg_color: tuple,
    text: str,
    font: ImageFont.ImageFont,
    text_color: tuple = (255, 255, 255),
    padding: tuple = (16, 8),
    radius: int = 12
) -> int:
    """Draws a rounded pill badge with text and returns its total width."""
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x, y = xy
    px, py = padding
    pill_w = text_w + 2 * px
    pill_h = text_h + 2 * py

    draw.rounded_rectangle([(x, y), (x + pill_w, y + pill_h)], radius=radius, fill=bg_color)

    # Calculate text position (centered vertically/horizontally in pill)
    tx = x + px - bbox[0]
    ty = y + py - bbox[1]
    draw.text((tx, ty), text, font=font, fill=text_color)

    return pill_w

def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int = 3) -> List[str]:
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = font.getbbox(test_line)
        if (bbox[2] - bbox[0]) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                if len(lines) == max_lines - 1:
                    break
            else:
                lines.append(word)
                current_line = []
                break

    if current_line and len(lines) < max_lines:
        lines.append(" ".join(current_line))

    if len(lines) == max_lines and words:
        # Check if there were leftover words
        last_line = lines[-1]
        lines[-1] = last_line[:max(0, len(last_line) - 3)] + "..."

    return lines

async def generate_movie_poster(movie_doc: Dict[str, Any]) -> io.BytesIO:
    """
    Generates a 1080p landscape poster (1920x1080) for movie update posts and file covers.
    Matching style:
    - 1920x1080 landscape image canvas with backdrop background
    - Left portrait thumbnail with rounded corners
    - Title text, rating badge, year, genres, telegram tag
    - Plot/overview summary text at the bottom
    """
    cache_key = f"{movie_doc.get('_id')}_{movie_doc.get('year')}_{movie_doc.get('rating')}"
    if cache_key in _POSTER_CACHE:
        _POSTER_CACHE.move_to_end(cache_key)
        out = io.BytesIO(_POSTER_CACHE[cache_key])
        out.seek(0)
        return out

    # Determine image URLs
    backdrop_url = movie_doc.get("backdrop_url") or movie_doc.get("poster_url")
    poster_url = movie_doc.get("poster_url") or backdrop_url

    # Fetch images in parallel
    backdrop_task = asyncio.create_task(fetch_image_bytes(backdrop_url, timeout=4))
    poster_task = asyncio.create_task(fetch_image_bytes(poster_url, timeout=4))
    backdrop_bytes, poster_bytes = await asyncio.gather(backdrop_task, poster_task)

    # Base Canvas 1920x1080
    W, H = 1920, 1080
    canvas = Image.new("RGB", (W, H), (20, 20, 30))

    # Process Backdrop Background
    if backdrop_bytes:
        try:
            bg_img = Image.open(io.BytesIO(backdrop_bytes)).convert("RGB")
            # Aspect fill resize
            bg_ratio = bg_img.width / bg_img.height
            target_ratio = W / H
            if bg_ratio > target_ratio:
                new_h = H
                new_w = int(H * bg_ratio)
            else:
                new_w = W
                new_h = int(W / bg_ratio)
            bg_img = bg_img.resize((new_w, new_h), Image.LANCZOS)
            crop_x = (new_w - W) // 2
            crop_y = (new_h - H) // 2
            bg_img = bg_img.crop((crop_x, crop_y, crop_x + W, crop_y + H))
            canvas.paste(bg_img, (0, 0))
        except Exception as e:
            logger.warning(f"Error processing backdrop image: {e}")

    # Add dark gradient/overlay at bottom/left for text contrast
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    # Darken bottom area (from y=400 to 1080)
    for y in range(350, H):
        alpha = int(210 * ((y - 350) / (H - 350)))
        overlay_draw.line([(0, y), (W, y)], fill=(10, 10, 18, alpha))
    # Darken left side slightly for poster
    for x in range(0, 600):
        alpha = int(120 * ((600 - x) / 600))
        overlay_draw.line([(x, 0), (x, H)], fill=(10, 10, 18, alpha))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    # Process Left Portrait Poster Inset
    poster_w, poster_h = 360, 540
    poster_x, poster_y = 80, (H - poster_h) // 2 + 50
    if poster_bytes:
        try:
            p_img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA")
            p_img = p_img.resize((poster_w, poster_h), Image.LANCZOS)
            p_img = add_rounded_corners(p_img, radius=20)

            # White border around thumbnail
            border_img = Image.new("RGBA", (poster_w + 8, poster_h + 8), (255, 255, 255, 220))
            border_img = add_rounded_corners(border_img, radius=22)
            canvas.paste(border_img, (poster_x - 4, poster_y - 4), border_img)
            canvas.paste(p_img, (poster_x, poster_y), p_img)
        except Exception as e:
            logger.warning(f"Error processing portrait poster: {e}")

    draw = ImageDraw.Draw(canvas)

    # Fonts
    font_title = get_font(72, bold=True)
    font_sub = get_font(32, bold=True)
    font_badge = get_font(28, bold=True)
    font_plot = get_font(34, bold=False)

    # Right Content Position
    content_x = poster_x + poster_w + 60
    content_y = poster_y + 10

    # Title
    title_text = str(movie_doc.get("_id") or "Movie Update").strip()
    # Strip year from end if present
    year_val = str(movie_doc.get("year") or "").strip()
    if year_val and title_text.endswith(year_val):
        title_text = title_text[:-len(year_val)].strip()

    title_lines = wrap_text(title_text, font_title, max_width=W - content_x - 80, max_lines=2)
    current_y = content_y
    for line in title_lines:
        draw.text((content_x, current_y), line, font=font_title, fill=(255, 215, 0)) # Gold title
        bbox = font_title.getbbox(line)
        current_y += (bbox[3] - bbox[1]) + 15

    current_y += 15

    # Badges Row
    badge_x = content_x
    badge_y = current_y

    # Rating badge
    rating_val = str(movie_doc.get("rating") or "-").strip()
    if rating_val and rating_val != "-":
        rating_str = f"★ {rating_val}"
        w = draw_pill(draw, (badge_x, badge_y), bg_color=(20, 20, 20, 230), text=rating_str, font=font_badge, text_color=(255, 215, 0), padding=(14, 8), radius=10)
        badge_x += w + 16

        # IMDb badge
        w = draw_pill(draw, (badge_x, badge_y), bg_color=(245, 197, 24), text="IMDb", font=font_badge, text_color=(0, 0, 0), padding=(14, 8), radius=10)
        badge_x += w + 16

    # Year badge
    if year_val:
        w = draw_pill(draw, (badge_x, badge_y), bg_color=(220, 53, 69), text=year_val, font=font_badge, text_color=(255, 255, 255), padding=(14, 8), radius=10)
        badge_x += w + 16

    # Genre badges
    raw_genres = movie_doc.get("genres", "")
    if isinstance(raw_genres, str):
        genre_list = [g.strip().upper() for g in raw_genres.split(",") if g.strip()]
    else:
        genre_list = [str(g).strip().upper() for g in raw_genres if str(g).strip()]

    colors = [(225, 112, 12), (111, 66, 193), (13, 110, 253), (25, 135, 84)]
    for idx, genre in enumerate(genre_list[:2]): # Max 2 genres to fit row
        color = colors[idx % len(colors)]
        w = draw_pill(draw, (badge_x, badge_y), bg_color=color, text=genre, font=font_badge, text_color=(255, 255, 255), padding=(14, 8), radius=10)
        badge_x += w + 16

    # Telegram handle badge
    w = draw_pill(draw, (badge_x, badge_y), bg_color=(0, 136, 204), text="✈ @cholochhitro", font=font_badge, text_color=(255, 255, 255), padding=(14, 8), radius=10)

    current_y = badge_y + 60

    # Plot overview text
    plot_text = movie_doc.get("plot") or movie_doc.get("overview") or ""
    if not plot_text:
        # Generate clean overview summary string from metadata
        q = movie_doc.get("quality", "HD")
        l = movie_doc.get("language", "")
        plot_text = f"Available in {q} quality. Audio: {l if l else 'Multiple Languages'}. Search and download now on Telegram."

    plot_lines = wrap_text(plot_text, font_plot, max_width=W - content_x - 100, max_lines=3)
    for line in plot_lines:
        draw.text((content_x, current_y), line, font=font_plot, fill=(240, 240, 240))
        bbox = font_plot.getbbox(line)
        current_y += (bbox[3] - bbox[1]) + 12

    # Output image buffer
    final_img = canvas.convert("RGB")
    buf = io.BytesIO()
    final_img.save(buf, format="JPEG", quality=90)
    buf.seek(0)

    img_bytes = buf.getvalue()

    # Cache result
    _POSTER_CACHE[cache_key] = img_bytes
    if len(_POSTER_CACHE) > MAX_CACHE_SIZE:
        _POSTER_CACHE.popitem(last=False)

    out = io.BytesIO(img_bytes)
    out.seek(0)
    return out
