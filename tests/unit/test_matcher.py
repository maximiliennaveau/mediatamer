import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from mediatamer.matcher import EpisodeMatcher

@pytest.fixture
def mock_episodes():
    return [
        {'id': 1, 'episode_number': 1, 'season_number': 9, 'name': 'The Magician\'s Apprentice', 'runtime': 45},
        {'id': 2, 'episode_number': 2, 'season_number': 9, 'name': 'The Witch\'s Familiar', 'runtime': 45},
        {'id': 3, 'episode_number': 3, 'season_number': 9, 'name': 'Under the Lake', 'runtime': 45},
    ]

@pytest.fixture
def matcher(mock_episodes):
    return EpisodeMatcher(mock_episodes)

@patch('mediatamer.matcher.get_technical_metadata')
@patch('mediatamer.matcher.parse_filename')
@patch('mediatamer.matcher.extract_subtitle_text')
@patch('mediatamer.matcher.extract_pgs_as_text')
def test_match_perfect_filename(mock_pgs, mock_sub, mock_parse, mock_tech, matcher):
    # Setup
    p = MagicMock(spec=Path)
    p.exists.return_value = True
    p.name = 'Doctor_Who_S9_E01.mkv'
    p.__str__.return_value = 'Doctor_Who_S9_E01.mkv'
    mock_tech.return_value = {'duration': 45 * 60} # Exact match
    mock_parse.return_value = {'season': 9, 'episode': 1}
    mock_sub.return_value = None
    
    # Act
    candidates = matcher.match_file(p)
    
    # Assert
    assert candidates
    best = candidates[0]
    assert best['episode']['episode_number'] == 1
    assert best['score'] > 100 # Baseline + Duration + Filename

@patch('mediatamer.matcher.get_technical_metadata')
@patch('mediatamer.matcher.parse_filename')
@patch('mediatamer.matcher.extract_subtitle_text')
@patch('mediatamer.matcher.extract_pgs_as_text')
def test_match_ocr_content(mock_pgs, mock_sub, mock_parse, mock_tech, matcher):
    # Setup
    p = MagicMock(spec=Path)
    p.exists.return_value = True
    p.name = 'Track01.mkv'
    p.__str__.return_value = 'Track01.mkv'
    mock_tech.return_value = {'duration': 45 * 60}
    mock_parse.return_value = {'season': None, 'episode': None}
    mock_sub.return_value = None
    mock_pgs.return_value = "SOMETHING SOMETHING THE WITCH'S FAMILIAR SOMETHING"
    
    # Act
    candidates = matcher.match_file(p)
    
    # Assert
    best = candidates[0]
    assert best['episode']['episode_number'] == 2
    assert "Title 'the witch's familiar' found in subtitles" in best['reasons'][0].lower() or \
           any("title" in r.lower() for r in best['reasons'])
