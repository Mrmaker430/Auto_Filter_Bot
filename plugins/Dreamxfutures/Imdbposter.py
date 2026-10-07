import re
import time
import asyncio
import aiohttp
import warnings
import logging
from io import BytesIO
from datetime import datetime
from difflib import SequenceMatcher
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, TMDB_API_KEY, MAX_LIST_ELM

logger = logging.getLogger(__name__)

LONG_IMDB_DESCRIPTION = False

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

#TMDB API ADDED BY @Bharath_boy

# --- TMDB Configuration ---
TMDB_BEARER_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2ZGU3YTIyZGU1YjE5YTFjNmUyZGU5ZWEyMzE2ZmQxMCIsIm5iZiI6MTc0NTMyMjQ2Mi41MzMsInN1YiI6IjY4MDc4MWRlYzVjODAzNWZiMDhhNjExNCIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.rMMJ2-PBIv8Y7ybxPIEpIlzTEXzuwrm9ruKxAUCAsbw'
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/original'
MIN_RUNTIME = 40

_session: aiohttp.ClientSession | None = None


# --- In-Memory Caching and Timeouts ---
TMDB_DETAILS_CACHE = {}
IMDB_DETAILS_CACHE = {}
CACHE_MAX_SIZE = 500
CACHE_TTL = 3600  # 1 hour

def _get_from_cache(cache_dict, key):
    if key in cache_dict:
        data, timestamp = cache_dict[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            del cache_dict[key]
    return None

def _set_in_cache(cache_dict, key, data):
    if len(cache_dict) >= CACHE_MAX_SIZE:
        # Remove oldest entry
        oldest_key = next(iter(cache_dict))
        cache_dict.pop(oldest_key, None)
    cache_dict[key] = (data, time.time())

# --- Query cleaning helpers ---
_MATH_ALNUM = re.compile(r'[\U0001D400-\U0001D7FF]+')                 # fancy unicode like 𝑺𝒂𝒕𝒚𝒂𝒋𝒊𝒕
_SXXEXX     = re.compile(r'[Ss](\d{1,2})[\s\.\-_]*[Ee](\d{1,3})')     # S01E01, s1e1, S01.E01
_SEASON_WORD= re.compile(r'\b(?:Season|Episode|Ep)\s*\d+\b', re.IGNORECASE)
_FILE_EXT   = re.compile(r'\.(mkv|mp4|avi|mov|webm|flv|wmv|ts|m2ts|m4v)$', re.IGNORECASE)

_JUNK_TAGS = re.compile(
    r'\b(?:'
    r'480p|540p|720p|1080p|1440p|2160p|4k|8k|'
    r'HDTV|WEB[- ]?DL|WEB[- ]?Rip|WEBRip|WEB|BluRay|Blu[- ]?Ray|BRRip|BDRip|HDRip|DVDRip|HDCAM|HDTS|'
    r'x264|x265|h\.?264|h\.?265|HEVC|AVC|10bit|8bit|'
    r'AAC|AAC5\.1|AC3|EAC3|DDP?5\.1|DD5\.1|DTS|DTS[- ]?HD|TrueHD|FLAC|MP3|'
    r'ESubs|ESub|Subs|Subbed|Subtitle|Subtitles|Dubbed|Dual[ -]?Audio|Multi[ -]?Audio|'
    r'Hindi|Korean|English|Tamil|Telugu|Malayalam|Kannada|Bengali|Marathi|Urdu|Japanese|Chinese|'
    r'ORG|AMZN|NF|DSNP|HMAX|ATVP|iTunes|HULU|ZEE5|SonyLIV|Hotstar|'
    r'Remux|Proper|Repack|Extended|Unrated|Theatrical|'
    r'MKV|MP4|AVI|MOV|WEBM'
    r')\b',
    re.IGNORECASE
)


def _clean_query(query: str):
    """Strip release-group junk, quality tags and SxxExx markers.
    Returns (clean_title, season, episode)."""
    q = str(query or '')
    q = _MATH_ALNUM.sub(' ', q)
    q = _FILE_EXT.sub(' ', q)

    season = episode = None
    m = _SXXEXX.search(q)
    if m:
        season  = int(m.group(1))
        episode = int(m.group(2))
        q = _SXXEXX.sub(' ', q)

    q = _SEASON_WORD.sub(' ', q)
    q = _JUNK_TAGS.sub(' ', q)
    q = re.sub(r'[\._\-]+', ' ', q)
    q = re.sub(r'\s+', ' ', q).strip()
    return q, season, episode


async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )
    return _session

