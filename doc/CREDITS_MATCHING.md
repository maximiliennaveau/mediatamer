# Credits-Based Episode Matching

## Overview
A comprehensive system for identifying TV episodes from DVD rips by extracting and comparing credits information.

## Why Credits Matching?

### The Problem
When DVDs are ripped with MakeMKV:
- Episode titles are lost (they were in the DVD menu, not the video metadata)
- Files are named generically (`title_01.mkv`, `B1_t00.mkv`)
- Traditional filename-based matching fails

### The Solution
Episode credits contain unique, identifiable information:
- **Episode titles** appear in opening/closing credits
- **Writers** differ between episodes
- **Directors** differ between episodes
- **Guest stars** are episode-specific

## Implementation

### 1. Credits Extraction

**Function**: `extract_credits_text(path, opening_duration=180, closing_duration=180)`

**Strategy**:
- Extract frames from **opening** (0-3 minutes)
- Extract frames from **closing** (last 3 minutes)
- Use OCR (tesseract) to convert frames to text

**Why This Works**:
- Episode titles typically appear in opening or closing credits
- Much faster than scanning entire 45-minute episode
- Credits use large, clear text that OCR handles well

**Technical Details**:
```python
# Frame extraction rate: 0.2 fps (1 frame every 5 seconds)
# Opening: 180 seconds = ~36 frames
# Closing: 180 seconds = ~36 frames
# Total: ~72 frames per episode
```

### 2. TMDB Credits API

**Endpoints**:
```
GET /tv/{show_id}/season/{season}/episode/{ep}/credits
```

**Data Retrieved**:
- `crew[]`: Array of crew members
  - `name`: Person's name
  - `job`: Role (Writer, Director, Executive Producer, etc.)
- `guest_stars[]`: Array of guest cast
  - `name`: Actor's name
  - `character`: Character name

**Coverage**:
- Regular seasons (Season 1-N)
- Season 0 (Specials/Extras)

### 3. Matching Logic

#### Title Matching
```python
if episode_title.lower() in credits_text.lower():
    score += 150  # Very strong signal
```

#### Crew Matching
```python
for crew_member in episode['crew']:
    if crew_member['job'] in ('Writer', 'Director', 'Executive Producer'):
        if crew_member['name'].lower() in credits_text.lower():
            score += 60  # Per crew member match
```

#### Cast Matching
```python
for actor in episode['guest_stars'][:5]:  # Top 5
    if actor['name'].lower() in credits_text.lower():
        score += 60  # Per cast member match
```

## Scoring System

| Match Type | Points | Rationale |
|------------|--------|-----------|
| Title in Credits | 150 | Episode title is unique and definitive |
| Crew Member | 60 each | Writers/directors are episode-specific |
| Guest Star | 60 each | Guest cast varies by episode |
| Title Token Overlap | up to 80 | Partial title matches (e.g., "Zygon" matches both "Zygon Invasion" and "Zygon Inversion") |

## Example: Doctor Who Season 9

### Episode 7: "The Zygon Invasion"
- **Writer**: Peter Harness
- **Director**: Daniel Nettheim
- **Guest Stars**: Jemma Redgrave, Ingrid Oliver

### Episode 8: "The Zygon Inversion"
- **Writer**: Peter Harness & Steven Moffat
- **Director**: Daniel Nettheim
- **Guest Stars**: Jemma Redgrave, Ingrid Oliver

### Episode 9: "Sleep No More"
- **Writer**: Mark Gatiss
- **Director**: Justin Molotnikov
- **Guest Stars**: Reece Shearsmith, Elaine Tan

**Distinguishing Power**:
- If OCR finds "Mark Gatiss" → Strong signal for Episode 9
- If OCR finds "Steven Moffat" → Strong signal for Episode 8
- If OCR finds "Peter Harness" alone → Could be E7 or E8 (need other signals)

## Performance Considerations

### OCR Processing Time
- **Per Episode**: ~30-60 seconds (depends on hardware)
- **8 Episodes**: ~4-8 minutes total
- **Bottleneck**: Tesseract OCR, not frame extraction

### Optimization Strategies
1. **Parallel Processing**: Process multiple files concurrently
2. **Caching**: Cache TMDB crew data to avoid repeated API calls
3. **Frame Rate Tuning**: Adjust fps (currently 0.2) based on accuracy needs
4. **Early Exit**: Stop OCR if high-confidence match found early

### API Call Optimization
- **Current**: 1 API call per episode for credits (N calls per season)
- **Improvement**: Batch requests or cache season data
- **Rate Limiting**: TMDB allows 40 requests/10 seconds

## Accuracy Improvements

### Before Credits Matching
- Relied on: Filename patterns, duration, subtitle text
- **Problem**: Generic filenames (`t00`, `t01`) provided weak signals
- **Result**: Mismatches between consecutive episodes

### After Credits Matching
- Added: Episode titles in credits, crew/cast matching
- **Benefit**: Episode-specific signals (writers, directors)
- **Result**: Much stronger differentiation between episodes

## Code Locations

- **Credits Extraction**: [`extract_subtitle.py:171-286`](file:///data/videos/mediatamer/mediatamer/extract_subtitle.py#L171-L286)
- **TMDB Credits Fetch**: [`matcher.py:139-175`](file:///data/videos/mediatamer/mediatamer/matcher.py#L139-L175)
- **Crew Matching Logic**: [`matcher.py:273-298`](file:///data/videos/mediatamer/mediatamer/matcher.py#L273-L298)
- **Credits Title Matching**: [`matcher.py:248-270`](file:///data/videos/mediatamer/mediatamer/matcher.py#L248-L270)

## Future Enhancements

1. **Named Entity Recognition**: Use NLP to better extract names from OCR text
2. **Character Matching**: Compare character names (from TMDB) with credits
3. **Production Company**: Match production companies for additional signal
4. **Music Credits**: Composer information for theme music
5. **Multi-Language**: Support for non-English credits
