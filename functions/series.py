import os
import requests
import re

tmdb_key = os.getenv("TMDb_KEY")

def fetch_series_names(dir):
    return  [name for name in os.listdir(dir)
            if os.path.isdir(os.path.join(dir, name))]
    
# For One Piece only as of now
def get_season(episode_number, id):
    # Step 1: Fetch series details
    series_url = f"https://api.themoviedb.org/3/tv/{id}?api_key={tmdb_key}"
    series_response = requests.get(series_url)
    series_data = series_response.json()
    
    # Step 2: Iterate through the seasons
    for season in series_data['seasons']:
        season_number = season['season_number']
        
        # Step 3: Fetch season details
        season_url = f"https://api.themoviedb.org/3/tv/{id}/season/{season_number}?api_key={tmdb_key}"
        season_response = requests.get(season_url)
        season_data = season_response.json()
        
        # Step 4: Iterate through the episodes
        for episode in season_data['episodes']:
            if episode['episode_number'] == episode_number:
                # Step 5: Return the season number
                return season_number
    
    return None  # If not found

def movie_folder_name(filename):
  # Regex pattern to match year in various formats (brackets or not)
  year_pattern = r"\[?\(?(\d{4})\]?\)?"

  # Split the filename based on year pattern
  parts = re.split(year_pattern, filename, maxsplit=1)

  if len(parts) < 2:
    # Year not found
    return None

  # Remove dots (".") that might be used instead of spaces
  movie_name = parts[0].replace(".", " ")

  # Extract year from the second part
  year_match = re.search(year_pattern, parts[1])
  if year_match:
    year = year_match.group(1)
  else:
    # Year not found in second part, might be incomplete filename
    return None

  # Combine movie name and year in desired format
  return f"{movie_name}({year})"

def series_id(name):
    name = name.replace(' ', '+')
    url = f'https://api.themoviedb.org/3/search/tv?api_key={tmdb_key}&query={name}'
    response = requests.get(url).json()
    series_id = None
    for i in range((len(response['results'])/2)):
        if response['results'][i]['original_language'] == 'ja':
            series_id = response['results'][i]['id']
            return series_id
    if series_id == None:
        for i in range(len(response['results'])):
            series_id = response['results'][i]['id']
            return series_id