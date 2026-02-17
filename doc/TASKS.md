# MediaTamer Development Tasks

## ✅ Phase 1: Core Refactoring (COMPLETE)
- [x] Rename `get_dvd_metadata.py` → `get_tv_shows_metadata.py`
- [x] Implement `get_tv_shows_metadata()` API function
- [x] Refactor `EpisodeMatcher` to single-file lookup
- [x] Update `cli.py` with `tv-metadata` command
- [x] Add `tv-metadata` alias to CLI

## ✅ Phase 2: Signal Implementation (COMPLETE)
- [x] Implement filename parsing with explicit/guessed detection
- [x] Extract technical metadata (duration, MKV tags)
- [x] Implement PGS/DVD subtitle OCR
- [x] Add tesseract to `flake.nix`
- [x] Parameterize OCR scan duration

## ✅ Phase 3: Credits Matching (COMPLETE)
- [x] Implement `extract_credits_text()` for targeted OCR
- [x] Integrate credits matching into `EpisodeMatcher`
- [x] Fetch crew data from TMDB API (writers, directors)
- [x] Fetch guest stars from TMDB API
- [x] Implement crew/cast name comparison
- [x] Add scoring for crew/cast matches (60 points each)

## ✅ Phase 4: Extras and Specials (COMPLETE)
- [x] Implement Season 0 (Specials) fallback in TMDB lookup
- [x] Add "Extras" suffix handling (files starting with 'C')
- [x] Strip TMDB title suffixes like "(1)" for clean output
- [x] Improve show name normalization

## 🔄 Phase 5: Testing and Verification (IN PROGRESS)
- [x] Basic unit tests passing
- [x] Integration test framework created
- [ ] Complete Doctor Who S9 DVD3 integration test
- [ ] Investigate B2_t01 mismatch (matching E7 instead of E8)
- [ ] Update unit test mocks for crew API calls
- [ ] Re-enable build checks in `flake.nix`

## 📋 Phase 6: Performance and Polish (PLANNED)
- [ ] Optimize OCR performance (parallel processing?)
- [ ] Add progress indicators for long operations
- [ ] Cache TMDB crew data to reduce API calls
- [ ] Add crew matching to pipeline transparency prints
- [ ] Implement `apply-metadata` command for batch renaming
- [ ] Create review plan JSON format
- [ ] Add JSON output mode for programmatic use

## 📋 Phase 7: Additional Enhancements (FUTURE)
- [ ] Subtitle hash matching (OpenSubtitles API)
- [ ] Multi-language support for credits
- [ ] Named Entity Recognition for better name extraction
- [ ] Character name matching from TMDB
- [ ] Confidence thresholds configuration
- [ ] Web UI for review workflow

## Current Blockers
1. **OCR Performance**: Processing 8 files takes 4-8 minutes
2. **Unit Test Mocks**: Need update for new crew/credits API structure
3. **Integration Test**: Need to complete full run to verify accuracy

## Next Immediate Actions
1. Let integration test complete to see full results
2. Investigate why B2_t01 is matching E7 instead of E8
3. Update unit test mocks for crew API
4. Consider OCR optimization strategies
