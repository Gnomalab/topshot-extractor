# TopShot
### Smart Frame Extractor for 3DGS & Photogrammetry
**by Gnomalab Studio 2026 — [gnomalab.es](https://www.gnomalab.es)**

---

TopShot analyzes video and automatically selects the best frames for 3D Gaussian Splatting, NeRF, and photogrammetry workflows (Metashape, COLMAP, Postshot, RealityCapture).

Unlike basic frame extractors, TopShot uses three quality filters in cascade to ensure only clean, sharp, non-redundant frames make it into your dataset.

---

## What makes TopShot different

Most frame extractors simply grab frames at a fixed interval. TopShot goes further:

| Filter | What it does |
|---|---|
| **Blur detection** (Laplacian variance) | Rejects out-of-focus or motion-blurred frames |
| **Camera shake** (Farneback optical flow) | Detects and discards frames with excessive camera movement |
| **Duplicate detection** (Perceptual hash) | Removes redundant frames that add no new information |

No other tool in the 3DGS ecosystem combines all three filters with a visual review interface.

---

## Features

- Smart automatic selection (Auto mode) or uniform distribution (Manual mode)
- IN/OUT trim zone — analyze only the portion you need
- Visual filmstrip with frame preview and per-frame exclusion
- ffmpeg acceleration (up to 20x faster analysis when available)
- Full-resolution export in JPG or PNG
- SmartShot — one-click full pipeline from video to export
- Optional analysis report `.txt`
- Keyboard shortcuts for fast review

---

## Installation

**Requirements:** Python 3.10+

```bash
pip install opencv-python numpy Pillow customtkinter tkinterdnd2
```

**Windows:** Double-click `Abrir_TopShot.bat` — it installs all dependencies automatically.

**Mac / Linux:** Run directly:
```bash
python topshot_extractor.py
```

### Optional — ffmpeg (recommended)

ffmpeg accelerates analysis up to 20x by working with I-frames only.
Click the **ffmpeg ?** badge in the toolbar to auto-install it.

---

## Usage

1. Drag a video onto the window or click **Abrir**
2. *(Optional)* Mark an IN/OUT zone on the timeline
3. Click **Analizar** — TopShot scores every frame
4. Review the filmstrip, exclude unwanted frames if needed
5. Click **Exportar**

### SmartShot (one-click mode)

Click **SmartShot** on the welcome screen for fully automatic analysis and export with zero configuration.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `I` | Mark IN point |
| `O` | Mark OUT point |
| `←` / `→` | Step 1 frame |
| `Shift + ←` / `Shift + →` | Step 10 frames |
| `Home` / `End` | Go to start / end |
| `E` | Export selected frames |

---

## Output

Frames are saved next to the source video in a folder named `videoname_topshot/`.
Custom output folder available in the bottom bar or in Preferences.

---

## Roadmap

- **v1.0.0** — Exposure/color consistency detection, overlap estimation, health timeline, SmartShot v2
- **v1.1.0** — LichtFeld Studio plugin integration
- **v1.2.0** — Batch processing queue

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Credits

TopShot uses [OpenCV](https://opencv.org/), [ffmpeg](https://ffmpeg.org/), [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), and [Pillow](https://python-pillow.org/).