async def fetch_image(url, size=(860, 1200)):
    if not DREAMXBOTZ_IMAGE_FETCH:
        logger.info("Image fetching is disabled.")
        return url

    try:
        session = await get_session()

        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch image: {response.status} for {url}")
                return None

            data = await response.read()
            img = Image.open(BytesIO(data))
            img = img.resize(size, Image.LANCZOS)

            out = BytesIO()
            img.save(out, format="JPEG")
            out.seek(0)
            return out

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request error in fetch_image: {e}")
    except IOError as e:
        logger.error(f"I/O error in fetch_image: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_image: {e}")

    return None


async def close_session():
    if _session and not _session.closed:
        await _session.close()

def list_to_str(lst):
    if lst:
        return ", ".join(map(str, lst))
    return ""


def _list_to_str_tmdb(data_list, limit=10, key=None):
    """Helper for formatting TMDB response lists to comma-separated strings."""
    if not data_list or not isinstance(data_list, list):
        return None
    items = data_list[:limit]
    if key:
        return ", ".join(str(item.get(key, '')) for item in items if item)
    return ", ".join(str(item) for item in items if item)


def _extract_title_and_year(query: str):
    """Extract title and optional 4-digit release year from a search query string."""
    clean_q = query.strip()
    year_match = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', clean_q)
    if year_match:
        year = int(year_match.group(1))
        # Remove year and surrounding brackets/parentheses
        title = re.sub(r'\(?\b' + str(year) + r'\b\)?', '', clean_q).strip()
        title = re.sub(r'\s+', ' ', title).strip()
        return title if title else clean_q, year
    return clean_q, None


