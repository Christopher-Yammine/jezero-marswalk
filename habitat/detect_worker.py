"""Detection worker: loads a detector once, then answers one JSON request per stdin line.

Runs under a Python that has torch + transformers (the mars-walk-dataset venv), separate from the
lightweight habitat server. Request:  {"path": "/abs/image.jpg"}
Reply (one line):  {"ok": true, "w": W, "h": H, "ms": N, "model": "...", "detections": [
                      {"class": "sand", "prompt": "...", "score": 0.31, "box": [x, y, w, h] as 0..1 fractions}]}

Today the detector is OWLv2 zero-shot (not trained on Mars, so its boxes are suggestions).
When the trained small model exists, it replaces `detect()` and nothing else changes.
"""
import json, sys, time

PROMPTS = {
    'a large boulder': 'boulders', 'a big rock': 'boulders',
    'small sharp rocks': 'sharp_rocks', 'scattered pebbles': 'sharp_rocks',
    'a sand ripple': 'sand', 'a sand dune': 'sand', 'a patch of loose sand': 'sand',
    'flat bedrock': 'bedrock', 'a rock ledge or cliff edge': 'ledge', 'a small crater or pit': 'pit',
    'a rover wheel': 'rover_hardware', 'part of a robot or machine': 'rover_hardware',
    'tire tracks in the dirt': 'rover_tracks',
}
THR, MAX_SIDE = 0.12, 960
# Per-hazard cut-off and minimum box size (fraction of the image), tuned on hand-sorted photos by
# mars-walk-dataset/scripts/tune_thresholds.py. Missing file -> the raw 0.12 threshold for everything.
try:
    from pathlib import Path as _P
    TUNED = json.load(open(_P(__file__).with_name('detector_thresholds.json')))
except Exception:
    TUNED = {}


def main():
    import torch
    from PIL import Image, ImageOps
    from transformers import Owlv2Processor, Owlv2ForObjectDetection
    torch.set_num_threads(4)
    name = 'google/owlv2-base-patch16-ensemble'
    proc = Owlv2Processor.from_pretrained(name)
    model = Owlv2ForObjectDetection.from_pretrained(name).eval()
    texts = list(PROMPTS)
    print(json.dumps({'ready': True, 'model': name}), flush=True)

    def iou(a, b):
        ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])); iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
        i = ix * iy; return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)

    for line in sys.stdin:
        t0 = time.time()
        try:
            req = json.loads(line)
            im = ImageOps.exif_transpose(Image.open(req['path'])).convert('RGB')   # phone photos carry rotation in EXIF
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            W, H = im.size; side = max(W, H)
            inp = proc(text=[texts], images=im, return_tensors='pt')
            with torch.no_grad():
                out = model(**inp)
            res = proc.post_process_object_detection(out, threshold=THR, target_sizes=torch.tensor([[side, side]]))[0]
            dets = []
            for box, sc, lb in zip(res['boxes'].tolist(), res['scores'].tolist(), res['labels'].tolist()):
                x0, y0 = max(0, box[0]), max(0, box[1]); x1, y1 = min(W, box[2]), min(H, box[3])
                w, h = x1 - x0, y1 - y0
                if w < 8 or h < 8 or w * h > 0.9 * W * H:
                    continue
                dets.append({'class': PROMPTS[texts[lb]], 'prompt': texts[lb], 'score': round(sc, 3),
                             'box': [round(x0 / W, 4), round(y0 / H, 4), round(w / W, 4), round(h / H, 4)]})
            dets.sort(key=lambda d: -d['score']); kept = []
            for d in dets:
                if all(not (d['class'] == k['class'] and iou(d['box'], k['box']) > 0.5) for k in kept):
                    kept.append(d)
            def passes(d):
                t = TUNED.get(d['class'])
                return not t or (d['score'] >= t['min_score'] and d['box'][2] * d['box'][3] >= t['min_area'])
            final = [d for d in kept if passes(d)]
            print(json.dumps({'ok': True, 'w': W, 'h': H, 'ms': int((time.time() - t0) * 1000), 'model': name,
                              'tuned': bool(TUNED), 'raw_count': len(kept), 'detections': final[:40]}), flush=True)
        except Exception as e:
            print(json.dumps({'ok': False, 'error': str(e)}), flush=True)


if __name__ == '__main__':
    main()
