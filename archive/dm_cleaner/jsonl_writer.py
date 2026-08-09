import json, datetime

def to_records(doc_id: str, system: str, setting_guess: str, filename: str, chunks):
    now = datetime.datetime.utcnow().isoformat()+'Z'
    for i, ch in enumerate(chunks, 1):
        yield {
            'doc_id': doc_id,
            'chunk_id': f"{doc_id}:{i:04d}",
            'title': None,
            'type': 'story',
            'system': system,
            'setting': setting_guess,
            'tone': ch['story'].get('Tones', []),
            'themes': ch['story'].get('Themes', []),
            'acts': ch.get('acts', []),
            'read_aloud': ch.get('read_aloud', []),
            'interrupt_points': ch.get('interrupt_points', []),
            'solo_targets': ch.get('solo_targets', []),
            'story_elements': ch.get('story', {}),
            'content': ch.get('text', ''),
            'created_at': now,
            'source_file': filename,
        }

def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def write_csv(path, records):
    import pandas as pd
    df = pd.DataFrame(list(records))
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
