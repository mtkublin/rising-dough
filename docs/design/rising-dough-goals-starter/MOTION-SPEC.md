# Levi · motion spec

CSS: `css/starter-motion.css`. Live: `motion.html`.

| Moment | Layer | Keyframes | Duration | Easing | Loop | Reduced motion |
|---|---|---|---|---|---|---|
| all idle loops | rule | nothing moves: every loop is cells changing colour or blinking in and out (opacity only). Waves are 8 bands of cells, each lagging the previous by ⅛ of the cycle | — | — | — | stills as drawn |
| idle · dormant | .dough-surface (.erode/.fringe) · .flow .sheen · .sleep-bubble .sb | surface: the top cell of each column blinks out and the one above blinks in, left to right; a faint light band climbs the dough; the sleep bubble: 1 cell → 2×2 → ring at the mouth, then the ring shows 2 rows higher, five times, then scatters | 7 s surface · 7 s sheen · 5 s bubble (0.4 s per step) | linear · ease-in-out | ∞ | still, lid on, no bubble |
| idle · sleepy | as dormant + .bubbles .trail | as dormant; one bubble rises through the dough, one cell lit at a time, to just above the surface | 6 s · 6 s · 4 s bubble · 3.6 s rise (0.16 s per cell) | linear | ∞ | still |
| idle · bubbly | .dough-surface · .sheen · .blink · .bubbles .trail | surface wave; a brighter band climbs the dough; blink: eye cells covered in crust for 4% of the cycle; two bubble columns rising | 4.8 s · 4.8 s · 6 s blink · 3.2 s rise (0.14 s per cell) | linear · ease-in-out | ∞, columns offset 1.1 s | still |
| idle · rising | as bubbly | same layers, faster, three bubble columns | 4.2 s · 4.2 s · 5 s blink · 2.6 s rise (0.12 s per cell) | as bubbly | ∞ | still |
| idle · overflowing | .dough-surface (.erode/.fringe) · .flow (.sheen/.fold) · .trails · .pops · .blink | a caramel ripple with a light crest behind it rolls out from the top centre; edge cells blink in just outside the outline and out just inside it, travelling round the edge; drops run down the slumps; surface cells flash and go | 2.8 s waves · 3.2 s edge · 2.4 s drops (0.2 s per cell) · 2.8 s pops · 4.5 s blink | ease-in-out · linear | ∞ | still |
| fed | .flow .sheen (card and badge) | a light flash climbs the dough band by band | 700 ms, +60 ms per band | ease-out | once per feed (.is-fed) | none; new state shows |
| state change | two stills (.rd-starter__swap) | opacity crossfade | 300 ms | ease | once | instant swap |
| wake up | .lid › .b0…b7 → SVG swap → .sheen | lid cells blink out left to right over 500 ms; swap to the awake SVG; a light flash climbs the dough | 1100 ms | linear · ease-out | once (.is-waking) | instant swap |
| welcome | dialog · .sheen | dialog fade + translateY 8 px → 0 (UI, not artwork); one fed flash | 240 ms + 700 ms | ease-out | once | dialog fade only |
| milestone toast | .rd-toast | translateY 8 px → 0, opacity 0 → 1 (UI, not artwork) | 200 ms in · 200 ms out | ease-out | once | fade only |
| loaf baked | .rd-loaf.is-new .rd-loaf__art .r0…r3 | the loaf's cells appear in four row bands, bottom to top | 400 ms (100 ms per band) | linear | once | appears |
| loaf label | .rd-loaf__tip | opacity 0 → 1 on hover, focus, tap | 150 ms | ease | — | instant |
