# MediaTamer - Robust Metadata Extraction

## Project Goal
Achieve "100% success" in identifying and organizing TV show episodes ripped from DVDs for Jellyfin by using content-based signals (OCR, duration, credits matching) rather than relying on filename patterns.

## Current Status: Credits-Based Matching Implementation

### ✅ Completed Features

#### 1. Core API Refactoring
- **Module**: Renamed `get_dvd_metadata.py` → `get_tv_shows_metadata.py`
- **API Function**: `get_tv_shows_metadata(path, api_key, language, recursive)` returns structured metadata
- **CLI**: Updated with `tv-metadata` command (alias: `dvd-metadata`)
- **Matcher**: Refactored `EpisodeMatcher` to accept single file path and perform self-contained matching

#### 2. Signal Implementation

##### Filename Parsing (`signals/filename.py`)
- Explicit vs. guessed episode detection
- `SxxExx` patterns (high confidence: 80 points)
- Generic `tXX` patterns (low confidence: 20 points)
- Directory-based show/season inference

##### Technical Metadata (`signals/technical.py`)
- Duration extraction for runtime matching (50 points if within 45s)
- MKV header tags extraction (embedded titles: 100 points)

##### Subtitle Extraction (`extract_subtitle.py`)
- **Text Subtitles**: Direct SRT extraction
- **PGS/DVD Subtitles**: OCR with tesseract (10-minute scan)
- **Credits Extraction**: NEW - Targeted OCR of opening (0-3 min) and closing (last 3 min)
  - Much faster than full subtitle scan
  - Episode titles typically appear in credits
  - 150 points for exact title match in credits

##### Cast/Crew Matching (NEW)
- **TMDB Integration**: Fetches crew (writers, directors) and guest stars for each episode
- **OCR Comparison**: Matches names found in credits text with TMDB data
- **Scoring**: 60 points per crew/cast member match
- **Uniqueness**: Different episodes have different writers/directors, making this a very strong signal

#### 3. Matching Logic (`matcher.py`)

**Multi-Signal Scoring System**:
| Signal | Points | Confidence |
|--------|--------|------------|
| Crew/Cast Match | 60 per match | Very High |
| Title in Credits | 150 | Very High |
| Embedded Title (MKV tags) | 100 | High |
| Title in Subtitles | 100 | High |
| Filename SxxExx (explicit) | 80 | High |
| Duration Match (<45s diff) | 50 | Medium |
| Credits Title Token Overlap | up to 80 | Medium |
| Subtitle Title Token Overlap | up to 60 | Medium |
| Filename tXX (guessed) | 20 | Low |

**Threshold**: 40 points minimum for match acceptance

**Extras Detection**:
- Files starting with 'C' tagged as "Extras"
- TMDB lookup includes Season 0 (Specials)
- Fallback to base show name if "Extras" suffix search fails

#### 4. Pipeline Transparency
- Detailed console output showing which signals contributed to each match
- Example:
  ```
  [MATCH] B1_t00.mkv -> Doctor Who S9E7 (The Zygon Invasion)
      - Duration match (30s diff)
      - Title words in credits overlap 1.00
      - Crew/cast match: Peter Harness (Writer)
  ```

### 🔄 In Progress

- **Testing**: Full Doctor Who S9 DVD3 integration test (OCR is slow but working)
- **Performance**: OCR processing time optimization

### 📋 Next Steps

1. **Complete Integration Testing**
   - Verify accuracy on all 8 files in Doctor Who S9 DVD3
   - Test extras/specials matching
   
2. **Performance Optimization**
   - Consider caching TMDB crew data
   - Optimize OCR frame extraction rate
   - Add progress indicators for long-running OCR

3. **Additional Enhancements**
   - Add crew matching to pipeline transparency prints
   - Implement `apply-metadata` command for batch renaming
   - Consider subtitle hash matching for additional signal

## Architecture

```
mediatamer/
├── cli.py                      # CLI entry point
├── get_tv_shows_metadata.py    # Main API (returns dict of metadata)
├── matcher.py                  # EpisodeMatcher class (multi-signal scoring)
├── extract_subtitle.py         # Subtitle/credits OCR extraction
├── metadata.py                 # ffprobe wrapper
├── signals/
│   ├── filename.py            # Filename pattern parsing
│   ├── technical.py           # Duration, tags extraction
│   └── subtitle_hash.py       # OpenSubtitles hash (stub)
└── organize.py                # File organization utilities
```

## Dependencies

- **ffmpeg/ffprobe**: Video processing and metadata extraction
- **tesseract**: OCR for PGS/DVD subtitles and credits
- **pytesseract**: Python wrapper for tesseract
- **Pillow**: Image processing for OCR
- **requests**: TMDB API calls

## TMDB API Usage

**Endpoints Used**:
- `/search/tv` - Find show by name
- `/tv/{show_id}/season/{season}` - Get season episodes
- `/tv/{show_id}/season/{season}/episode/{ep}/credits` - Get crew/cast data
- `/tv/episode_group/{group_id}` - Doctor Who Blu-ray order (special case)

**Rate Limiting**: Consider implementing caching to reduce API calls

## Testing

- **Unit Tests**: `tests/unit/` (currently skipped for development speed)
- **Integration Test**: `tests/unit/test_get_tv_shows_metadata.py` (real API calls)
- **Build**: `nix build . -L` (currently disabled checks for faster iteration)

## Known Issues

1. **OCR Performance**: Processing 8 files takes several minutes
2. **Unit Test Mocking**: Needs update for new crew/credits API calls
3. **B2_t01 Conflict**: Matching E7 instead of E8 (needs investigation)
