"""The tool's name, mark and page palette, in one place (Karoline's decisions of 2026-09-27).

The tool is called grownet (#71): the package, the module and the command, since 2026-09-28. The
repository and the schema id keep the old name, crossfeed, for now (Craig's call).

The page style is the one Karoline approved in the grownet interface proposal: a header with the mark and
the wordmark, one green primary action, quiet table headers, and directions colored with the legend's two
signal colors. Inhibition is the orange-red #C2410C, not a plain red, because with uniform arrowheads the
color is the only cue and green against red is the hardest pair for color vision deficiency.
"""
from __future__ import annotations

NAME = "grownet"
COMMAND = "grownet"            # the installed command

INK, MUTED, LINE, PANEL, PAGE = "#1C1F1E", "#5B625F", "#D9DDDA", "#F6F8F7", "#EEF1EF"
GROWTH, INHIBITION, NODE = "#1A7F5A", "#C2410C", "#7A8580"
# Node colors by genus in Cytoscape, one per genus (Karoline, 2026-09-27: "each genus its own color").
# The first four (blue, yellow, pink, violet) are the categorical palette's slots that do not read as a sign
# next to the arcs, checked with the dataviz palette validator together with GROWTH and INHIBITION. The rest
# were picked greedily from OKLCH, outside the hue bands of the two arc colors, each time the candidate
# farthest from every color already chosen and from the arc colors, by the validator's own measure (OKLab
# Delta E x100, the worst of normal vision and simulated deuteranopia, protanopia and tritanopia). So the
# list runs from most to least distinct: the 10th color still keeps 8.6 from all before it (the validator's
# target is 8), the 12th 6.9, the 20th 4.7, the 48th 2.2. The most common genera of a network take the
# first colors; mGrowthDB held 44 genera when this was made, so 48 leaves room.
GENUS_COLORS = (
    "#2A78D6", "#EDA100", "#E87BA4", "#4A3AA7", "#A2C5FF", "#762E61", "#069CE4", "#C7CA85", "#B8892D",
    "#635A93", "#F1ACCC", "#A3B472", "#A74FBB", "#8AACE4", "#583A84", "#D75EB4", "#854E73", "#B25977",
    "#CC96C6", "#544EC5", "#9DDA4F", "#738242", "#8080FC", "#3C561C", "#92689C", "#4CDBE3", "#88194A",
    "#878CC9", "#4C701A", "#84C030", "#E5598E", "#BA93FB", "#959754", "#6B2094", "#724AAB", "#984260",
    "#9E658B", "#7B67CC", "#7E0F7A", "#7A5283", "#C8729C", "#E38AB5", "#B249AC", "#8E35A1", "#64B8D2",
    "#6C4302", "#A76C12", "#623B6B"
)

# The mark (docs/logo.svg): three gray nodes joined by directed edges, green for facilitation and
# orange-red for inhibition, the same arrowhead on both. The legend and the page both take it from here.
LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" '
        'role="img" aria-label="grownet">'
        '<g>'
        '<line x1="16.6" y1="42.5" x2="24.9" y2="27.8" stroke="#1A7F5A" stroke-width="5.0" stroke-linecap="round"/>'
        '<path d="M 27.80 22.51 L 27.33 34.84 L 17.55 29.38 z" fill="#1A7F5A" '
        'stroke="#1A7F5A" stroke-width="0.6" stroke-linejoin="round"/>'
        '<line x1="36.2" y1="21.1" x2="43.7" y2="31.9" stroke="#C2410C" stroke-width="5.0" stroke-linecap="round"/>'
        '<path d="M 47.12 36.92 L 36.26 31.04 L 45.48 24.69 z" fill="#C2410C" '
        'stroke="#C2410C" stroke-width="0.6" stroke-linejoin="round"/>'
        '<circle cx="13" cy="49" r="6.4" fill="#7A8580"/><circle cx="32" cy="15" r="6.4" fill="#7A8580"/>'
        '<circle cx="52" cy="44" r="6.4" fill="#7A8580"/></g>'
        '</svg>')

# the wordmark: all lowercase in the system font, with "net" in the growth green
WORDMARK = '<span class="word">grow<b>net</b></span>'


def logo_svg(size: int = 64) -> str:
    """The mark at `size` pixels."""
    return LOGO.replace("{size}", str(size))


