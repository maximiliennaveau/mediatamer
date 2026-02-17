# Implementation Plan - Robust MediaTamer

## Goal
Achieve "100% success" in identifying and organizing TV show episodes ripped from DVDs for Jellyfin.

## Success Criteria
1. **Strong Signals**: OCR (credits), duration, crew/cast matching, subtitle text
2. **Robust Matching**: Multi-signal scoring system with configurable thresholds
3. **User Verification**: High-confidence auto-match, low-confidence review workflow

## Implementation Phases

### Phase 1: Core Refactoring ✅ COMPLETE

#### API-First Design
- [x] Rename `get_dvd_metadata.py` → `get_tv_shows_metadata.py`
- [x] Implement `get_tv_shows_metadata(path, api_key, language, recursive)` API
- [x] Refactor CLI `main()` to call API and handle output
- [x] Update `cli.py` with `tv-metadata` command

#### EpisodeMatcher Refactoring
- [x] Accept `file_path` and `tmdb_api_key` in constructor
- [x] Implement `find_metadata()` for self-contained matching
- [x] Infer show/season from directory structure
- [x] Fetch TMDB data internally

### Phase 2: Signal Implementation ✅ COMPLETE

#### Filename Parsing
- [x] Distinguish explicit (`SxxExx`) vs guessed (`tXX`) patterns
- [x] Extract show/season from parent directories
- [x] Confidence scoring based on pattern type

#### Technical Metadata
- [x] Duration extraction via ffprobe
- [x] MKV header tags extraction
- [x] Runtime comparison (±45s tolerance)

#### Subtitle Extraction
- [x] Direct SRT extraction for text subtitles
- [x] PGS/DVD subtitle OCR with tesseract
- [x] Configurable scan duration (default: 10 minutes)

### Phase 3: Credits-Based Matching ✅ COMPLETE

#### Credits Extraction
- [x] `extract_credits_text()` function
- [x] Targeted OCR: opening (0-3 min) + closing (last 3 min)
- [x] Frame rate: 0.2 fps (1 frame per 5 seconds)
- [x] Efficient alternative to full subtitle scan

#### TMDB Credits API Integration
- [x] Fetch crew data (writers, directors, producers)
- [x] Fetch guest stars (top 5 per episode)
- [x] Apply to both regular seasons and Season 0 (Specials)

#### Cast/Crew Matching
- [x] Compare OCR'd names with TMDB crew data
- [x] Scoring: 60 points per crew/cast match
- [x] Very strong signal (crew is episode-specific)

### Phase 4: Extras and Specials Robustness ✅ COMPLETE

#### TMDB Lookup Enhancements
- [x] Always fetch Season 0 (Specials) as fallback
- [x] Strip "- Extras" suffix for TMDB search
- [x] Preserve suffix in local metadata
- [x] Heuristic: files starting with 'C' are extras

#### Title Normalization
- [x] Strip trailing `(1)`, `(2)` from TMDB titles
- [x] Clean output for better user experience

### Phase 5: Testing and Verification 🔄 IN PROGRESS

#### Unit Tests
- [x] `test_matcher.py` - Basic matcher tests (currently skipped)
- [x] `test_signals_modules.py` - Filename parsing tests
- [x] `test_metadata.py` - Metadata extraction tests
- [ ] Update mocks for new crew/credits API calls

#### Integration Tests
- [x] `test_get_tv_shows_metadata.py` - Real API test
- [ ] Verify all 8 files in Doctor Who S9 DVD3
- [ ] Test extras/specials matching accuracy

#### Build Verification
- [x] `nix build . -L` (checks disabled for dev speed)
- [ ] Re-enable checks after testing complete

### Phase 6: Performance and Polish 📋 PLANNED

#### Performance Optimization
- [ ] Cache TMDB crew data to reduce API calls
- [ ] Optimize OCR frame extraction rate
- [ ] Add progress indicators for long OCR operations
- [ ] Consider parallel processing for multiple files

#### Pipeline Transparency
- [x] Print detailed matching reasons
- [ ] Add crew matching to output
- [ ] JSON output mode for programmatic use

#### User Workflow
- [ ] Implement `apply-metadata` command
- [ ] Review plan JSON format
- [ ] Batch renaming based on review plan

## Scoring System

| Signal | Points | Implementation |
|--------|--------|----------------|
| Crew/Cast Match | 60 each | `matcher.py` L271-298 |
| Title in Credits | 150 | `matcher.py` L248-270 |
| Embedded Title | 100 | `matcher.py` L217-226 |
| Title in Subtitles | 100 | `matcher.py` L228-247 |
| Filename SxxExx | 80 | `matcher.py` L195-203 |
| Duration Match | 50 | `matcher.py` L182-193 |
| Credits Token Overlap | up to 80 | `matcher.py` L260-270 |
| Subtitle Token Overlap | up to 60 | `matcher.py` L238-247 |
| Filename tXX | 20 | `matcher.py` L200-203 |

**Match Threshold**: 40 points minimum

## File Structure

```
mediatamer/
├── cli.py                      # CLI dispatcher
├── get_tv_shows_metadata.py    # Main API + CLI handler
├── matcher.py                  # EpisodeMatcher (scoring logic)
├── extract_subtitle.py         # OCR extraction
│   ├── extract_subtitle_text() # Full subtitle OCR
│   ├── extract_pgs_as_text()   # PGS/DVD OCR
│   └── extract_credits_text()  # Targeted credits OCR
├── metadata.py                 # ffprobe wrapper
├── signals/
│   ├── filename.py            # Pattern parsing
│   ├── technical.py           # Duration/tags
│   └── subtitle_hash.py       # OpenSubtitles hash (stub)
└── organize.py                # File organization
```

## Dependencies

- **ffmpeg/ffprobe**: Video processing
- **tesseract**: OCR engine
- **pytesseract**: Python OCR wrapper
- **Pillow**: Image processing
- **requests**: HTTP/TMDB API

## Known Issues

1. **OCR Performance**: Slow for multiple files (several minutes for 8 files)
2. **B2_t01 Mismatch**: Matching E7 instead of E8 (investigate crew data)
3. **Unit Test Mocks**: Need update for crew API calls

## Next Actions

1. Complete integration test run
2. Investigate B2_t01 mismatch
3. Optimize OCR performance
4. Update unit test mocks
5. Re-enable build checks
