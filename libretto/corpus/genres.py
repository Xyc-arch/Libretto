"""libretto.corpus.genres — evidence-grounded artist -> genre assignment from MusicBrainz.

Query the MusicBrainz search API (structured, citable) for an artist's community genre tags, map them
(count-weighted) to a cleaned taxonomy, and record the chosen bucket + confidence + evidence (top MB tags)
+ MBID URL. Grounds corpus genre labels in an external source, not one person's judgment; low confidence
flags ambiguous artists for review. Rate-limited <=1 req/s with a descriptive UA (MusicBrainz policy).

Resumable file output (append, skips artists already grounded):
  python -m libretto.corpus.genres ARTIST [ARTIST2 ...]
  python -m libretto.corpus.genres --file artists.txt --out grounded.jsonl
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

UA = "LibrettoCorpus/1.0 (research; symbolic-music corpus genre grounding)"

# cleaned taxonomy: (bucket, keyword substrings). Order = priority (specific before the generic pop/rock).
TAXONOMY = [
    ("classical",       ["classical", "baroque", "romantic", "impressionist", "orchestral", "opera",
                         "chamber music", "symphony", "concerto"]),
    ("metal",           ["metal", "thrash"]),
    ("hiphop_rap",      ["hip hop", "hip-hop", "rap", "trap"]),
    ("reggae_ska",      ["reggae", "ska", "dub", "dancehall"]),
    ("latin",           ["latin", "salsa", "flamenco", "tango", "bossa nova", "bossa", "samba", "merengue",
                         "cumbia", "mambo", "bolero", "cuban"]),
    ("jazz",            ["jazz", "bebop", "swing", "big band", "fusion", "smooth jazz"]),
    ("funk_soul_rnb",   ["funk", "soul", "r&b", "rhythm and blues", "rhythm & blues", "motown", "disco",
                         "new jack swing"]),
    ("blues_gospel",    ["blues", "gospel"]),
    ("folk_country",    ["folk", "country", "americana", "bluegrass", "singer-songwriter"]),
    ("film_score",      ["soundtrack", "film score", "score", "new age"]),
    ("electronic_dance", ["electronic", "electronica", "dance", "techno", "house", "trance", "edm",
                          "synthpop", "synth-pop", "eurodance", "industrial", "ambient", "downtempo"]),
    ("pop_rock",        ["pop", "rock", "new wave", "britpop", "power pop", "soft rock", "classic rock"]),
]
GENRES = [b for b, _ in TAXONOMY]


def norm_name(name):
    """clean_midi folder-name -> query name. Handles 'Last,First' and stray quotes."""
    n = name.strip().strip('"').strip()
    if "," in n:
        parts = [p.strip() for p in n.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            n = f"{parts[1]} {parts[0]}"
    return n


def _tag_bucket(tag):
    t = tag.lower()
    for bucket, kws in TAXONOMY:
        if any(k in t for k in kws):
            return bucket
    return None


def mb_query(artist):
    q = urllib.parse.quote(f'artist:"{norm_name(artist)}"')
    url = f"https://musicbrainz.org/ws/2/artist/?query={q}&fmt=json&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def ground(artist):
    """Return {artist, genre, confidence, evidence, mbid, mb_url} (genre None if unmatched/unmappable)."""
    try:
        d = mb_query(artist)
        a = (d.get("artists") or [None])[0]
        toks = norm_name(artist).split()
        if not a and len(toks) == 2:                    # 'Reinhardt Django' -> retry 'Django Reinhardt'
            time.sleep(1.1)
            d = mb_query(f"{toks[1]} {toks[0]}")
            a = (d.get("artists") or [None])[0]
    except Exception as e:  # noqa: BLE001
        return dict(artist=artist, genre=None, confidence=0.0, evidence=[], mbid=None, error=str(e)[:80])
    if not a:
        return dict(artist=artist, genre=None, confidence=0.0, evidence=[], mbid=None, error="no MB match")
    tags = sorted(a.get("tags", []), key=lambda t: -t.get("count", 0))
    votes = {}
    for t in tags:
        b = _tag_bucket(t["name"])
        if b:
            votes[b] = votes.get(b, 0) + max(1, t.get("count", 1))
    if not votes:
        return dict(artist=artist, genre=None, confidence=0.0, mbid=a.get("id"),
                    evidence=[t["name"] for t in tags[:6]], error="no mappable tag")
    total = sum(votes.values())
    genre = max(votes, key=votes.get)
    return dict(artist=artist, genre=genre, confidence=round(votes[genre] / total, 2),
                mbid=a.get("id"), mb_url=f"https://musicbrainz.org/artist/{a.get('id')}",
                evidence=[f"{t['name']}({t.get('count', 0)})" for t in tags[:6]])


def main(argv=None):
    args = list(argv or sys.argv[1:])
    out = None
    if "--out" in args:
        i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
    if "--file" in args:
        i = args.index("--file"); names = [x.strip() for x in open(args[i + 1]) if x.strip()]; del args[i:i + 2]
    else:
        names = args
    done = set()
    fh = None
    if out:
        if os.path.exists(out):
            done = {json.loads(l).get("artist") for l in open(out) if l.strip()}
        fh = open(out, "a")
    todo = [n for n in names if n not in done]
    for j, name in enumerate(todo):
        line = json.dumps(ground(name))
        (fh.write(line + "\n"), fh.flush()) if fh else print(line)
        if j < len(todo) - 1:
            time.sleep(1.1)
    if fh:
        fh.close(); print(f"grounded {len(todo)} new ({len(done)} skipped) -> {out}")


if __name__ == "__main__":
    main()