async def _tmdb_get(path, params=None, api_key=None):
    """Async GET request to TMDB API using aiohttp."""
    url = f"{TMDB_BASE_URL}/{path.lstrip('/')}"
    _params = params.copy() if params else {}
    _headers = {}

    if api_key:
        _params['api_key'] = api_key
    elif TMDB_BEARER_TOKEN:
        _headers = {
            'Authorization': f'Bearer {TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

    session = await get_session()
    async with session.get(url, params=_params, headers=_headers, ssl=False) as resp:
        resp.raise_for_status()
        return await resp.json()


def is_korean_media(item: dict, media_type: str = "tv") -> bool:
    """Check if TMDB item is Korean drama/movie based on origin_country or original_language."""
    if not item or not isinstance(item, dict):
        return False
    if media_type in ['tv', 'series', 'show', 'shows', 'kdrama', 'k-drama']:
        return "KR" in item.get("origin_country", []) or item.get("original_language") == "ko"
    return item.get("original_language") == "ko" or "KR" in item.get("origin_country", [])


async def search_korean_media(query: str, media_type: str = "tv", limit: int = 10, api_key=None) -> list:
    """Search Korean dramas or movies on TMDB."""
    endpoint = 'search/tv' if media_type in ['tv', 'series', 'show', 'shows', 'kdrama', 'k-drama'] else 'search/movie'
    data = await _tmdb_get(endpoint, params={'query': query, 'include_adult': 'false'}, api_key=api_key or TMDB_API_KEY or None)
    results = data.get('results', []) if isinstance(data, dict) else []
    korean_results = [item for item in results if is_korean_media(item, media_type)]
    return korean_results[:limit]


async def get_popular_korean_media(media_type: str = "tv", limit: int = 10, api_key=None) -> list:
    """Fetch popular Korean dramas or movies from TMDB."""
    if media_type in ['tv', 'series', 'show', 'shows', 'kdrama', 'k-drama']:
        endpoint = 'discover/tv'
        params = {
            'with_origin_country': 'KR',
            'sort_by': 'popularity.desc',
            'page': 1
        }
    else:
        endpoint = 'discover/movie'
        params = {
            'with_original_language': 'ko',
            'sort_by': 'popularity.desc',
            'page': 1
        }
    data = await _tmdb_get(endpoint, params=params, api_key=api_key or TMDB_API_KEY or None)
    results = data.get('results', []) if isinstance(data, dict) else []
    return results[:limit]


async def _fetch_media_details(media_type: str, media_id: int, api_key=None):
    """Fetch full details for a movie or TV show from TMDB."""
    params = {
        'append_to_response': 'credits,external_ids,alternative_titles,release_dates,images',
        'include_image_language': 'en,ko,null'
    }
    return await _tmdb_get(f"{media_type}/{media_id}", params=params, api_key=api_key)


async def _search_media_id(query: str, api_key=None, category=None):
    """Search TMDB for the best matching movie/TV show and return (media_type, media_id)."""
    cleaned, season, episode = _clean_query(query)
    title, year = _extract_title_and_year(cleaned)
    raw_title, raw_year = _extract_title_and_year(query.strip())
    if not title and not raw_title:
        return None, None

    # Build fallback queries — preserving raw title as first option if valid
    queries_to_try = []
    if raw_title and len(raw_title) > 0:
        queries_to_try.append(raw_title)
    if title and title not in queries_to_try:
        queries_to_try.append(title)

    words = (title or raw_title).split()
    if len(words) >= 3:
        queries_to_try.append(" ".join(words[:-1]))
    queries_to_try = list(dict.fromkeys([q for q in queries_to_try if q]))

    # Determine endpoint based on category or SxxExx
    if category in ['movie', 'movies']:
        endpoint = 'search/movie'
    elif category in ['series', 'tv', 'show', 'shows', 'kdrama', 'k-drama'] or season is not None:
        endpoint = 'search/tv'
    else:
        endpoint = 'search/multi'

    multi_results = []
    for target_query in queries_to_try:
        if not target_query:
            continue
        params = {'query': target_query, 'language': 'en-US', 'page': 1, 'include_adult': 'false'}
        result = await _tmdb_get(endpoint, params=params, api_key=api_key)
        multi_results = result.get('results', [])
        if multi_results:
            break

    target_words = set(re.findall(r'\w+', (title or raw_title).lower()))

    def get_title_score(res_title):
        if not res_title or not (title or raw_title):
            return 0.0
        res_clean = res_title.lower().strip()
        title_clean = (title or raw_title).lower().strip()
        if res_clean == title_clean:
            return 1.0

        res_words = set(re.findall(r'\w+', res_clean))
        extra_words = res_words - target_words
        base_ratio = SequenceMatcher(None, res_clean, title_clean).ratio()

        if res_clean.startswith(title_clean) or title_clean in res_clean:
            return max(0.5, base_ratio - (0.1 * len(extra_words)))

        # Heavily penalize candidate titles that contain extra words not in search query
        penalty = 0.25 * len(extra_words)
        return max(0.0, base_ratio - penalty)

    scored_results = []
    for r in multi_results:
        res_title = r.get('title') or r.get('name')
        t_score = get_title_score(res_title)
        if t_score >= 0.45 or (res_title and res_title.lower().strip() in [title.lower().strip() if title else '', raw_title.lower().strip() if raw_title else '']):
            scored_results.append((r, t_score))

    if not scored_results:
        return None, None

    is_korean_query = any(k in query.lower() for k in ['korean', 'kdrama', 'k-drama']) or category in ['kdrama', 'k-drama']

    today = datetime.utcnow().date()
    candidates_past, candidates_upcoming = [], []
    for r, ratio in scored_results:
        mtype = r.get('media_type')
        if not mtype:
            if endpoint == 'search/movie':
                mtype = 'movie'
            elif endpoint == 'search/tv':
                mtype = 'tv'
            else:
                mtype = None
        if category in ['movie', 'movies'] and mtype != 'movie':
            continue
        if category in ['series', 'tv', 'show', 'shows', 'kdrama', 'k-drama'] and mtype != 'tv':
            continue

        rd_str = r.get('release_date') or r.get('first_air_date')
        if not (rd_str and mtype in ['movie', 'tv']):
            continue
        try:
            rd_date = datetime.strptime(rd_str, '%Y-%m-%d').date()
        except ValueError:
            continue

        year_bonus = 0.0
        effective_year = year or raw_year
        if effective_year:
            year_diff = abs(rd_date.year - effective_year)
            if year_diff == 0:
                year_bonus = 0.20
            elif year_diff == 1:
                year_bonus = 0.10
            elif year_diff == 2:
                year_bonus = 0.05
            else:
                year_bonus = -0.10

        korean_bonus = 0.0
        if is_korean_query and is_korean_media(r, mtype):
            korean_bonus = 0.15

        if mtype == 'movie':
            try:
                details = await _fetch_media_details(mtype, r['id'], api_key=api_key)
                runtime  = details.get('runtime')
                is_video = details.get('video', False)
                if is_video or (runtime and runtime < MIN_RUNTIME):
                    continue
            except Exception:
                continue

        candidate = {
            'type':  mtype,
            'id':    r['id'],
            'date':  rd_date,
            'score': r.get('popularity', 0),
            'ratio': ratio + year_bonus + korean_bonus
        }
        (candidates_upcoming if rd_date > today else candidates_past).append(candidate)

    candidates_past.sort(key=lambda x: (x['ratio'], x['date'], x['score']), reverse=True)
    candidates_upcoming.sort(key=lambda x: (x['ratio'], x['date'], x['score']), reverse=True)
    final = candidates_past or candidates_upcoming
    if not final:
        return None, None
    top = final[0]
    return top['type'], top['id']


def _process_images(images_data):
    """Organize poster, backdrop, and logo images by language."""
    posters_by_lang, backdrops_by_lang, logos_by_lang = {}, {}, {}
    for img in images_data.get('posters', []):
        lang = img.get('iso_639_1') or 'no_lang'
        posters_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    for img in images_data.get('backdrops', []):
        lang = img.get('iso_639_1') or 'no_lang'
        backdrops_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    for img in images_data.get('logos', []):
        lang = img.get('iso_639_1') or 'no_lang'
        logos_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    posters_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('posters', [])]
    backdrops_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('backdrops', [])]
    logos_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('logos', [])]
    languages = sorted(set(posters_by_lang) | set(backdrops_by_lang) | set(logos_by_lang))
    return {'posters': posters_by_lang, 'backdrops': backdrops_by_lang, 'logos': logos_by_lang, 'available_languages': languages}


