"""Reduce authorized, recording-relative chat logs to candidate highlight times."""
import json
import math
import re
import subprocess
from collections import defaultdict
from statistics import median

MAX_LOG_BYTES = 8 * 1024 * 1024
REACTION = re.compile(r"\b(?:wow|omg|lmao|lol|no way|clutch|insane|goat|kya|bhai|gg)\b|[😂🤣🔥😱]", re.I)


def chat_bursts(raw, duration, recording_offset=0):
    """Accept normalized JSONL and YouTube live chat replay JSONL."""
    bins = defaultdict(dict)
    seen = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError('Each chat line must be a JSON object')
        if 'replayChatItemAction' in row:
            replay = row['replayChatItemAction']
            position = float(replay['videoOffsetTimeMsec']) / 1000
            messages = (action.get('addChatItemAction', {}).get('item', {}).get('liveChatTextMessageRenderer', {})
                        for action in replay.get('actions', []))
            entries = ((msg.get('id'), msg.get('authorExternalChannelId'),
                        ' '.join(run.get('text', run.get('emoji', {}).get('shortcuts', [''])[0])
                                 for run in msg.get('message', {}).get('runs', [])))
                       for msg in messages)
        elif 'offset_seconds' in row:
            position = float(row['offset_seconds'])
            entries = [(row.get('id'), row.get('author_id'), row.get('text', ''))]
        else:
            continue
        t = position - recording_offset
        if not math.isfinite(t) or not 0 <= t < duration:
            continue
        for identity, author, message in entries:
            if not all(isinstance(value, str) and value for value in (identity, author, message)):
                continue
            if identity in seen:
                continue
            seen.add(identity)
            bucket = bins[int(t // 5)]
            bucket[author] = bucket.get(author, False) or bool(REACTION.search(message[:500]))
    result = []
    for index, authors in sorted(bins.items()):
        baseline = median(len(bins.get(n, {})) for n in range(max(0, index - 12), index)) if index else 0
        reactions = sum(authors.values())
        if len(authors) < max(4, baseline * 2.5, baseline + 3):
            continue
        if reactions < 2 and len(authors) < max(8, baseline * 3):
            continue
        strength = min(12, len(authors) - baseline + reactions)
        item = {'time': index * 5 + 2.5, 'boost': round(strength), 'viewers': len(authors)}
        if result and item['time'] - result[-1]['time'] <= 10:
            if item['boost'] > result[-1]['boost']:
                result[-1] = item
        else:
            result.append(item)
    return sorted(result, key=lambda burst: -burst['boost'])[:40]


def has_playable_context(path, time):
    """Check for audible audio and nonblack video around the inferred moment."""
    try:
        checked = subprocess.run(
            ['ffmpeg', '-nostdin', '-hide_banner', '-ss', str(max(0, time - 3)), '-i', str(path),
             '-t', '6', '-map', '0:v:0', '-map', '0:a:0', '-vf',
             'scale=160:-2,blackdetect=d=0.5:pix_th=0.10', '-af',
             'silencedetect=n=-42dB:d=0.5', '-f', 'null', '-'],
            capture_output=True, text=True, timeout=15, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    for kind in ('black', 'silence'):
        durations = re.findall(rf'{kind}_duration\s*:\s*([\d.]+)', checked.stderr)
        if sum(map(float, durations)) >= 4:
            return False
    return True


def boost_candidates(candidates, bursts, media_path):
    """Let chat surface speech windows after playback and transcript checks."""
    boosted = set()
    for burst in bursts[:8]:
        # Viewer reactions usually trail the source moment.
        moment = max(0, burst['time'] - 5)
        nearby = [clip for clip in candidates
                  if clip['start'] <= moment <= clip['end'] - 2 and clip['score'] >= 55]
        if not nearby or not has_playable_context(media_path, moment):
            continue
        clip = max(nearby, key=lambda item: (
            item['score'] - abs(moment - (item['start'] + (item['end'] - item['start']) * .65)) * .3,
            -(item['end'] - item['start']),
        ))
        if id(clip) in boosted:
            continue
        boosted.add(id(clip))
        clip['score'] = min(99, clip['score'] + burst['boost'])
        clip['reason'] += f" · Chat burst ({burst['viewers']} distinct viewers)"
    return candidates


def collect_live(video_id, stop, rows, state):
    """Collect one capture window from the official YouTube Data API."""
    from datetime import datetime
    from .channel_monitor import DiscoveryError, _google

    try:
        video = _google('videos', {'part': 'liveStreamingDetails', 'id': video_id})
        videos = video.get('items', [])
        chat_id = videos[0].get('liveStreamingDetails', {}).get('activeLiveChatId') if videos else None
        if not chat_id:
            state['message'] = 'No accessible live chat for this broadcast'
            return
        params = {'part': 'snippet,authorDetails', 'liveChatId': chat_id, 'maxResults': 200}
        pages = 0
        while not stop.is_set() and pages < 40:
            page = _google('liveChat/messages', params)
            for item in page.get('items', []):
                snippet = item['snippet']
                if snippet['type'] != 'textMessageEvent':
                    continue
                rows.append({
                    'id': item['id'],
                    'author_id': item.get('authorDetails', {}).get('channelId'),
                    'text': snippet.get('displayMessage', '')[:500],
                    'offset_seconds': datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00')).timestamp(),
                })
            pages += 1
            token = page.get('nextPageToken')
            if token:
                params['pageToken'] = token
            if stop.wait(max(1, float(page.get('pollingIntervalMillis', 5000)) / 1000)):
                break
    except (DiscoveryError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        state['message'] = 'Live chat unavailable; using recording and transcript'
