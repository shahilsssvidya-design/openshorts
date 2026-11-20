import json

from app import chat_signals, main


def test_replay_offset_dedup_and_spam():
    replay = {
        'replayChatItemAction': {
            'videoOffsetTimeMsec': '125000',
            'actions': [
                {'addChatItemAction': {'item': {'liveChatTextMessageRenderer': {
                    'id': str(index), 'authorExternalChannelId': str(index),
                    'message': {'runs': [{'text': 'wow'}]},
                }}}}
                for index in range(6)
            ],
        },
    }
    spam = [{'id': f'spam-{index}', 'author_id': 'one', 'offset_seconds': 140, 'text': 'wow'}
            for index in range(100)]
    raw = '\n'.join(map(json.dumps, [replay, replay, *spam]))
    assert chat_signals.chat_bursts(raw, 50, 100) == [{'time': 27.5, 'boost': 12, 'viewers': 6}]


def test_chat_requires_playable_context(monkeypatch):
    transcript = [{
        'start': 0, 'end': 38,
        'text': 'How did this happen? The biggest mistake was waiting. Now the result is surprising!',
    }]
    signal = [{'time': 27.5, 'boost': 12, 'viewers': 6}]
    monkeypatch.setattr(chat_signals, 'has_playable_context', lambda *_: False)
    unboosted = main.rank_clips(transcript, 42, bursts=signal, media_path='recording')
    monkeypatch.setattr(chat_signals, 'has_playable_context', lambda *_: True)
    boosted = main.rank_clips(transcript, 42, bursts=signal, media_path='recording')
    assert all('Chat burst' not in clip['reason'] for clip in unboosted)
    assert boosted[0]['score'] > unboosted[0]['score']
    assert 'Chat burst (6 distinct viewers)' in boosted[0]['reason']


def test_live_chat_uses_api_timestamps_and_poll_interval(monkeypatch):
    from app import channel_monitor

    calls = []

    def google(path, params):
        calls.append((path, params.copy()))
        if path == 'videos':
            return {'items': [{'liveStreamingDetails': {'activeLiveChatId': 'chat-id'}}]}
        return {
            'pollingIntervalMillis': 3000,
            'nextPageToken': 'next',
            'items': [{
                'id': 'msg-1',
                'authorDetails': {'channelId': 'author-1'},
                'snippet': {'type': 'textMessageEvent', 'displayMessage': 'wow',
                            'publishedAt': '1970-01-01T00:02:05Z'},
            }],
        }

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            assert seconds == 3
            return True

    monkeypatch.setattr(channel_monitor, '_google', google)
    rows, state = [], {}
    chat_signals.collect_live('video-id', Stop(), rows, state)
    assert calls[1][1]['liveChatId'] == 'chat-id'
    assert rows == [{'id': 'msg-1', 'author_id': 'author-1', 'text': 'wow', 'offset_seconds': 125}]
    assert not state
