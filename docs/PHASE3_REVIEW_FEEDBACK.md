Review-Rückmeldung zu Commits `8093875`/`abc5575` (Phase 3). Testsuite läuft
in einer funktionierenden Umgebung grün (33/33), Migration verifiziert — dein
`pytest`-Sandbox-Problem bleibt ein reines Toolchain-Problem, kein
Code-Problem an dieser Stelle. Ein echter, schwerwiegender Fund bleibt aber
offen, bitte gezielt beheben, nichts anderes anfassen:

## Fund: `threading.Barrier` in Produktionscode kann Live-Läufe zum Absturz bringen und Ergebnisse verlieren

In `app/routers/projects.py`, `_run_solution_agents()`:

```python
persistence_barrier = threading.Barrier(len(pending)) if len(pending) > 1 else None

def invoke(role: str):
    ...
    if persistence_barrier is not None:
        persistence_barrier.wait(timeout=5)   # <- außerhalb jedes try/except
    ...
```

`persistence_barrier.wait(timeout=5)` liegt **außerhalb** des `try/except
ModelProviderError`-Blocks und wird von `invoke()` nicht abgefangen; auch
`future.result()` beim Fan-in (`outcomes = {role: future.result() ...}`) fängt
nichts ab. Architect und Challenger sind zwei unabhängige HIGH-Modell-Aufrufe
mit unterschiedlicher, variabler Latenz (siehe echte Gateway-Läufe in
`PHASE1_CHECKPOINT.md`: 6,8s/8,1s bereits bei trivialen Prompts) — im echten
Betrieb werden die beiden Aufrufe regelmäßig mehr als 5 Sekunden
auseinanderliegen, nicht als Ausnahme, sondern als Normalfall.

Sobald das passiert, wirft `Barrier.wait()` `BrokenBarrierError` für **beide**
wartenden Threads. Konkrete Folgen:

1. Der komplette Request (`research/approve` bzw. der automatische Übergang in
   `_run_research_agent`) crasht mit unbehandeltem 500.
2. Beide Ergebnisse gehen verloren — auch das eines bereits erfolgreich (und
   kostenpflichtig) abgeschlossenen Modellaufrufs, weil der Schreibvorgang
   hinter der Barrier liegt und nie erreicht wird.
3. Das Projekt bleibt dauerhaft in `GENERATING_SOLUTIONS` hängen:
   `architect`/`challenger.run_status` bleibt bei `"RUNNING"` (wurde vor dem
   Aufruf gesetzt, nie zurückgesetzt), und `agent_runs.status` bleibt ebenfalls
   `"RUNNING"` statt `"FAILED"` — `/retry` findet daher „nichts zum
   Wiederholen" (409) und es gibt keinen Weg zurück ohne manuellen
   DB-Eingriff.

Der Test `test_approval_runs_both_roles_in_parallel_with_identical_isolated_context`
fängt das nicht ab, weil sein Mock beide Zweige absichtlich fast gleichzeitig
fertig werden lässt (`barrier.wait(timeout=2)` + `time.sleep(0.05)` in
beiden) — das bildet reale, ungleiche Modell-Latenz nicht ab.

## Erforderliche Korrektur

* **Die `threading.Barrier` komplett aus `_run_solution_agents`/`invoke()`
  entfernen.** Sie gehört nicht in den Produktionspfad. AT-3.2 (getrennte
  Tabellen/Sessions/Transaktionen unter WAL-Modus vertragen echte
  Gleichzeitigkeit ohne `database is locked`) ist bereits durch die getrennten
  `branch_session()`-Transaktionen erfüllt — dafür ist keine Laufzeit-
  Synchronisation zwischen den beiden Threads nötig, jeder Zweig schreibt
  unabhängig, sobald er fertig ist.
* Der Test soll die erzwungene Überlappung **rein im Testcode** simulieren
  (z. B. wie bisher ein `barrier`/`sleep` **im Mock von `call_model`**), ohne
  dass Produktionscode dafür eine Synchronisationsprimitive bereitstellen
  muss. Das ist im Test bereits so gebaut (`fake_call_model` in
  `test_phase3_planning.py`) — nur die Abhängigkeit von einer Barrier *in der
  Anwendung selbst* muss weg.
* Nach der Korrektur: Testsuite erneut lokal ausführen (`compileall`/
  `py_compile` reicht nicht, um dieses Verhalten zu prüfen — ideal wäre ein
  ergänzter Test, der zwei `call_model`-Mocks mit stark unterschiedlicher,
  aber realistischer Verzögerung (z. B. 0,01s vs. 0,3s) laufen lässt und
  sicherstellt, dass **beide** Zweige trotzdem korrekt und unabhängig
  `DONE` erreichen, ganz ohne Barrier).
* `docs/PHASE3_CHECKPOINT.md` entsprechend korrigieren: der Satz „Eine
  Barrier synchronisiert im Test die beiden Persistierungsversuche" ist
  irreführend, weil die Barrier tatsächlich in der Anwendung selbst lag, nicht
  nur im Test.

Bitte ausschließlich diesen einen Punkt beheben, nichts an Scope oder bereits
getroffenen Entscheidungen ändern. Danach kurz in `docs/PHASE3_CHECKPOINT.md`
nachtragen, was korrigiert wurde, committen und pushen.