async def _fetch_tmdb_data(query: str, api_key=None, category=None):
    """
    Core TMDB lookup: search → fetch details → build response dict.
    This replaces the external tmdb.blazeposters.workers.dev API call.
    """
    media_type, media_id = await _search_media_id(query, api_key=api_key, category=category)
    if not media_id:
        return None

    details = await _fetch_media_details(media_type, media_id, api_key=api_key)
    crew = details.get('credits', {}).get('crew', [])

    certificates = None
    if media_type == 'movie' and 'release_dates' in details:
        us = [r for r in details['release_dates']['results'] if r['iso_3166_1'] == 'US']
        if us and us[0]['release_dates']:
            certificates = us[0]['release_dates'][0].get('certification')

    runtime_display = None
    if media_type == 'movie':
        runtime = details.get('runtime')
        runtime_display = f"{runtime} min" if runtime else None
    else:
        er = _list_to_str_tmdb(details.get('episode_run_time', []))
        runtime_display = f"{er} min" if er else None

    images_structured = _process_images(details.get('images', {}))
    images_structured['original_language'] = details.get('original_language')

    output_data = {
        'query': query, 'media_type': media_type, 'media_id': media_id,
        'title': details.get('title') or details.get('name'),
        'localized_title': details.get('original_title') or details.get('original_name'),
        'aka': _list_to_str_tmdb(details.get('alternative_titles', {}).get('titles', []), key='title'),
        'kind': media_type,
        'year': (details.get('release_date') or details.get('first_air_date', ''))[:4],
        'release_date': details.get('release_date') or details.get('first_air_date'),
        'imdb_id': details.get('external_ids', {}).get('imdb_id'),
        'tmdb_id': details.get('id'),
        'rating': details.get('vote_average'),
        'votes': details.get('vote_count'),
        'runtime': runtime_display,
        'certificates': certificates,
        'genres': _list_to_str_tmdb(details.get('genres', []), key='name'),
        'languages': _list_to_str_tmdb(details.get('spoken_languages', []), key='english_name'),
        'countries': _list_to_str_tmdb(details.get('production_countries', []), key='name'),
        'director': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Director'], key='name'),
        'writer': _list_to_str_tmdb([p for p in crew if p.get('job') in ['Screenplay', 'Writer', 'Story']], key='name'),
        'producer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Producer'], key='name'),
        'composer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Original Music Composer'], key='name'),
        'cinematographer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Director of Photography'], key='name'),
        'cast': _list_to_str_tmdb(details.get('credits', {}).get('cast', []), key='name', limit=15),
        'plot': details.get('overview'),
        'tagline': details.get('tagline'),
        'box_office': details.get('revenue') if details.get('revenue', 0) > 0 else "N/A",
        'distributors': _list_to_str_tmdb(details.get('production_companies', []), key='name'),
        'poster_url': f"{TMDB_IMAGE_BASE_URL}{details.get('poster_path')}" if details.get('poster_path') else None,
        'url': f"https://www.themoviedb.org/{media_type}/{details.get('id')}",
        'images': images_structured,
    }

    if media_type == 'tv':
        output_data.update({
            'seasons': details.get('number_of_seasons'),
            'episodes': details.get('number_of_episodes'),
        })

    return output_data


