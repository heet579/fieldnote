# Demonstration incident: failed load and recovery

**Classification:** deliberately injected local test, not an actual service incident.

**Trigger:** the failure fixture contains two revised existing observations. The loader is instructed to raise an exception immediately after processing its first accepted row.

**Expected risk:** without transaction control, only one correction might become visible, leaving a partially updated dataset.

**Observed behaviour:** the data transaction rolled back. The before/after comparison showed identical fact rows; staging changes from that run did not persist. The separately committed audit row retained `failed` status and an injected-failure message. The raw input remained archived by content hash. Counts on the failed audit represented zero committed work.

**Recovery:** rerun the same failure fixture without the injection switch. Both revisions were applied in one successful transaction. The full demonstration receipt records two updates and no new observations.

**Further exercise:** a CSV containing an unexpected `reading` column was rejected before row processing. The failed audit was preserved without changing facts.

**Verification:** `tests/test_warehouse.py` checks rollback and recovery. `portfolio/evidence.json` records the full demo's outcome; `portfolio/dashboard.html` exposes the corresponding audit runs.

**Remaining limitation:** a forced process kill can leave a run marked `running`. This demonstration tests handled exceptions, not host power loss or every database failure mode.
