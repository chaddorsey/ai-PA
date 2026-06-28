#!/usr/bin/env python3
"""Voice audition — synthesize one sample (a squib + an interstitial) across the
professional TTS engines we have keys for, so the candidates can be compared by ear.
Saves audition_voices/<engine>.mp3. Build-time exploration; needs API keys in .env."""
import json
import re
import sys
import urllib.request
from pathlib import Path

DIR = Path(__file__).resolve().parent
OUT = DIR / 'audition_voices'
OUT.mkdir(exist_ok=True)


def _env(key):
    p = DIR
    for _ in range(6):
        f = p / '.env'
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith(key + '='):
                    return line.split('=', 1)[1].strip()
        p = p.parent
    return None


def _req(url, headers, data=None, method=None):
    r = urllib.request.Request(url, data=data, headers=headers, method=method or ('POST' if data else 'GET'))
    with urllib.request.urlopen(r, timeout=90) as resp:
        return resp.read()


def _json(url, headers):
    return json.loads(_req(url, headers))


def sample_text():
    n = json.loads((DIR / 'data' / 'route_narration.json').read_text())['3']
    sqs = [u for u in n if u['kind'] == 'squib' and 1075 <= u.get('mile', 0) <= 1100] \
        or [u for u in n if u['kind'] == 'squib']
    its = [u for u in n if u['kind'] == 'interstitial' and 1050 <= u.get('from_mi', 0) <= 1110] \
        or [u for u in n if u['kind'] == 'interstitial']
    sq = sqs[0]
    it = max(its, key=lambda u: len(u['text'].split()))   # the meatiest interstitial nearby
    return sq['text'].strip() + "\n\n" + it['text'].strip()


def eleven(text):
    key = _env('ELEVENLABS_API_KEY')
    vs = _json('https://api.elevenlabs.io/v1/voices', {'xi-api-key': key}).get('voices', [])
    pick = None
    for kw in ('george', 'matilda', 'sarah', 'river', 'will'):   # prefer warm storyteller/mature
        pick = next((v for v in vs if kw in v.get('name', '').lower()), None)
        if pick:
            break
    pick = pick or (vs[0] if vs else None)
    vid, vname = pick['voice_id'], pick['name']
    data = json.dumps({'text': text, 'model_id': 'eleven_multilingual_v2'}).encode()
    audio = _req(f'https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128',
                 {'xi-api-key': key, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'}, data)
    return audio, vname


def openai(text):
    key = _env('OPENAI_API_KEY')
    data = json.dumps({'model': 'gpt-4o-mini-tts', 'voice': 'fable', 'input': text,
                       'instructions': 'A warm, wise, unhurried rail-travel companion riding alongside the listener; documentary-narrator tone, measured pace.'}).encode()
    return _req('https://api.openai.com/v1/audio/speech',
                {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, data), 'fable'


def cartesia(text):
    key, ver = _env('CARTESIA_API_KEY'), '2024-11-13'
    vs = _json('https://api.cartesia.ai/voices', {'X-API-Key': key, 'Cartesia-Version': ver})
    vl = vs if isinstance(vs, list) else vs.get('data', vs.get('voices', []))
    pick = None
    for kw in ('narrat', 'documentary', 'audiobook', 'thinker', 'deep', 'calm', 'ronald'):
        pick = next((v for v in vl if kw in (v.get('name', '') + ' ' + (v.get('description') or '')).lower()), None)
        if pick:
            break
    pick = pick or (vl[0] if vl else None)
    vid = pick['id']
    data = json.dumps({'model_id': 'sonic-2', 'transcript': text, 'language': 'en',
                       'voice': {'mode': 'id', 'id': vid},
                       'output_format': {'container': 'mp3', 'sample_rate': 44100, 'bit_rate': 128000}}).encode()
    return _req('https://api.cartesia.ai/tts/bytes',
                {'X-API-Key': key, 'Cartesia-Version': ver, 'Content-Type': 'application/json'}, data), pick.get('name', vid)


def deepgram(text):
    key = _env('DEEPGRAM_API_KEY')
    model = 'aura-2-apollo-en'   # Aura caps ~2000 chars/request → chunk on paragraphs/sentences
    chunks, buf = [], ''
    for part in re.split(r'(\n\n|(?<=[.!?]) )', text):
        if len(buf) + len(part) > 1800:
            chunks.append(buf)
            buf = ''
        buf += part
    if buf.strip():
        chunks.append(buf)
    audio = b''
    for c in chunks:
        if c.strip():
            audio += _req(f'https://api.deepgram.com/v1/speak?model={model}',
                          {'Authorization': 'Token ' + key, 'Content-Type': 'application/json'},
                          json.dumps({'text': c.strip()}).encode())
    return audio, f'{model} ({len(chunks)} chunks)'


def main():
    text = sample_text()
    (OUT / 'SAMPLE.txt').write_text(text)
    print(f"  sample: {len(text.split())} words / {len(text)} chars\n")
    for name, fn in [('elevenlabs', eleven), ('openai', openai), ('cartesia', cartesia), ('deepgram', deepgram)]:
        try:
            audio, voice = fn(text)
            (OUT / f'{name}.mp3').write_bytes(audio)
            print(f"  {name}: OK  voice='{voice}'  {len(audio) // 1024} KB")
        except urllib.error.HTTPError as e:
            print(f"  {name}: HTTP {e.code} — {e.read()[:200].decode(errors='replace')}")
        except Exception as e:
            print(f"  {name}: ERROR {str(e)[:200]}")


if __name__ == '__main__':
    import urllib.error
    main()
