# Cross-camera tracking on the government test grid — what the footage allows

Written by hand after attempting to demonstrate live cross-camera vehicle
tracking end to end on the real government grid (`cctv.corp8.cloud`).

The attempt did not succeed, and the reason turned out to be a property of
the test footage rather than of the matching, tracking or route code. That
distinction matters enough to record, because the same failure looks from
the console exactly like the feature being broken.

---

## The claim under test

Reconstructing one vehicle's journey across several cameras is the
headline capability: a plate goes in, a timestamped per-camera timeline and
a mapped route come out. Demonstrating it live requires one thing the
architecture cannot supply on its own — **the same vehicle, seen by two
cameras, in the same span of time.**

## What the grid actually serves

Each camera replays its own archived clip, and the clips are from different
dates. Read from each camera's own burned-in clock while all four were
streaming simultaneously:

| Camera | Location | Scene time | |
|---|---|---|---|
| cam06 | Junagadh | 17 Jun 2026, 12:30 | archive |
| cam08 | Junagadh | 13 Jun 2026, 15:48 | archive |
| cam09 | Junagadh | 13 Jun 2026, 21:11 | archive |
| cam10 | Junagadh | 26 Sep 2026, 08:57 | **live** (48 s behind real time) |
| cam17 | Rajkot | 14 Jun 2026, 08:43 | archive |
| cam18 | Rajkot | 13 Jun 2026, 21:08 | archive |

Only **cam10** is a live feed. Every other camera probed is replaying
recorded footage, and no two of them are replaying the same day.

A vehicle cannot be on 13 June, 17 June and 26 September at once. Between
those cameras the cross-camera claim is not merely unlikely, it is
impossible — and any match found between them would be a false one.

## The one pair that could have worked

`cam08` and `cam09` share coordinates (21.5222, 70.4579) and were briefly
within **27 seconds** of each other in scene time — 15:48:02 against
15:47:35 on the same day. That is a genuine shared window.

It fails on footage quality instead:

- **cam09 is a black frame.** Its clip reaches 21:11 at night with no
  useful illumination anywhere in shot. Over twenty minutes of analysis it
  produced 2 plate reads and 0 that formed a valid registration.
- **cam08** produced 14 reads and 0 valid in the same period.

So the only time-aligned pair has no usable image between them.

## What this does not mean

The route machinery itself was verified working during the same session,
against real footage rather than fixtures. Searching `GJ11U0117` returned
both of its sightings with location, scene timestamp, match confidence and
the evidence snapshot, rendered as a movement map and timeline. The code
path a cross-camera route would take is the same one; it simply had one
camera's sightings to draw rather than two.

Over the run, 4 cameras produced **1,160 reads and 34 distinct valid
registrations**, all from cam06 — the only camera combining daylight,
a usable angle, and traffic close enough to resolve.

## What would make the demonstration possible

1. **Two cameras on one corridor, streaming live.** The grid has exactly one
   live feed, so this is not currently available. A second live camera in
   Junagadh would be sufficient.
2. **Archived clips from a common window.** If the organisers can align the
   replayed clips — even to the same hour on the same day — the existing
   Junagadh cluster of five cameras becomes a genuine corridor.
3. **Closer camera placement.** Independently of timing, the wide-area
   framing on most of these cameras puts plates at 30–80 px, below what any
   OCR resolves. See `M1-CAPACITY-FINDINGS.md`.

## A bug this exposed

The first apparent cross-camera matches were the plates `1`, `111` and `4`
— the same OCR fragment read by two cameras at once, which is
indistinguishable from one vehicle seen in two places.

They were 28% of every detection stored. The pipeline now discards reads
below six characters: Indian plate grammar admits nothing shorter than
eight, and the matching ladder reaches an edit distance of two, so a
shorter read cannot resolve to a real registration however it is matched.

That one is worth stating plainly, because the fabricated journey it would
have produced is precisely the kind of evidence this system must never
manufacture.
