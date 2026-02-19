import requests
from typing import List, Dict, Any, Optional

def lang_to_tmdb_locale(lang_code: Optional[str]) -> str:
    """Map an ISO 639-1 code to a TMDB locale string."""
    mapping = {
        'fr': 'fr-FR',
        'de': 'de-DE',
        'es': 'es-ES',
        'it': 'it-IT',
        'pt': 'pt-PT',
        'nl': 'nl-NL',
        'ja': 'ja-JP',
        'zh': 'zh-CN',
        'ko': 'ko-KR',
    }
    return mapping.get(lang_code or '', 'en-US')

def fetch_tmdb_episodes(show_name: str, season_number: int, api_key: str, locale: str = 'en-US') -> tuple[str, List[Dict[str, Any]]]:
    """
    Fetch episodes and detailed credits from TMDB for a given show and season.
    
    Returns:
        A tuple of (normalized_show_name, list_of_episodes).
    """
    episodes_result = []
    final_show_name = show_name
    
    try:
        # 1. Search for Show ID
        search_query = show_name
        is_extras = " - Extras" in search_query
        if is_extras:
            search_query = search_query.replace(" - Extras", "")

        search_url = f"https://api.themoviedb.org/3/search/tv"
        params = {'api_key': api_key, 'query': search_query, 'language': 'en-US'}
        resp = requests.get(search_url, params=params, timeout=10)
        if not resp.ok:
            return final_show_name, []
        
        results = resp.json().get('results', [])
        best_show = None
        
        for s in results:
            if s['name'].lower() == search_query.lower():
                best_show = s
                break
        
        if not best_show and is_extras:
            for s in results:
                if "extra" in s['name'].lower():
                    best_show = s
                    break

        if not best_show and results:
            best_show = results[0]
        
        if not best_show:
            return final_show_name, []
        
        show_id = best_show['id']
        tmdb_name = best_show['name']
        if is_extras and "extra" not in tmdb_name.lower():
             final_show_name = f"{tmdb_name} - Extras"
        else:
             final_show_name = tmdb_name

        # 2. Get Season Episodes
        def fetch_season(s_num):
            s_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{s_num}"
            r = requests.get(s_url, params={'api_key': api_key, 'language': locale})
            if r.ok:
                eps = r.json().get('episodes', [])
                for ep in eps:
                    ep_num = ep.get('episode_number')
                    if ep_num:
                        # Fetch credits (crew & cast)
                        c_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{s_num}/episode/{ep_num}/credits"
                        cr = requests.get(c_url, params={'api_key': api_key})
                        if cr.ok:
                            cr_data = cr.json()
                            ep['crew'] = cr_data.get('crew', [])
                            ep['guest_stars'] = cr_data.get('guest_stars', [])
                return eps
            return []

        episodes_result.extend(fetch_season(season_number))
        
        # If it's extras or no episodes found, also pull Specials (Season 0)
        if is_extras or not episodes_result:
            episodes_result.extend(fetch_season(0))

    except Exception as e:
        print(f"TMDB Fetch Error: {e}")

    return final_show_name, episodes_result
