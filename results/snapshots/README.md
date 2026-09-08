# Snapshots

`results/*.json` is regenerated on every run and always shows the current
measurement. These are frozen copies of earlier ones, kept because the paper cites
them and a generated file cannot hold its own history.

| file | what it is |
|---|---|
| `map-2026-09-07.json` | the measurement the paper reports, before the defects the suite found in Samyama-Graph were fixed |
| `metamorphic-2026-09-07.json` | the metamorphic run of the same date |

At that snapshot Samyama-Graph scored 8 conforming, 4 diverging, 0 rejecting, 5
inexpressible, with 24 metamorphic violations. It now scores 15 / 2 / 0 / 0 with none.
See `POST-PUBLICATION.md` for why those two rows are not comparable.

The five external engines are byte-identical between the snapshot and the current
run — that is the check that the re-measurement changed nothing it should not have.