async def get_movie_details(query, bulk=False, id=False, file=None):
    cache_key = f"{str(query).strip().lower()}_bulk={bulk}_id={id}_file={file}"
    if not bulk:
        cached = _get_from_cache(IMDB_DETAILS_CACHE, cache_key)
        if cached is not None:
            return cached

    result = await _get_movie_details_uncached(query, bulk=bulk, id=id, file=file)
    if result and not bulk:
        _set_in_cache(IMDB_DETAILS_CACHE, cache_key, result)
    return result

async def _get_movie_details_uncached(query, bulk=False, id=False, file=None):
    if not id:
        from utils import listx_to_str, imdb
        query = (query.strip()).lower()
        title = query
        year_val = None
        
        year_list = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        if year_list:
            year_val = year_list[0]
            title = (query.replace(year_val, "")).strip()
        elif file is not None:
            year_list = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            if year_list:
                year_val = year_list[0]
        
        search_result = await asyncio.to_thread(imdb.search_movie, title.lower())
        if not search_result or not search_result.titles:
            return None
        
        movie_list = search_result.titles[:MAX_LIST_ELM]
        
        if year_val:
            filtered = [m for m in movie_list if m.year and str(m.year) == str(year_val)]
            if not filtered:
                filtered = movie_list
        else:
            filtered = movie_list
            
        kind_filter = ['movie', 'tv series', 'tvSeries', 'tvMiniSeries', 'tvMovie']
        filtered_kind = [m for m in filtered if m.kind and m.kind in kind_filter]
        
        if not filtered_kind:
            filtered_kind = filtered
        
        if bulk:
            return filtered_kind[:MAX_LIST_ELM]
        if not filtered_kind:
            return None   
        movie_brief = filtered_kind[0]
        movieid_str = movie_brief.imdb_id 
    else:
        movieid_str = query

    movie = await asyncio.to_thread(imdb.get_movie, movieid_str)
    if not movie:
        return None

    if movie.release_date:
        date = movie.release_date
    elif movie.year:
        date = str(movie.year)
    else:
        date = "N/A"
        
    plot = movie.plot[0] if isinstance(movie.plot, list) else movie.plot or ""
    if len(plot) > 800:
        plot = plot[:800] + "..."
    imdb_id = movie.imdb_id
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
    return {
        'title': movie.title,
        'votes': movie.votes,
        "aka": listx_to_str(movie.title_akas),
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": movie.worldwide_gross,
        'localized_title': movie.title_localized,
        'kind': movie.kind,
        "imdb_id": imdb_id,
        "cast": listx_to_str(movie.stars),
        "runtime": listx_to_str(movie.duration),
        "countries": listx_to_str(movie.countries),
        "certificates": listx_to_str(movie.certificates),
        "languages": listx_to_str(movie.languages),
        "director": listx_to_str(movie.directors),
        "writer": listx_to_str([p.name for p in movie.writers]),
        "producer": listx_to_str([p.name for p in movie.producers]),
        "composer": listx_to_str([p.name for p in movie.composers]),
        "cinematographer": listx_to_str([p.name for p in movie.cinematographers]),
        "music_team": listx_to_str([p.name for p in movie.music_team]),
        "distributors": listx_to_str([c.name for c in movie.distributors]),        
        'release_date': date,
        'year': movie.year,
        'genres': listx_to_str(movie.genres),
        'poster': movie.cover_url,
        'poster_url': movie.cover_url.split("._V1_")[0] + "._V1_SX1280.jpg" if movie.cover_url and "._V1_" in movie.cover_url else movie.cover_url,
        'plot': plot,
        'rating': str(movie.rating),
        "url": movie.url or f"https://www.imdb.com/title/{imdb_id}"
    }


