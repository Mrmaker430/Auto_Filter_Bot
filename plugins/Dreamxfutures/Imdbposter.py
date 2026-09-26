import re
import asyncio
import aiohttp
import warnings
import logging
from io import BytesIO
from datetime import datetime
from difflib import SequenceMatcher
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, TMDB_API_KEY, OMDB_API_KEY, MAX_LIST_ELM

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


async def _fetch_media_details(media_type: str, media_id: int, api_key=None):
    """Fetch full details for a movie or TV show from TMDB."""
    params = {'append_to_response': 'credits,external_ids,alternative_titles,release_dates,images'}
    return await _tmdb_get(f"{media_type}/{media_id}", params=params, api_key=api_key)


async def _search_media_id(query: str, api_key=None):
    """Search TMDB for the best matching movie/TV show and return (media_type, media_id)."""
    title, year = _extract_title_and_year(query)
    
    multi_results = []
    words = title.split()
    
    # Generate up to 3 fallback queries to minimize API rate limit usage
    queries_to_try = [title]
    if len(words) > 2:
        queries_to_try.append(" ".join(words[:-1]))  # Drop the last word
        queries_to_try.append(words[0])              # Keep just the first word
    elif len(words) == 2:
        queries_to_try.append(words[0])
        
    # Remove any duplicates but preserve order, capping at 3 attempts
    queries_to_try = list(dict.fromkeys(queries_to_try))[:3]
    
    for target_query in queries_to_try:
        if not target_query:
            continue
        params = {'query': target_query, 'language': 'en-US', 'page': 1, 'include_adult': 'false'}
        result = await _tmdb_get('search/multi', params=params, api_key=api_key)
        multi_results = result.get('results', [])
        if multi_results:
            break

    def get_ratio(s1, s2):
        if not s1 or not s2:
            return 0
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    scored_results = []
    for r in multi_results:
        # Score the string matched against the ORIGINAL title, not the shortened target_query
        res_title = r.get('title') or r.get('name')
        ratio = get_ratio(res_title, title)
        if ratio >= 0.5:
            scored_results.append((r, ratio))

    if not scored_results:
        scored_results = [(r, get_ratio(r.get('title') or r.get('name'), title)) for r in multi_results[:10]]

    today = datetime.utcnow().date()
    candidates_past, candidates_upcoming = [], []
    for r, ratio in scored_results:
        mtype = r.get('media_type')
        rd_str = r.get('release_date') or r.get('first_air_date')
        if not (rd_str and mtype in ['movie', 'tv']):
            continue
        try:
            rd_date = datetime.strptime(rd_str, '%Y-%m-%d').date()
        except ValueError:
            continue

        # Calculate year match score multiplier
        year_bonus = 0.0
        if year:
            year_diff = abs(rd_date.year - year)
            if year_diff > 2:
                continue
            elif year_diff == 0:
                year_bonus = 0.25
            elif year_diff == 1:
                year_bonus = 0.1

        if mtype == 'movie':
            try:
                details = await _fetch_media_details(mtype, r['id'], api_key=api_key)
                runtime = details.get('runtime')
                is_video = details.get('video', False)

                if is_video or (runtime and runtime < MIN_RUNTIME):
                    continue
            except Exception:
                continue
        candidate = {
            'type': mtype,
            'id': r['id'],
            'date': rd_date,
            'score': r.get('popularity', 0),
            'ratio': ratio + year_bonus
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


async def _fetch_tmdb_data(query: str, api_key=None):
    """
    Core TMDB lookup: search → fetch details → build response dict.
    This replaces the external tmdb.blazeposters.workers.dev API call.
    """
    media_type, media_id = await _search_media_id(query, api_key=api_key)
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


async def _fetch_omdb_data(query: str, id: bool = False, api_key: str = None):
    """
    Fetch movie/series details directly from OMDB API.
    """
    key = api_key or OMDB_API_KEY or '52a3fdbd'
    q = str(query).strip()
    session = await get_session()

    data = None
    if id or q.startswith("tt"):
        imdb_id = q if q.startswith("tt") else f"tt{q}"
        url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={key}"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("Response") == "True":
                        data = res
        except Exception as e:
            logger.error(f"Error fetching OMDB by ID '{imdb_id}': {e}")

    if not data:
        title, year = _extract_title_and_year(q)
        params = {'t': title, 'apikey': key}
        if year:
            params['y'] = str(year)

        try:
            async with session.get("http://www.omdbapi.com/", params=params) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("Response") == "True":
                        data = res
        except Exception as e:
            logger.error(f"Error fetching OMDB by title '{title}': {e}")

        if not data and year:
            try:
                async with session.get("http://www.omdbapi.com/", params={'t': title, 'apikey': key}) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get("Response") == "True":
                            data = res
            except Exception:
                pass

        if not data:
            try:
                async with session.get("http://www.omdbapi.com/", params={'s': title, 'apikey': key}) as resp:
                    if resp.status == 200:
                        s_res = await resp.json()
                        search_list = s_res.get("Search", [])
                        if search_list:
                            first_id = search_list[0].get("imdbID")
                            if first_id:
                                async with session.get(f"http://www.omdbapi.com/?i={first_id}&apikey={key}") as resp2:
                                    if resp2.status == 200:
                                        res2 = await resp2.json()
                                        if res2.get("Response") == "True":
                                            data = res2
            except Exception as e:
                logger.error(f"Error fetching OMDB search for '{title}': {e}")

    if not data or data.get("Response") != "True":
        return None

    poster_raw = data.get("Poster")
    poster_url = None
    if poster_raw and poster_raw != "N/A" and poster_raw.startswith("http"):
        if "._V1_" in poster_raw:
            poster_url = poster_raw.split("._V1_")[0] + "._V1_SX1280.jpg"
        else:
            poster_url = poster_raw

    rating_val = data.get("imdbRating")
    try:
        rating = round(float(rating_val), 1) if rating_val and rating_val != "N/A" else None
    except Exception:
        rating = None

    def _split_commas(val):
        if not val or val == "N/A":
            return []
        return [s.strip() for s in val.split(",") if s.strip()]

    return {
        'title': data.get("Title"),
        'year': int(data.get("Year")[:4]) if data.get("Year") and data.get("Year")[:4].isdigit() else data.get("Year"),
        'release_date': data.get("Released") if data.get("Released") != "N/A" else None,
        'rating': rating,
        'votes': int(data.get("imdbVotes").replace(",", "")) if data.get("imdbVotes") and data.get("imdbVotes") != "N/A" and data.get("imdbVotes").replace(",", "").isdigit() else 0,
        'runtime': data.get("Runtime") if data.get("Runtime") != "N/A" else None,
        'certificates': data.get("Rated") if data.get("Rated") != "N/A" else None,
        'genres': _split_commas(data.get("Genre")),
        'languages': _split_commas(data.get("Language")),
        'countries': _split_commas(data.get("Country")),
        'director': _split_commas(data.get("Director")),
        'writer': _split_commas(data.get("Writer")),
        'cast': _split_commas(data.get("Actors")),
        'plot': data.get("Plot") if data.get("Plot") != "N/A" else "",
        'tagline': None,
        'box_office': data.get("BoxOffice") if data.get("BoxOffice") != "N/A" else None,
        'distributors': [],
        'poster_url': poster_url,
        'backdrop_url': poster_url,
        'logo_url': None,
        'imdb_id': data.get("imdbID"),
        'tmdb_id': None,
        'kind': 'movie' if data.get("Type") == 'movie' else 'tv series',
        'url': f"https://www.imdb.com/title/{data.get('imdbID')}" if data.get("imdbID") else None,
    }


async def get_movie_details_omdb(query, id=False, file=None):
    """
    Fetches movie/series details directly from OMDB API.
    """
    return await _fetch_omdb_data(query, id=id)


async def get_movie_detailsx(query, id=False, file=None):
    """
    Primary movie details fetcher using direct TMDB API calls with OMDB fallback.
    Falls back to OMDB then IMDb-based get_movie_details() on failure.
    """
    q = str(query).strip()
    data = None
    try:
        data = await _fetch_tmdb_data(q, api_key=TMDB_API_KEY or None)
    except Exception as e:
        logger.error(f"TMDB direct call failed: {e}")

    # If TMDB failed or returned no poster_url, try OMDB API
    if not data or not (data.get("poster_url") or data.get("images", {}).get("posters")):
        try:
            omdb_data = await _fetch_omdb_data(q, id=id)
            if omdb_data and omdb_data.get("poster_url"):
                return omdb_data
        except Exception as e:
            logger.error(f"OMDB call failed: {e}")

    if not data:
        logger.warning(f"TMDB & OMDB returned no results for '{q}' → switching to IMDb fallback")
        return await get_movie_details(q)

    # Normalize fields
    details = {}
    details['title'] = data.get('title') or data.get('localized_title')
    details['year'] = (data.get('year', 0)) if data.get('year') else None
    details['release_date'] = data.get('release_date')
    details['rating'] = round(float(data.get('rating', 0)), 1) if data.get('rating') is not None else None
    details['votes'] = int(data.get('votes', 0))
    details['runtime'] = data.get('runtime')
    details['certificates'] = data.get('certificates')
    details['tmdb_url'] = data.get('url')
    
    for key in ('genres', 'languages', 'countries'):
        raw = data.get(key)
        details[key] = [s.strip() for s in raw.split(',')] if raw else []
    for role in ('director', 'writer', 'producer', 'composer', 'cinematographer', 'cast'):
        raw = data.get(role)
        details[role] = [s.strip() for s in raw.split(',')] if raw else []
        
    details['plot'] = data.get('plot')
    details['tagline'] = data.get('tagline')
    details['box_office'] = (data.get('box_office', 0)) if data.get('box_office') else None
    raw_dist = data.get('distributors')
    details['distributors'] = [d.strip() for d in raw_dist.split(',')] if raw_dist else []
    details['imdb_id'] = data.get('imdb_id')
    details['tmdb_id'] = data.get('tmdb_id')
    
    posters = data.get('images', {}).get('posters', {})
    original_language = data.get('images', {}).get('original_language')
    poster_url = data.get('poster_url')
    if not poster_url:
        for key in ('en', original_language, 'xx'):
            if key and posters.get(key):
                poster_url = posters[key][0]
                break
    details['poster_url'] = poster_url.replace("/original/", "/w1280/") if poster_url else None

    backdrops = data.get('images', {}).get('backdrops', {})
    original_language = data.get('images', {}).get('original_language')
    backdrop_url = None
    for key in ('en', original_language, 'xx', 'no_lang'):
        if key and backdrops.get(key):
            backdrop_url = backdrops[key][0]
            break
    details['backdrop_url'] = backdrop_url.replace("/original/", "/w1280/") if backdrop_url else None

    logos = data.get('images', {}).get('logos', {})
    logo_url = None
    for key in ('en', original_language, 'xx', 'no_lang', 'all'):
        if key and logos.get(key):
            logo_url = logos[key][0]
            break
    details['logo_url'] = logo_url.replace("/original/", "/w500/") if logo_url else None

    return details

