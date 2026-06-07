### resumen cluster

- leader esperado: lnx200nas: lnx200nas, lnx202pc: lnx200nas, lnx203hp: ?

- nodo          health    state          t_state     pres     wdog  busy   stage                       prog    p_age  stall   local_size  local_events    created  executing  completed  dirty  
- lnx200nas     ok        ACTIVE            1.8m       0s       1s  Y      -                              -        -  N                0           448        448          0          0  -      
- lnx202pc      ok        STAND-BY          1.7m       0s       0s  Y      -                              -        -  N                0          2464       2464          0          0  -      
- lnx203hp      stale     STAND-BY         10.8m     3.3m     3.3m  Y      -                              -        -  N                0             0          0          0          0  -      

### events de lnx200nas:

- lnx200nas         events.local.000.jsonl          301784      2026-06-07T15:44:22.377217923+
- lnx200nas         events.lnx200nas.000.jsonl      299543      2026-06-07T15:44:21.539907324+
- lnx202pc          events.lnx200nas.000.jsonl      301784      2026-06-07T15:44:22.895101487+
- lnx203hp          events.lnx200nas.000.jsonl      1439441     2026-06-07T15:41:01.227480417+

### events de lnx202pc:

- lnx202pc          events.local.000.jsonl          1958548     2026-06-07T13:09:15.582610545+
- lnx200nas         events.lnx202pc.000.jsonl       1958548     2026-06-07T13:09:16.071386735+
- lnx200nas         events.lnx202pc.000.jsonl       1958548     2026-06-07T13:09:16.071386735+
- lnx203hp          events.lnx202pc.000.jsonl       1958548     2026-06-07T13:09:16.157989650+

### events de lnx203hp:

- lnx203hp          events.local.000.jsonl          40809       2026-06-07T13:08:48.880815773+
- lnx200nas         events.lnx203hp.000.jsonl       40809       2026-06-07T13:08:48.960021159+
- lnx200nas         events.lnx203hp.000.jsonl       40809       2026-06-07T13:08:48.960021159+
- lnx202pc          events.lnx203hp.000.jsonl       40809       2026-06-07T13:08:49.000379692+

### log de lnx200nas:

- lnx200nas         event_log.local.000.jsonl       354155      2026-06-07T15:44:22.373217806+
- lnx200nas         event_log.lnx200nas.000.jsonl   351914      2026-06-07T15:44:21.335696721+
- lnx202pc          event_log.lnx200nas.000.jsonl   354155      2026-06-07T15:44:22.787599517+
- lnx203hp          event_log.lnx200nas.000.jsonl   1583076     2026-06-07T15:41:00.599475362+

### log de lnx202pc:

- lnx202pc          event_log.local.000.jsonl       1976504     2026-06-07T13:09:13.764594790+
- lnx200nas         event_log.lnx202pc.000.jsonl    1976504     2026-06-07T13:09:15.446378049+
- lnx200nas         event_log.lnx202pc.000.jsonl    1976504     2026-06-07T13:09:15.446378049+
- lnx203hp          event_log.lnx202pc.000.jsonl    1976504     2026-06-07T13:09:15.533987047+

### log de lnx203hp:

- lnx203hp          event_log.local.000.jsonl       40809       2026-06-07T13:08:48.644874872+
- lnx200nas         event_log.lnx203hp.000.jsonl    40809       2026-06-07T13:08:48.824701499+
- lnx200nas         event_log.lnx203hp.000.jsonl    40809       2026-06-07T13:08:48.824701499+
- lnx202pc          event_log.lnx203hp.000.jsonl    40809       2026-06-07T13:08:48.870396885+
