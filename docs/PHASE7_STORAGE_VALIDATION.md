# Phase 7 storage validation

**Actual backup/recovery PASSED; retention/capacity remains PARTIAL (P5-02).** Measurements use the Phase7 test database, including the first failed full stress attempt, supplementary streams and subsequent periodic idle assessments. They are not 90-day endurance or representative production sizing.

| Consistent snapshot | Observation rows | Total public table rows | Database bytes | Compressed dump bytes | Dump / restore seconds |
|---|---:|---:|---:|---:|---|
| Before raw archival | 3434 | 66386 | 131561139 | 8863591 | 2.74 / 6.39 |
| After archival and overnight idle history | 5648 | 295323 | 617264819 | 44705176 | 6.30 / 45.59 |

Both actual PostgreSQL custom-format `pg_dump` operations used an exported repeatable-read snapshot. Each restored into a new database; ordered canonical row checksums and counts match for **every public table**. Sixty recovered CAS artifact files match content-address hashes. The post-archive recovery independently copied and verified all **5120 raw archived messages**, including source digest and row identity. Dumps, CAS archives, raw archive objects, table/relation/index measurements and repeated API query times are in `phase7/storage_recovery.json`, `phase7/archive_recovery.json` and their raw output directories. Source databases were not replaced.

Optional bounded external archival moves only completed inbox rows: **5120 rows**, **7044508 bytes** → **546593 compressed bytes**. Durable content-hash objects are fsynced before the SQL deletion transaction commits. SQL keeps duplicate identity/digest, source, received time and archive row pointer. Pending jobs, scientific observations, evidence, events, provenance and explanations remain. Recovered samples replay as duplicates, and no pre-existing scientific row was deleted. Unit tests reject corrupted archives and protect unresolved work. The actual days=0 policy is an explicit accelerated lab test, not a claim of 90-day operation. Deployments must back up the archive directory together with SQL.

**Archiving raw inbox payloads does not solve F1 trace growth.** The second snapshot has 213592 trace rows with 984449313 logical JSON bytes; PostgreSQL TOAST/storage allocation means logical JSON size differs from physical database size. Ordinary vacuum/archival does not guarantee file shrinkage. No blocking `VACUUM FULL` or destructive history pruning was performed during stress. Periodic idle fusion also appends history; completed test workers were stopped after evidence capture to prevent continued test-only growth.

The observed mixed/idle snapshot interval was 13.14 hours and grew by 485703680 physical bytes: about **35.2 MiB/hour**. Holding that particular rate fixed projects **74.4 GiB/90 days**, before artifacts, replicas, indexes beyond this history mix, free space, backups or uncertainty. This is a rate extrapolation, not an endurance result or a bound for continuous active streams. Active throughput can produce much larger evidence/trace rates. Capacity approval requires a representative workload, long-horizon trace/event policy and measured storage headroom; the prior Phase5 projection is preserved as historical evidence.

Reproduce `scripts/phase7_archive_validate.py` and `scripts/phase7_storage_validate.py --output <new-output> --restore-name phase7_restore_<new> --archive-root <archive-store>`. The latter verifies all archived row identities after restore. Do not point restoration at the source database.



After all restore equality and dump hashes passed, the two disposable restore-target databases were removed to reclaim test storage. Source databases, SQL dumps, CAS archives, raw archives and recorded equality evidence remain. See `phase7/restore_fixture_cleanup.json`. Raw archival preserves parsed inbox envelope content and original wire digest; it is not a packet capture of arbitrary original JSON formatting.
