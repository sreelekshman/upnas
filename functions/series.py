import os
import httpx
import re
import asyncio

tmdb_key = os.getenv("TMDb_KEY")

def fetch_series_names(dir):
    try:
        return [name for name in os.listdir(dir) if os.path.isdir(os.path.join(dir, name))]
    except FileNotFoundError:
        return []

async def get_season(episode_number, id, max_retries=3):
    """Fetch the season number given a series ID and episode number."""
    series_url = f"https://api.themoviedb.org/3/tv/{id}?api_key={tmdb_key}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(max_retries):
            try:
                series_response = await client.get(series_url)
                series_response.raise_for_status()
                series_data = series_response.json()
                break
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == max_retries - 1:
                    print(f"Error fetching series details: {e}")
                    return None
                await asyncio.sleep(2)
        
        for season in series_data.get('seasons', []):
            season_number = season['season_number']
            if season_number == 0:  # Skip specials if usually unnecessary
                continue
                
            season_url = f"https://api.themoviedb.org/3/tv/{id}/season/{season_number}?api_key={tmdb_key}"
            for attempt in range(max_retries):
                try:
                    season_response = await client.get(season_url)
                    season_response.raise_for_status()
                    season_data = season_response.json()
                    break
                except (httpx.RequestError, httpx.HTTPStatusError):
                    if attempt == max_retries - 1:
                        season_data = {'episodes': []}
                    await asyncio.sleep(1)
            
            for episode in season_data.get('episodes', []):
                if episode.get('episode_number') == episode_number:
                    return season_number
                    
    return None

def movie_folder_name(filename):
    year_pattern = r"\[?\(?(\d{4})\]?\)?"
    parts = re.split(year_pattern, filename, maxsplit=1)
    if len(parts) < 2:
        return None

    # Replace dots and underscores with spaces
    movie_name = parts[0].replace(".", " ").replace("_", " ")
    
    # Remove anything in brackets [] or ()
    movie_name = re.sub(r"[\[\(].*?[\)\]]", "", movie_name).strip()
    
    # Sometimes names might have extra dashes or weird prefixes if not caught by brackets
    movie_name = re.sub(r"^[-_ ]+", "", movie_name)

    year_match = re.search(year_pattern, parts[1])
    if year_match:
        year = year_match.group(1)
    else:
        return None

    return f"{movie_name} ({year})"

async def series_id(name, max_retries=3):
    name = name.replace(' ', '+')
    url = f'https://api.themoviedb.org/3/search/tv?api_key={tmdb_key}&query={name}'
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                break
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == max_retries - 1:
                    print(f"Error searching series: {e}")
                    return None
                await asyncio.sleep(2)

    results = data.get('results', [])
    if not results:
        return None
        
    for i in range(max(1, len(results) // 2)):
        if i < len(results) and results[i].get('original_language') == 'ja':
            return results[i].get('id')
            
    return results[0].get('id')

def extract_season_episode(filename):
    # s01e01, S01 E01, S01 - E01, S1E1, etc.
    match = re.search(r's(\d+)\s*[-_]?\s*e(\d+)', filename, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Match episode with E like "E01" or "E 01" or "ep01"
    match = re.search(r'(?<!s\d)(?:e|ep)\s*[-_]?\s*(\d+)', filename, re.IGNORECASE)
    if match:
        return None, int(match.group(1))

    # Match pure numbers if separated like "- 01" or "- 1071"
    match = re.search(r'-\s*(\d{1,4})(?!\d)', filename)
    if match:
        return None, int(match.group(1))
        
    # Anime style " 1071 " or " 1071.mkv"
    match = re.search(r'(?:\s|-|_)(0?\d{1,4})(?:\s|-|_|\.|v\d|\])', filename)
    if match:
        ep_candidate = int(match.group(1))
        # Ignore common video resolutions or codecs that might be falsely matched
        if ep_candidate not in [480, 720, 1080, 2160, 264, 265]:
            return None, ep_candidate

    return None, None
