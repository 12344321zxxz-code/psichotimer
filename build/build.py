#!/usr/bin/env python3
"""Builds audio/exam.mp3: one continuous track for the whole exam.

Silence, and at each event time: a short beep followed by a spoken
announcement (Google Translate voice via gTTS). Because it is a single
audio file, it keeps playing on an iPhone with the screen locked.

Usage: python3 build/build.py          (needs internet for gTTS)
       python3 build/build.py --fake   (sine tones instead of speech, for testing)
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 16000
FAKE = "--fake" in sys.argv

with open(os.path.join(ROOT, "schedule.json"), encoding="utf-8") as f:
    SCHEDULE = json.load(f)


def events():
    """(seconds, text) for every announcement, in order."""
    out, t = [], 0
    secs = SCHEDULE["sections"]
    for i, s in enumerate(secs):
        start_text = s["start"] if i == 0 else f'{secs[i-1]["end"]} {s["start"]}'
        out.append((t * 60, start_text))
        out.append(((t + s["minutes"] - 5) * 60, s["five"]))
        t += s["minutes"]
    out.append((t * 60, f'{secs[-1]["end"]} {SCHEDULE["finish"]}'))
    return out


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main():
    tmp = tempfile.mkdtemp()
    pcm = ["-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le"]

    # beep: two short tones
    beep = os.path.join(tmp, "beep.wav")
    ff("-f", "lavfi", "-i", "sine=frequency=880:duration=0.22",
       "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=0.12",
       "-f", "lavfi", "-i", "sine=frequency=1175:duration=0.3",
       "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=0.4",
       "-filter_complex", "[0][1][2][3]concat=n=4:v=0:a=1,volume=0.45", *pcm, beep)

    clips = []
    for n, (t, text) in enumerate(events()):
        speech = os.path.join(tmp, f"s{n}.wav")
        if FAKE:
            ff("-f", "lavfi", "-i", "sine=frequency=300:duration=3", *pcm, speech)
        else:
            from gtts import gTTS
            mp3 = os.path.join(tmp, f"s{n}.mp3")
            gTTS(text, lang="iw").save(mp3)
            ff("-i", mp3, "-af", "volume=1.6", *pcm, speech)
        clip = os.path.join(tmp, f"c{n}.wav")
        ff("-i", beep, "-i", speech, "-filter_complex", "[0][1]concat=n=2:v=0:a=1", *pcm, clip)
        clips.append((t, clip))
        print(f"{t//60:>4} min  {text}")

    # silence + clip, silence + clip, ...
    parts, pos = [], 0.0
    for n, (t, clip) in enumerate(clips):
        gap = t - pos
        if gap > 0.01:
            sil = os.path.join(tmp, f"sil{n}.wav")
            ff("-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", f"{gap:.3f}", *pcm, sil)
            parts.append(sil)
        parts.append(clip)
        pos = t + dur(clip)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)

    os.makedirs(os.path.join(ROOT, "audio"), exist_ok=True)
    out = os.path.join(ROOT, "audio", "exam.mp3")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libmp3lame", "-q:a", "7", out)
    print(f"wrote {out}: {dur(out)/60:.1f} min, {os.path.getsize(out)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
