import pytest
from backend.app.history import query_history
from backend.app.config import HISTORY

@pytest.mark.skipif(not HISTORY.is_file(),reason='原始五天历史库不可用')
def test_real_history_time_normalization():
    result=query_history(cow=1,start='2023-07-21',end='2023-07-21',start_time='00:00',end_time='24:00')
    row=result['daily_summaries'][0]
    assert row['observable_feeding_seconds']==4806
    assert row['observable_seconds']+row['unknown_seconds']+row['pending_seconds']==row['expected_seconds']
    assert result['reviewed'] is False
    with pytest.raises(ValueError):query_history(start_time='bad')