CSS = f"""
:root {{ --ink: {INK}; --muted: {MUTED}; --line: {LINE}; --panel: {PANEL}; --grow: {GROWTH};
        --hold: {INHIBITION}; }}
* {{ box-sizing: border-box; }}
body {{ font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink);
       background: {PAGE}; margin: 0; padding: 1.5rem 1rem; }}
.app {{ max-width: 72rem; margin: 0 auto; background: #fff; border: 1px solid var(--line);
       border-radius: 10px; overflow: hidden; }}
.app > header {{ display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; padding: .8rem 1.2rem;
                border-bottom: 1px solid var(--line); background: var(--panel); }}
.brand {{ display: flex; align-items: center; gap: .55rem; margin: 0; font-size: 1.15rem;
         color: inherit; text-decoration: none; }}
.word {{ font-weight: 650; letter-spacing: -.01em; }} .word b {{ font-weight: 650; color: var(--grow); }}
.version {{ font-size: .8rem; color: var(--muted); border: 1px solid var(--line); border-radius: 999px;
           padding: .05rem .5rem; background: #fff; }}
.app > header nav {{ margin-left: auto; display: flex; gap: .4rem; }}
.app > main {{ padding: 1.2rem; }}
h2 {{ font-size: 1.05rem; margin: 1.8rem 0 .5rem; }}
h2.page {{ font-size: 1.3rem; margin-top: 0; }}
label.field {{ display: block; font-weight: 600; margin-bottom: .1rem; }}
.examples {{ color: var(--muted); font-size: .82rem; margin: 0 0 .4rem; }}
textarea, input, select {{ font: inherit; }}
textarea {{ width: 100%; padding: .6rem .7rem; border: 1px solid var(--line); border-radius: 8px; resize: vertical; }}
input[type=text] {{ padding: .25rem .45rem; border: 1px solid var(--line); border-radius: 6px; }}
select {{ padding: .25rem .45rem; border: 1px solid var(--line); border-radius: 6px; background: #fff; }}
textarea:focus, input:focus, select:focus, button:focus, .btn:focus {{ outline: 2px solid var(--grow);
  outline-offset: 2px; }}
.hint, .muted {{ color: var(--muted); font-size: .88rem; }} .hint {{ margin: .35rem 0 0; }}
.btn, button {{ font: inherit; display: inline-block; padding: .45rem 1rem; border-radius: 8px;
               border: 1px solid var(--line); background: #fff; color: var(--ink); cursor: pointer;
               text-decoration: none; }}
.btn.primary, button.primary {{ background: var(--grow); border-color: var(--grow); color: #fff; font-weight: 600; }}
.btn.quiet {{ background: transparent; padding: .3rem .7rem; }}
.bar {{ display: flex; gap: .6rem; margin-top: .9rem; flex-wrap: wrap; align-items: center; }}
details {{ margin-top: 1.1rem; border-top: 1px solid var(--line); padding-top: .8rem; }}
summary {{ cursor: pointer; font-weight: 600; }}
.row {{ margin: .55rem 0; }}
.note {{ background: var(--panel); border: 1px solid var(--line); padding: .7rem .9rem; border-radius: 8px; }}
.result {{ margin-top: 1.4rem; border-top: 1px solid var(--line); padding-top: .4rem; }}
.scroll {{ overflow-x: auto; }} .legend svg {{ max-width: 100%; height: auto; }}
.idea {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: .8rem 1.2rem;
        margin: .8rem 0 .3rem; }}
.idea figure {{ margin: 0; }} .idea svg {{ width: 100%; height: auto; display: block; }}
table {{ border-collapse: collapse; width: 100%; font-size: .9rem; margin-top: .5rem; }}
th, td {{ text-align: left; padding: .38rem .5rem; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ color: var(--muted); font-weight: 600; font-size: .78rem; text-transform: uppercase; letter-spacing: .03em; }}
.nowrap {{ white-space: nowrap; }}
.up {{ color: var(--grow); font-weight: 600; }} .down {{ color: var(--hold); font-weight: 600; }}
.pill {{ display: inline-block; font-size: .75rem; padding: .05rem .45rem; margin: .1rem .15rem .1rem 0;
        border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }}
.sources {{ font-size: .9rem; }} .sources li {{ margin-bottom: .3rem; }}
pre {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: .6rem .8rem;
      white-space: pre-wrap; }}
code {{ font-size: .9em; }} dd code {{ overflow-wrap: anywhere; }}
dt {{ font-weight: 600; margin-top: .8rem; }} dd {{ margin-left: 1rem; }}
.decisions li, .toc li {{ margin-bottom: .3rem; }}
a {{ color: var(--grow); }}
form.inline {{ display: inline-flex; gap: .4rem; align-items: center; margin: 0; }}
.outputs {{ margin: .6rem 0 1rem; }}
.outputs details.report {{ margin: 0; border: 0; padding: 0; }}
.outputs details.report[open] {{ flex-basis: 100%; }}
summary.btn {{ list-style: none; display: inline-block; font-weight: normal; }}
summary.btn::-webkit-details-marker {{ display: none; }}
.report pre {{ max-height: 26rem; overflow: auto; font-size: .82rem; margin-top: .6rem; }}
progress {{ width: 100%; height: 10px; accent-color: var(--grow); }}
"""
