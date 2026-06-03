### resumen cluster

- leader esperado: lnx200nas: lnx200nas, lnx202pc: lnx202pc, lnx203hp: ?

- nodo          health    state          t_state     pres     wdog  busy   stage                       prog    p_age  stall   local_size  local_events    created  executing  completed  dirty  
- lnx200nas     ok        ACTIVE            2.4h       0s       1s  Y      -                              -        -  N                0          2038       2038          0          0  -      
- lnx202pc      ok        ACTIVE             15s       2s       2s  Y      -                              -        -  N                0          2477       2477          0          0  -      
- lnx203hp      stale     STAND-BY          2.3h     2.3h     2.3h  Y      -                              -        -  N                0             0          0          0          0  -      

### events de lnx200nas:

- lnx200nas         events.local.000.jsonl          1369475     2026-06-02T15:54:17.818690652+
- lnx200nas         events.lnx200nas.000.jsonl      1369475     2026-06-02T15:54:17.713909380+
- lnx202pc          events.lnx200nas.000.jsonl      1369475     2026-06-02T15:54:18.195526845+
- lnx203hp          events.lnx200nas.000.jsonl      910110      2026-06-02T13:36:46.186795794+

### events de lnx202pc:

- lnx202pc          events.local.000.jsonl          1873995     2026-06-02T15:54:16.940514141+
- lnx200nas         events.lnx202pc.000.jsonl       1873995     2026-06-02T15:54:17.447138003+
- lnx200nas         events.lnx202pc.000.jsonl       1873995     2026-06-02T15:54:17.447138003+
- lnx203hp          events.lnx202pc.000.jsonl       1704703     2026-06-02T13:36:44.241782711+

### events de lnx203hp:

- lnx203hp          events.local.000.jsonl          1817338     2026-06-02T13:36:46.292796507+
- lnx200nas         events.lnx203hp.000.jsonl       1817338     2026-06-02T13:36:46.807303940+
- lnx200nas         events.lnx203hp.000.jsonl       1817338     2026-06-02T13:36:46.807303940+
- lnx202pc          events.lnx203hp.000.jsonl       1817338     2026-06-02T13:36:47.136353090+

### log de lnx200nas:

- lnx200nas         event_log.local.000.jsonl       1582200     2026-06-02T14:30:46.814568263+
- lnx200nas         event_log.lnx200nas.000.jsonl   1582200     2026-06-02T15:54:16.906126212+
- lnx202pc          event_log.lnx200nas.000.jsonl   1582200     2026-06-02T15:54:17.675521581+
- lnx203hp          event_log.lnx200nas.000.jsonl   1049737     2026-06-02T13:36:45.196789135+

### log de lnx202pc:

- lnx202pc          event_log.local.000.jsonl       1948146     2026-06-02T14:11:04.463361253+
- lnx200nas         event_log.lnx202pc.000.jsonl    1948146     2026-06-02T15:54:16.883125711+
- lnx200nas         event_log.lnx202pc.000.jsonl    1948146     2026-06-02T15:54:16.883125711+
- lnx203hp          event_log.lnx202pc.000.jsonl    1762173     2026-06-02T13:36:43.505777760+

### log de lnx203hp:

- lnx203hp          event_log.local.000.jsonl       1836439     2026-06-02T13:36:44.751786141+
- lnx200nas         event_log.lnx203hp.000.jsonl    1836439     2026-06-02T13:36:45.712280256+
- lnx200nas         event_log.lnx203hp.000.jsonl    1836439     2026-06-02T13:36:45.712280256+
- lnx202pc          event_log.lnx203hp.000.jsonl    1836439     2026-06-02T13:36:46.016341695+
