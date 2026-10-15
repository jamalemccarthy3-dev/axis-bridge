# NEXXUS Academy: curriculum authoring

Platform mode is a digital academy: a school and training ground where people learn to build, operate and run real systems with exact prompts and commands, earn badges as proof, and then guide others. The content lives here as plain JSON, one file per **track**, checked by `academy.py` every time it loads (a bad step is reported in the Academy, never silently shown).

```
track  (academy/curriculum/NN-name.json)
  modules[]  each earns a module badge when every step is done
    steps[]  one lesson each
```

## A step

| field | meaning |
|---|---|
| `id`, `title` | slug and heading |
| `why` | why it matters, in a sentence or two |
| `do` | the things to do, in order |
| `prompts` | `{label, text}` exact prompts to paste into an AI helper (a Copy button is shown) |
| `commands` | `{label, text, where}` exact things to type into NEXXUS or a terminal, and where |
| `tips` | proven advice |
| `video` | `null`, or `{title, url, credit}` (see below) |
| `check` | how the learner knows they are done |
| `proof` | how completion is proved: `"note"` (self-reported, a sentence or two), `"link"` (an https link as evidence) or `"auto:<check>"` (NEXXUS verifies it against what the learner really did) |

Auto checks live in `academy.py` (`AUTO_CHECKS`): `profile_complete`, `first_post`, `public_post`, `public_post_substantial`, `profile_photo`, `first_photo`, `featured_post`. Add a check there, with a test, before using it in a step. **Prefer an auto check wherever something can be verified**: a badge made only of self-reported steps says so on its face.

## Rules for content

* Teach things that are true and that you have done. Commands must exist; prompts must work.
* No promises about income, followers or results. Business tracks carry a `disclaimer`; `test_academy.py` fails on phrases like "guaranteed" or "passive income".
* No private or personal data in examples. Keep it PG-13.

## Adding a video

Set a step's `video` to `{"title": "...", "url": "https://www.youtube-nocookie.com/embed/<id>", "credit": "who made it"}`. Only these hosts and embed paths are accepted, over https:

* `www.youtube-nocookie.com/embed/...`
* `player.vimeo.com/video/...`
* `www.facebook.com/plugins/video.php?...`

Anything else is rejected with a problem message. The video is **click-to-load**: nothing loads from the video host until the learner presses play, and the page says the host may track them. **Only attach videos you made or have permission to embed.** No video URLs ship in this repository: add real, rights-cleared ones.

## Badges

A module badge is earned when every step in it is done; a track badge when every module is; **Mentor-ready** when any whole track is done (the first step of the leadership loop; mentoring itself needs other people on the platform and is not built yet). Every badge records how it was proved (`verified`, `self-reported` or `mixed`) in `nexxus_data/platform/badges.jsonl`, an append-only ledger. Badges are separate from ranks: ranks come only from public contributions (`ranks.py`); badges only from learning and doing.
