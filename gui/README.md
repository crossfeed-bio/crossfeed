# crossfeed network viewer

A single self-contained HTML page that reads a crossfeed interaction network and shows it as a directed
graph. It is the presentation layer: the Python core stays dependency-free and emits the neutral format,
and this reads that format. No build step and no dependencies. Open `index.html` by double-click.

Use it:

- Load a network the engine wrote (the "Load network JSON" button), or start from the built-in synthetic
  example.
- Type species names to focus the network on them and their interactions.
- Click a species to list its interactions, each with effect, a coarse strength, condition, and the
  studies behind it. Facilitation, inhibition, and neutral are drawn with distinct color, line style, and
  arrowhead, so the sign reads without relying on color alone.
- Open "Advanced settings" to see the derivation choices and their defaults (from
  [docs/METHOD_NOTES.md](../docs/METHOD_NOTES.md)) alongside the live view filters.
- Download the current view as JSON or as GraphML. The GraphML matches `src/crossfeed/export.py`, so it is
  the same file the CLI writes, and it imports into Cytoscape through File, then Import, then Network.

No real data ships here: the built-in example is synthetic. Load a real network from a file to view
experimental interactions.
