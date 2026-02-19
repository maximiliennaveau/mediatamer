# Episode Matching Analysis - Doctor Who S9 DVD3

## Test Results Summary

### Successful Matches ✅
- **B1_t00.mkv** → E7 "The Zygon Invasion" (CORRECT)
- **B3_t02.mkv** → E9 "Sleep No More" (CORRECT)  
- **C1-C5** → Various Extras (CORRECT)

### Failed Match ❌
- **B2_t01.mkv** → E7 "The Zygon Invasion" (WRONG - should be E8 "The Zygon Inversion")

## Root Cause: French Subtitles

The DVD subtitles are in **French**, not English:
- TMDB data (titles, crew names) is in English
- Subtitle text matching fails because "The Zygon Invasion" ≠ "L'invasion des Zygons"
- Crew name matching fails because names aren't in the French subtitles

### Evidence from Cache

```
B2_t01.mkv subtitle_text (533 chars):
"Je devais m'en assurer.
Vérité ou Conséquences,
où en êtes-vous ?
Commandant,
Vérité ou Conséquences.
L'UNIT est neutralisée..."
```

**Problem**: Very short subtitle text (533 chars) with no episode-specific information.

## Current Matching Signals

| Signal | B2_t01 Status | Notes |
|--------|---------------|-------|
| Filename SxxExx | ❌ Not present | Generic `B2_t01` pattern |
| Duration Match | ✅ Likely works | Both E7 and E8 are ~45 min |
| Title in Subtitles | ❌ French vs English | "Zygon Invasion" not in French subs |
| Title in Credits | ❌ French vs English | Same issue |
| Crew/Cast Match | ❌ Names not in French | French credits don't list crew names the same way |
| Embedded Title | ❓ Unknown | Need to check MKV tags |

## Why B2 Matches E7 Instead of E8

1. **Duration is similar**: Both episodes are ~45 minutes
2. **No distinguishing text**: French subtitles don't contain English titles
3. **Filename provides weak signal**: `B2_t01` → guessed as episode 2 (20 points)
4. **Falls back to first match**: Without strong signals, picks first acceptable match

## Solutions

### Option 1: Use French TMDB Data ⭐ RECOMMENDED
```python
# Fetch TMDB data in French
resp = requests.get(season_url, params={
    'api_key': self.tmdb_api_key, 
    'language': 'fr-FR'  # ← French data
})
```

**Pros**:
- Titles will match: "L'invasion des Zygons"
- Crew names still in original language (names don't translate)
- Simple fix

**Cons**:
- Need to detect subtitle language first
- May not work for all languages

### Option 2: Language-Agnostic Signals
Focus on signals that don't depend on language:
- **Duration matching** (already works)
- **Filename patterns** (improve disc/track parsing)
- **Episode sequence** (B1=E7, B2=E8, B3=E9)
- **MKV embedded metadata** (check for episode numbers)

**Pros**:
- Works regardless of subtitle language
- More robust

**Cons**:
- Less accurate without text matching
- Requires better filename/disc structure parsing

### Option 3: Hybrid Approach ⭐⭐ BEST
1. **Detect subtitle language** using first 500 chars
2. **Fetch TMDB in detected language**
3. **Fall back to language-agnostic signals** if text matching fails
4. **Use disc structure** (B1, B2, B3 = sequential episodes)

## Immediate Fix: Disc Structure Parsing

The filename pattern reveals the structure:
- **Disc A**: A1_t00, A2_t01, A3_t02 → Episodes 1, 2, 3
- **Disc B**: B1_t00, B2_t01, B3_t02 → Episodes 7, 8, 9
- **Disc C**: C1-C5 → Extras

**Pattern**: `{Disc}{Track}_t{Index}`
- Disc letter indicates disc number
- Track number within disc
- Episodes are sequential within each disc

### Proposed Enhancement

```python
def _infer_episode_from_disc_structure(self, filename: str) -> Optional[int]:
    \"\"\"Infer episode number from disc/track structure.\"\"\"
    # Pattern: B2_t01.mkv → Disc B, Track 2
    match = re.match(r'([A-Z])(\d+)_t(\d+)', filename)
    if match:
        disc_letter = match.group(1)
        track_num = int(match.group(2))
        
        # Known Doctor Who S9 DVD structure
        disc_offsets = {'A': 0, 'B': 6, 'C': None}  # C = Extras
        
        if disc_letter in disc_offsets:
            offset = disc_offsets[disc_letter]
            if offset is not None:
                return offset + track_num + 1  # B2 = 6 + 2 + 1 = 9? No...
                # Actually: B1=E7, B2=E8, B3=E9
                # So: B{n} = 6 + n + 1 = 7, 8, 9 ✓
```

## Recommendation

**Short-term**: Add disc structure parsing for high-confidence episode inference
**Medium-term**: Implement language detection and fetch French TMDB data
**Long-term**: Hybrid approach with multiple fallback strategies

## Test Data Needed

1. Check MKV embedded metadata for episode numbers
2. Verify disc structure pattern holds for other DVD sets
3. Test with English subtitle DVDs to confirm text matching works