async def get_category_candidates(query: str):
    """
    Fast lookup for movie and TV series candidate title/year from TMDB.
    Uses caching to avoid repeated full details API calls.
    """
    clean_q, _, _ = _clean_query(query)
    title, year = _extract_title_and_year(clean_q)
    if not title:
        return {'movie': None, 'series': None}

    cache_key = f"cat_cand_{title.lower()}_{year}"
    cached = _get_from_cache(TMDB_DETAILS_CACHE, cache_key)
    if cached is not None:
        return cached

    params_m = {'query': title, 'language': 'en-US', 'page': 1, 'include_adult': 'false'}
    params_tv = {'query': title, 'language': 'en-US', 'page': 1, 'include_adult': 'false'}

    try:
        res_m, res_tv = await asyncio.gather(
            _tmdb_get('search/movie', params=params_m, api_key=TMDB_API_KEY or None),
            _tmdb_get('search/tv', params=params_tv, api_key=TMDB_API_KEY or None),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Error fetching category candidates: {e}")
        res_m = res_tv = None

    m_candidate = None
    if isinstance(res_m, dict) and res_m.get('results'):
        top_m = res_m['results'][0]
        m_title = top_m.get('title')
        m_date = top_m.get('release_date') or ''
        m_year = m_date[:4] if len(m_date) >= 4 else None
        m_candidate = {'title': m_title, 'year': m_year}

    tv_candidate = None
    if isinstance(res_tv, dict) and res_tv.get('results'):
        top_tv = res_tv['results'][0]
        tv_title = top_tv.get('name')
        tv_date = top_tv.get('first_air_date') or ''
        tv_year = tv_date[:4] if len(tv_date) >= 4 else None
        tv_candidate = {'title': tv_title, 'year': tv_year}

    result = {'movie': m_candidate, 'series': tv_candidate}
    _set_in_cache(TMDB_DETAILS_CACHE, cache_key, result)
    return result


async def get_movie_detailsx(query, id=False, file=None, category=None):
    """
    Primary movie details fetcher: fetches details and media images from TMDB.
    Falls back to IMDb on failure. Uses caching and timeout protection.
    """
    q = str(query).strip()
    cache_key = f"{q.lower()}_id={id}_file={file}_cat={category}"
    cached = _get_from_cache(TMDB_DETAILS_CACHE, cache_key)
    if cached is not None:
        return cached

    tmdb_data = None

    try:
        try:
            tmdb_data = await asyncio.wait_for(_fetch_tmdb_data(q, api_key=TMDB_API_KEY or None, category=category), timeout=8.0)
        except TypeError:
            tmdb_data = await asyncio.wait_for(_fetch_tmdb_data(q, api_key=TMDB_API_KEY or None), timeout=8.0)
    except asyncio.TimeoutError:
        logger.warning(f"TMDB request timed out for query '{q}'")
    except Exception as e:
        logger.error(f"TMDB call error in get_movie_detailsx: {e}")

    if tmdb_data and isinstance(tmdb_data, dict):
        details = {}
        details['title'] = tmdb_data.get('title') or tmdb_data.get('localized_title')
        details['year'] = int(tmdb_data.get('year')) if tmdb_data.get('year') and str(tmdb_data.get('year')).isdigit() else tmdb_data.get('year')
        details['release_date'] = tmdb_data.get('release_date')
        details['rating'] = round(float(tmdb_data.get('rating', 0)), 1) if tmdb_data.get('rating') is not None else None
        details['votes'] = int(tmdb_data.get('votes', 0))
        details['runtime'] = tmdb_data.get('runtime')
        details['certificates'] = tmdb_data.get('certificates')
        details['tmdb_url'] = tmdb_data.get('url')

        for key in ('genres', 'languages', 'countries'):
            raw = tmdb_data.get(key)
            details[key] = [s.strip() for s in raw.split(',')] if raw else []
        for role in ('director', 'writer', 'producer', 'composer', 'cinematographer', 'cast'):
            raw = tmdb_data.get(role)
            details[role] = [s.strip() for s in raw.split(',')] if raw else []

        details['plot'] = tmdb_data.get('plot')
        details['tagline'] = tmdb_data.get('tagline')
        details['box_office'] = (tmdb_data.get('box_office', 0)) if tmdb_data.get('box_office') else None
        raw_dist = tmdb_data.get('distributors')
        details['distributors'] = [d.strip() for d in raw_dist.split(',')] if raw_dist else []
        details['imdb_id'] = tmdb_data.get('imdb_id')
        details['tmdb_id'] = tmdb_data.get('tmdb_id')

        posters = tmdb_data.get('images', {}).get('posters', {})
        original_language = tmdb_data.get('images', {}).get('original_language')
        poster_url = tmdb_data.get('poster_url')
        if not poster_url:
            for key in ('en', original_language, 'xx'):
                if key and posters.get(key):
                    poster_url = posters[key][0]
                    break
        details['poster_url'] = poster_url

        backdrops = tmdb_data.get('images', {}).get('backdrops', {})
        backdrop_url = None
        for key in ('en', original_language, 'xx', 'no_lang', 'all'):
            if key and backdrops.get(key):
                for b_img in backdrops[key]:
                    if b_img and b_img != poster_url:
                        backdrop_url = b_img
                        break
                if backdrop_url:
                    break
                if not backdrop_url and backdrops[key]:
                    backdrop_url = backdrops[key][0]
                    break

        details['backdrop_url'] = backdrop_url

        logos = tmdb_data.get('images', {}).get('logos', {})
        logo_url = None
        for key in ('en', original_language, 'xx', 'no_lang', 'all'):
            if key and logos.get(key):
                logo_url = logos[key][0]
                break
        details['logo_url'] = logo_url

        _set_in_cache(TMDB_DETAILS_CACHE, cache_key, details)
        return details

    logger.warning(f"TMDB returned no results for '{q}' → switching to IMDb fallback")
    fallback_res = await get_movie_details(q)
    if fallback_res:
        _set_in_cache(TMDB_DETAILS_CACHE, cache_key, fallback_res)
    return fallback_res