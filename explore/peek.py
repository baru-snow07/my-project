"""Print the first record(s) of a .json.zst file without decompressing it to disk."""
import sys, json, zstandard

with open(sys.argv[1], 'rb') as fh:
    raw = zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh).read(2_000_000)
text = raw.decode('utf-8', errors='replace')
print("FIRST 200 CHARS:", repr(text[:200]))
lines = text.split('\n')
print("newline-separated lines in first 2 MB:", len(lines))
print(json.dumps(json.loads(lines[0]), indent=1)[:6000])
