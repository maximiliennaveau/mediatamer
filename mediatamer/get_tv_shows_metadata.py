#!/usr/bin/env python3
"""Extract TV show metadata from video files using robust matching."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import argcomplete

from mediatamer.metadata import extract_metadata
from mediatamer.parameters import get_extensions
from mediatamer.matcher import EpisodeMatcher


def get_tv_shows_metadata(path: Path, api_key: str, language: str = 'fr-FR', recursive: bool = False) -> Dict[str, Any]:
    """
    Analyze a video file or directory and return metadata plan.
    
    Args:
        path: File or Directory to analyze.
        api_key: TMDB API Key.
        language: Language for metadata (default fr-FR).
        recursive: If True and path is dir, scan recursively (not fully implemented in logic below but reserved).

    Returns:
        Dict containing processing results, candidates, and recommended actions.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path {path} does not exist")

    # 1. Identify Files
    files = []
    if path.is_file():
        files = [path]
        root_context = path.parent
    else:
        exts = {e if e.startswith('.') else f".{e}" for e in get_extensions()}
        if recursive:
            files = sorted([p for p in path.rglob("*") if p.suffix.lower() in exts and p.is_file()])
        else:
            files = sorted([p for p in path.glob("*") if p.suffix.lower() in exts and p.is_file()])
        root_context = path

    results = {
        'source': str(path),
        'files': [],
        'review_needed': False,
        'summary': {'analyzed': len(files), 'matched': 0, 'conflicts': 0}
    }
    
    assigned_episodes = {} # (show, season, episode) -> filename

    print(f"Analyzing {len(files)} files in {root_context}...")

    # Shared cache for show/season lookups could implemented here or inside Matcher if we wanted 
    # persistence across files, but currently Matcher is instantiated per file.
    
    for f in files:
        matcher = EpisodeMatcher(f, api_key)
        matcher.find_metadata()
        
        entry = {
            'file': f.name,
            'path': str(f),
            'show_detected': matcher.show_name,
            'season_detected': matcher.season_number,
            'episode_detected': matcher.episode_number,
            'candidates': [],
            'selected_episode': None,
            'status': 'NO_MATCH'
        }

        # Populate candidates info for review
        if matcher.candidates:
            import re
            for c in matcher.candidates[:3]:
                 raw_name = c['episode'].get('name') or ""
                 # Normalize: "Title (1)" -> "Title"
                 clean_name = re.sub(r'\s*\(\d+\)$', '', raw_name)
                 
                 entry['candidates'].append({
                    'episode_number': c['episode'].get('episode_number'),
                    'name': clean_name,
                    'score': c['score'],
                    'reasons': c['reasons'],
                    'tmdb_id': c['episode'].get('id'),
                    'overview': c['episode'].get('overview'),
                    'air_date': c['episode'].get('air_date'),
                 })

        # Logic for Selection & Status
        best = matcher.best_candidate
        if best:
            ep_num = best['episode'].get('episode_number')
            season = matcher.season_number
            show = matcher.show_name
            
            entry['selected_episode'] = entry['candidates'][0] # Best is always first if best_candidate is set
            
            # Conflict Check
            key = (show, season, ep_num)
            if key in assigned_episodes:
                entry['status'] = 'CONFLICT'
                entry['conflict_with'] = assigned_episodes[key]
                results['review_needed'] = True
                results['summary']['conflicts'] += 1
            else:
                entry['status'] = 'MATCH'
                assigned_episodes[key] = f.name
                results['summary']['matched'] += 1
                
        else:
            # No high confidence match
            results['review_needed'] = True
            if matcher.candidates:
                 entry['status'] = 'LOW_CONFIDENCE'
            else:
                 entry['status'] = 'NO_MATCH'

        results['files'].append(entry)
        
        best_name = "?"
        if entry['selected_episode']:
            best_name = entry['selected_episode']['name']
            
        print(f"  [{entry['status']}] {f.name} -> {matcher.show_name} S{matcher.season_number}E{matcher.episode_number if matcher.episode_number else '?'} ({best_name})")
        
        # Pipeline prints: Show what algorithm found what
        if matcher.best_candidate:
            for reason in matcher.best_candidate.get('reasons', []):
                print(f"      - {reason}")
        elif matcher.candidates:
            # Show best candidate's reasons even if low confidence
            top = matcher.candidates[0]
            # Normalize top name too if needed for print
            top_name = re.sub(r'\s*\(\d+\)$', '', top['episode'].get('name') or "?")
            print(f"      - Best candidate ({top_name}) reasons:")
            for reason in top.get('reasons', []):
                print(f"          - {reason}")

    return results

def get_argument_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--input-path", '-i', required=True, type=Path, help="Input file or directory")
    parser.add_argument("--tmdb-api-key", type=str, required=True, help="TMDB API Key")
    parser.add_argument("--language", type=str, default='fr-FR', help="Language for metadata")
    parser.add_argument("--dry-run", action="store_true", help="Do not write metadata files, only review plan (Defacto default if review needed)")
    # parser.add_argument("--output", ...) # Could add output dir
    return parser

def main():
    parser = argparse.ArgumentParser(description="Extract TV Show metadata")
    parser = get_argument_parser(parser)
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # Call API
    try:
        data = get_tv_shows_metadata(args.input_path, args.tmdb_api_key, args.language)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Output Logic
    output_dir = Path("/data/videos/metadata")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    review_needed = data['review_needed'] or args.dry_run
    
    if review_needed:
        review_file = output_dir / "review_plan.json"
        with open(review_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("\n" + "="*60)
        print(f"REVIEW REQUIRED. Plan written to {review_file}")
        print("Inspect the file, manually adjust 'selected_episode' if needed.")
    else:
        print("\nAll matches high confidence. Writing metadata...")
        for item in data['files']:
            if item['status'] == 'MATCH' and item['selected_episode']:
                # Construct final metadata
                # We need technical metadata too. 
                # Ideally, extract_metadata should support passing existing data to avoid re-probing?
                # For now, simplistic re-extraction or we should have returned tech data from API.
                
                # Fetch full metadata merging with what we found
                sel = item['selected_episode']
                
                # Simple tech extract
                try:
                    vm = extract_metadata(Path(item['path']), None, None, args.language)
                except:
                    vm = {}

                meta_entry = {
                     'filename': item['file'],
                     'filepath': item['path'],
                     'show_name': item['show_detected'],
                     'season': item['season_detected'],
                     'episode_number': sel['episode_number'],
                     'episode_title': sel['name'],
                     'tmdb_episode_id': sel['tmdb_id'],
                     'overview': sel.get('overview'),
                     'air_date': sel.get('air_date'),
                     'duration': vm.get('duration'),
                     'size': vm.get('size'),
                     'video_codec': vm.get('video', {}).get('codec_name'),
                }
                
                out_f = output_dir / f"{item['file']}.metadata.json"
                with open(out_f, 'w') as f:
                     json.dump(meta_entry, f, indent=2, ensure_ascii=False)
                print(f"Wrote {out_f.name}")

if __name__ == "__main__":
    main()
