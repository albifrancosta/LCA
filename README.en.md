# LCA — Light. Camera. Action. 🎬

[🇧🇷 Português](README.md) | 🇺🇸 **English**

[![testes](https://github.com/albifrancosta/LCA/actions/workflows/testes.yml/badge.svg)](https://github.com/albifrancosta/LCA/actions/workflows/testes.yml)

**An AI video studio inside Claude Code.**

Tell it the video you want — *"a 30-second ad for my store"*, *"a Christmas video thanking our customers"*, *"cut the pauses out of this video and add captions"* — and LCA does the work of a whole production company: it interviews you, writes the script, draws the storyboard, directs the images and the animation, records the narration, picks the music, edits everything in Remotion, checks the result and delivers an MP4 ready for Reels, TikTok, Shorts or YouTube.

You don't need to know how to make videos. You approve; LCA does the rest.

> ⚠️ **Language note:** LCA is **Portuguese-first**. The skill's instructions, agents, guides and script messages are in Brazilian Portuguese, and it talks to you in Portuguese by default. Narration can be generated in other languages on request. Translations and contributions are welcome.

---

## Contents

- [How it works](#how-it-works)
- [What you can do](#what-you-can-do)
- [The studio: departments](#the-studio-departments)
- [Free vs. paid](#free-vs-paid)
- [Installation](#installation)
- [API keys](#api-keys--all-optional)
- [Your first video](#your-first-video)
- [Your brand and memory](#your-brand-and-memory)
- [Quality: what LCA checks on its own](#quality-what-lca-checks-on-its-own)
- [FAQ](#faq)
- [Project structure](#project-structure)
- [Notices and license](#notices)

---

## How it works

Every new video goes through the same steps. At the ones marked ✋ LCA **stops and waits for your approval** — nothing paid happens before that.

```
 0. Interview ......... short questions, one at a time, each with its own recommendation
 1. Hook .............. 6 different openings, scored; you pick one
 2. Script ............ lines, timing per scene, a re-hook halfway, an ending that closes the loop
 ✋ Checkpoint 1 — script storyboard (frames with each scene's action and line)
 3. Images ............ generated via API, or by you in another AI with ready-made prompts
 ✋ Checkpoint 2 — storyboard with the real images
 4. Animation ......... each image becomes a clip (paid AI, free AI you run, or code)
 5. Narration ......... a voice with a defined tone, checked word by word
 6. Music ............. 3–4 options with verified licenses, aligned to the video's arc
 7. Edit .............. Remotion: cuts on speech, captions, on-screen text, broadcast-level mix
 8. Review ............ contact sheet, loudness (−14 LUFS), voice vs. music, clipped text
 ✋ Checkpoint 3 — the finished video
 9. Delivery .......... MP4 + post caption, hashtags, cover, pinned comment
10. Learning .......... tell it how the video performed; it adjusts its patterns for the next one
```

### A real example (summarized)

> **You:** I want a Christmas video for my company: a technician wakes up, takes the uniform out of the drawer like a superhero suit, and at the end we thank our customers.
>
> **LCA:** writes the script "The Uniform" (60 s, 10 scenes), shows the storyboard and explains one choice: it replaced "available at all times" with "by your side on every call", because the service contract covers business hours only.
>
> **You:** make it 7 a.m. · no rain · use the photos of our 4 technicians · no single protagonist, they all are.
>
> **LCA:** updates the script, the narration (now plural) and the 17 prompts; sends them one at a time; checks every image you generate ("the face doesn't match T3 — try this prompt") and every animated clip ("great, I'll use 0–4 s"); when the free quota runs out it animates the rest in code; records the voice, suggests 4 tracks, aligns the soft part of the music with the Christmas-night scene and delivers the MP4 with the post caption ready.

---

## What you can do

| Mode | You ask | LCA delivers |
|---|---|---|
| **Create** | "make a 45 s video about…" | script → images → animation → voice → music → MP4 |
| **Ad** | "a 30 s ad for my product" | pain → turn → solution → call to action, with scenes and lines on time |
| **Story** | "a Christmas mini-series with an A/B choice at the end" | episode with fixed characters, a hook and a vote in the comments |
| **Edit** | "remove the pauses and add captions to this video" | silence and filler cuts, word-by-word captions, multiple clips, 16:9 ↔ 9:16 |
| **Learn** | send a viral video "to use as a reference" | a breakdown of hook, cut rhythm, captions and structure — applied to future videos |
| **Feedback** | "it got 3k views and 40% retention" | adjusts the score of the patterns that worked or didn't |

Formats: vertical 9:16 (default), 16:9, 1:1. Length: from 15 s to a few minutes.

---

## The studio: departments

LCA works like a production company. The main session is the **Director**: it talks to you, decides and checks. The departments are Claude Code **agents** that process batches of work in parallel and report back to the Director — they never talk to you and never spend without an approved budget.

| Agent | Does |
|---|---|
| `estudio-roteirista` | script, lines, hook, re-hook and ending |
| `estudio-fotografia` | shot breakdown: framing, camera, duration, what each scene must show |
| `estudio-elenco` | character sheets (face, wardrobe, colors, voice) |
| `estudio-arte` | each scene's image (via API or directing you) and color matching |
| `estudio-animacao` | turns images into clips with real acting, not just zoom |
| `estudio-audio` | emotion-directed voices, ambience and sound effects |
| `estudio-musical` | picks and prepares the music (free library, AI or synthesized) |
| `estudio-editor` | Remotion edit, mixing and contact-sheet review |
| `estudio-qualidade` | rejects anything off-script: wrong face, deformed hand, swapped line |
| `estudio-atencao` | where viewers will lose interest and what to change |

Agents are optional: without them the Director does everything itself, just slower.

---

## Free vs. paid

LCA always tries the free path first and **shows the cost before any spending**.

| Step | Free | Paid (only with your OK) |
|---|---|---|
| Script, storyboard, editing, captions | ✅ always | — |
| Narration | Gemini voice (free daily quota) or your own recorded voice | — |
| Images | you generate them in any AI with the ready-made prompts | OpenAI GPT Image (~US$0.05 per image) |
| Animation | you animate them in another AI with the ready-made prompts · Hugging Face (a few per day) · zoom and effects in code | fal.ai / Runware — Kling (~US$0.35 per 5 s clip) |
| Music | Pixabay (commercial license) or synthesized track | AI music (ElevenLabs / ACE on fal.ai) |
| Stock footage | Pixabay / Pexels | — |

Example: the 66 s Christmas video above cost **a few cents** (just the voice), because the images and clips were generated by the user with free tools and what was missing was animated in code.

Every paid call is logged in a per-project ledger (`scripts/custos.py relatorio`).

---

## Installation

### Requirements

| | Used for |
|---|---|
| [Claude Code](https://claude.com/claude-code) | where LCA runs |
| Python 3.11+ | the scripts |
| [ffmpeg](https://ffmpeg.org/) on PATH | audio, video and measurements |
| Node.js 18+ | editing in [Remotion](https://www.remotion.dev/) |

### Step by step

```bash
git clone https://github.com/albifrancosta/LCA.git ~/.claude/skills/criador-video
cd ~/.claude/skills/criador-video
pip install -r requirements.txt
python scripts/instalar_agentes.py instalar
python scripts/chaves.py status
```

- The folder **must** be named `criador-video` — it's the skill's internal name.
- `instalar_agentes.py` copies the departments to `~/.claude/agents/`.
- `chaves.py status` shows what already works and what's missing (it never prints any key).
- Then **open a new** Claude Code session.

The optional packages in `requirements.txt` enable extra features (local transcription, pose analysis, music beat detection). Without them LCA takes another path.

---

## API keys — all optional

With no keys at all you already get: script, storyboards, editing and motion graphics in Remotion, video editing (cuts, silences, captions, formats), local transcription and synthesized music.

| Key | Service | Cost | Enables |
|---|---|---|---|
| `GEMINI_API_KEY` | Google Gemini | free with limits | AI narration, video analysis |
| `FAL_KEY` | fal.ai | **paid** | animated clips, AI music, lip-sync |
| `OPENAI_API_KEY` | OpenAI | **paid** | AI-generated images |
| `RUNWARE_API_KEY` | Runware | **paid** | clips and lip-sync (fal.ai alternative) |
| `PIXABAY_API_KEY` | Pixabay | free | stock footage search |
| `PEXELS_API_KEY` | Pexels | free | stock footage search |
| `HF_TOKEN` | Hugging Face | free | more free clips per day |

**Set them up outside the chat — never paste a key into the conversation** (anything typed in the chat stays in the history):

```bash
python scripts/configurar.py
```

It runs in your own terminal: input is hidden, each key is tested and saved to `.env` (which never goes to Git). Or copy `.env.example` to `.env` and fill it in.

---

## Your first video

In a new Claude Code session, just ask in plain language (in Portuguese):

```
faz um vídeo vertical de 30 segundos apresentando a minha padaria
```
*("make a 30-second vertical video introducing my bakery")*

LCA will:
1. check what is configured and tell you what's free and what's paid;
2. ask a few questions (audience, goal, voice tone, visual style);
3. suggest 3 hooks for you to choose from;
4. show the script as a storyboard and wait for your OK.

Other requests that work:

```
corta as pausas e os "é…" desse vídeo e coloca legenda: C:\videos\aula.mp4
transforma esse vídeo de 10 minutos em 5 cortes para o Reels
analisa esse vídeo viral e usa como referência: https://…
faz os prompts das imagens que eu gero no Gemini e você monta
troca a trilha por algo mais épico
```
*(cut the pauses and fillers and add captions · turn this 10-minute video into 5 Reels · analyze this viral video and use it as a reference · write the image prompts, I'll generate them and you edit · change the music to something more epic)*

---

## Your brand and memory

LCA learns from you and keeps it in `memoria/` (starts empty):

| File | Keeps |
|---|---|
| `perfil.md` | your brand, colors, contact, voice, default format and **fixed preferences** ("no yellow captions", "music always audible") |
| `padroes.md` | what holds attention (hook, pacing, re-hook…), with scores that go up or down based on your results |
| `historico.md` | every video made, with hook, patterns used and metrics |
| `biblioteca.md` | characters, scenes, tracks and components worth reusing (saves time and money) |

So your brand name is **pronounced** correctly by the voice and **recognized** in transcription, copy `config/marca.example.json` to `config/marca.json` and edit it.

---

## Quality: what LCA checks on its own

Before showing you anything, LCA checks:

- **Script:** words per second, a hook in the first 3 seconds, a re-hook halfway, on-screen numbers matching the spoken ones, promises the brand can't make.
- **Images:** face matches the reference, wardrobe matches the sheet, hands and objects not deformed, text or logos invented by the AI, resolution.
- **Clips:** the action really happens (not just zoom), the character doesn't "melt", nothing new pops in, clips accidentally stitched to the previous one.
- **Voice:** each line transcribed and compared with the script (wrong word = redo).
- **Edit:** a contact sheet with one frame per scene, captions over faces, clipped text, final loudness at −14 LUFS, voice 9–11 dB above the music.
- **Attention:** dead spots, where viewers tend to drop off, and what to change.

Nothing is approved just because the AI returned a file.

---

## FAQ

**Do I have to pay for anything?**
No. You can make complete videos using only free paths. Paid APIs speed things up and add options (AI-animated clips, images), always with the cost shown first.

**Can it use my own voice?**
Yes: record the lines and LCA uses them, or set up a local cloned voice (VoiceStudio) in `config/provedores.json`.

**Can I use real people in the images?**
Yes, from photos you provide — and only with each person's image-use consent.

**What about music?**
LCA uses libraries with commercial licenses (Pixabay), checks each track's license and warns you when a track is registered with Content ID (it may trigger an automatic claim on YouTube).

**Does it work on macOS and Linux?**
Yes. The scripts are Python + ffmpeg + Node; keys live in a `.env` file. On Windows it also reads the user's environment variables.

**Can I use it in English?**
The skill is written in Brazilian Portuguese and replies in Portuguese by default. You can ask for narration in other languages. A full English version would require translating the skill itself — contributions are welcome.

---

## Project structure

```
SKILL.md        the Director's instructions (the skill's "brain")
agentes/        the 10 departments (installed in ~/.claude/agents)
scripts/        the tools: voice, images, clips, mixing, inspection, costs, keys
templates/      ready-made Remotion projects (ad, story, motion graphics)
references/     guides: interview, hook, script, sync, editing, ads, attention
memoria/        what LCA learns from you (starts empty)
config/         provider catalog and prices, routing, brand
assets/sfx/     synthesized sound effects
tests/          tests with no internet and no spending
docs/           technical docs (router, production, examples)
```

### Tests

```bash
for t in tests/test_*.py; do python "$t"; done
```

They run offline and spend nothing (paid providers are mocked). Tests that need optional packages (`librosa`,
`gradio_client`, `scikit-image`) are **skipped with a notice** when the package isn't installed. GitHub runs the whole
suite on every push, on Ubuntu and Windows.

- Exact versions the tests passed with: `requirements-lock.txt` (`pip install -r requirements-lock.txt`).
- On Windows, if a script shows a character error (`UnicodeEncodeError`), run `set PYTHONUTF8=1` first
  (or `$env:PYTHONUTF8=1` in PowerShell). The skill already does this for the scripts it launches itself.

---

## Notices

- **Remotion** is free for individuals and companies with up to 3 employees; beyond that it requires a [Remotion license](https://www.remotion.dev/license).
- Paid services charge **your** account; keep an eye on each balance.
- Respect each service's terms — no multiple accounts to get around free quotas.
- Don't use third-party brands, characters or music without a license.

## Contributing

Issues and pull requests are welcome. Before submitting, run the tests and make sure no personal data (keys, phone numbers, local paths) made it into the commit.

## License

[MIT](LICENSE) © 2026 Albifran ([github.com/albifrancosta](https://github.com/albifrancosta))
