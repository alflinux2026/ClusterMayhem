### resumen cluster

- leader esperado: lnx200nas: lnx200nas, lnx202pc: lnx200nas, lnx203hp: lnx200nas

- nodo          health    state          t_state     pres     wdog  busy   stage                       prog    p_age  stall   local_size  local_events    created  executing  completed  dirty  
- lnx200nas     ok        ACTIVE            4.1h       0s       0s  Y      -                              -        -  N                0           496        496          0          0  -      
- lnx202pc      ok        STAND-BY          1.3h       1s       1s  Y      -                              -        -  N                0          2216       2216          0          0  -      
- lnx203hp      ok        STAND-BY          4.1h       0s       0s  Y      -                              -        -  N                0          1014       1014          0          0  -      

### events de lnx200nas:

- lnx200nas         events.local.000.jsonl          342665      2026-06-03T19:16:48.625890291+
- lnx200nas         events.lnx200nas.000.jsonl      342665      2026-06-03T19:16:48.618722767+
- lnx202pc          events.lnx200nas.000.jsonl      342665      2026-06-03T19:16:48.730845556+
- lnx203hp          events.lnx200nas.000.jsonl      342665      2026-06-03T19:16:48.841422802+

### events de lnx202pc:

- lnx202pc          events.local.000.jsonl          1703907     2026-06-03T19:16:49.548815534+
- lnx200nas         events.lnx202pc.000.jsonl       1703907     2026-06-03T19:16:50.183797943+
- lnx200nas         events.lnx202pc.000.jsonl       1703907     2026-06-03T19:16:50.183797943+
- lnx203hp          events.lnx202pc.000.jsonl       1703907     2026-06-03T19:16:50.298227338+

### events de lnx203hp:

- lnx203hp          events.local.000.jsonl          794783      2026-06-03T19:16:44.981209141+
- lnx200nas         events.lnx203hp.000.jsonl       794783      2026-06-03T19:16:45.504709599+
- lnx200nas         events.lnx203hp.000.jsonl       794783      2026-06-03T19:16:45.504709599+
- lnx202pc          events.lnx203hp.000.jsonl       794783      2026-06-03T19:16:45.630053348+

### log de lnx200nas:

- lnx200nas         event_log.local.000.jsonl       389078      2026-06-03T19:16:45.541693764+
- lnx200nas         event_log.lnx200nas.000.jsonl   389078      2026-06-03T19:16:48.292868370+
- lnx202pc          event_log.lnx200nas.000.jsonl   389078      2026-06-03T19:16:48.456290495+
- lnx203hp          event_log.lnx200nas.000.jsonl   389078      2026-06-03T19:16:48.599349754+

### log de lnx202pc:

- lnx202pc          event_log.local.000.jsonl       1752866     2026-06-03T19:16:48.133801218+
- lnx200nas         event_log.lnx202pc.000.jsonl    1752866     2026-06-03T19:16:49.420780823+
- lnx200nas         event_log.lnx202pc.000.jsonl    1752866     2026-06-03T19:16:49.420780823+
- lnx203hp          event_log.lnx202pc.000.jsonl    1752866     2026-06-03T19:16:49.483224538+

### log de lnx203hp:

- lnx203hp          event_log.local.000.jsonl       800418      2026-06-03T19:16:43.675204698+
- lnx200nas         event_log.lnx203hp.000.jsonl    800418      2026-06-03T19:16:44.847254198+
- lnx200nas         event_log.lnx203hp.000.jsonl    800418      2026-06-03T19:16:44.847254198+
- lnx202pc          event_log.lnx203hp.000.jsonl    800418      2026-06-03T19:16:44.930347448+
