#!/usr/bin/env python3
"""Convert a (scanned) PDF to single-column markdown, one page at a time, via a VLM.

For each page: render to PNG, send the image to an OpenAI vision model, and ask it
to transcribe the page into reading-order, SINGLE-COLUMN markdown -- explicitly
merging any multi-column layout into one flow. This sidesteps layout-segmentation
errors (e.g. side-by-side keys) because the model sees the whole page.

Usage:
  python tools/vlm_pdf_to_md.py INPUT.pdf -o OUT.md [--pages 1-4] [--model gpt-5.4-mini] [--dpi 200]

Env: OPENAI_API_KEY must be set (or pass --api-key).
"""
import argparse, base64, json, os, subprocess, sys, tempfile, time
from pathlib import Path

PROMPT = """You are transcribing one page of a scanned botanical reference book (Wagner's Manual of the Flowering Plants of Hawai'i) into Markdown.

Rules:
- FIRST, look at the running header at the very top of the page. It contains the printed page number (the folio), usually at the top-OUTER corner (top-right on right-hand pages, top-left on left-hand pages), next to a running head such as "ASTERACEAE" or a genus name. Output it as the FIRST line of your response, in exactly this format: "[page: N]" where N is that printed number (e.g. "[page: 244]"). If no printed page number is visible (e.g. a full-page plate), output "[page: ?]" instead. Do not invent a number.
- Transcribe ALL text on the page, exactly, including italics, diacritics (ʻokina, kahakō), numbers, ranges like "0.5-2(-3) mm", and bracketed notes like "[2n = 22.]".
- IMPORTANT: If the page has MULTIPLE COLUMNS, do NOT preserve the columns. Read the text in correct human reading order (for ordinary body text: left column top-to-bottom, then right column top-to-bottom; a sentence that breaks at the bottom of one column and continues at the top of the next must be JOINED into one continuous sentence). Output everything as a SINGLE COLUMN of flowing Markdown.
- Special case for identification KEYS laid out as two independent side-by-side keys: transcribe the entire LEFT key first (top to bottom), then the entire RIGHT key (top to bottom). Never interleave lines from the two keys. Keep each numbered couplet (e.g. "3(2).", "4.") on its own line, and keep the dotted leader + genus number that ends a couplet (e.g. "...... 43. Hypochoeris").
- Use Markdown headings (#) for species/genus headings and the family name. Use normal paragraphs for descriptions. Use a Markdown list for key couplets.
- If a figure/illustration is present, insert a line: ![figure](page-figure) where it appears, but do not invent a caption.
- Output ONLY the Markdown for this page. No preamble, no explanation, no code fences.
"""

PRICING = {  # USD per 1M tokens: (input, cached_input, output)
    "gpt-5.4-mini": (0.25, 0.025, 2.00),
    "gpt-5.4":      (2.50, 0.25, 15.00),
}


def parse_pages(spec, total):
    if not spec:
        return list(range(1, total + 1))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def pdf_page_count(pdf):
    r = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise RuntimeError("could not read page count")


def render_page(pdf, page, dpi, outdir):
    prefix = os.path.join(outdir, "pg")
    subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page),
                    "-png", "-r", str(dpi), pdf, prefix],
                   check=True, capture_output=True)
    # pdftoppm zero-pads to the page-count width; just glob for the one file
    files = sorted(Path(outdir).glob("pg*.png"))
    return str(files[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--pages", default=None, help="e.g. 1-4 or 1,4,7 (1-indexed)")
    ap.add_argument("--model", default="gpt-5.4-mini")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    ap.add_argument("--usage-file", default=None)
    args = ap.parse_args()

    import openai
    client = openai.OpenAI(api_key=args.api_key)

    total = pdf_page_count(args.pdf)
    pages = parse_pages(args.pages, total)
    print(f"Converting {len(pages)} page(s) of {args.pdf} with {args.model} @ {args.dpi} dpi", file=sys.stderr)

    tot_in = tot_cached = tot_out = 0
    results = []
    with tempfile.TemporaryDirectory() as td:
        for i, pg in enumerate(pages, 1):
            for f in Path(td).glob("pg*.png"):
                f.unlink()
            png = render_page(args.pdf, pg, args.dpi, td)
            b64 = base64.b64encode(open(png, "rb").read()).decode()
            t0 = time.time()
            resp = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}", "detail": "high"}},
                ]}],
            )
            md = resp.choices[0].message.content
            u = resp.usage
            cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
            tot_in += u.prompt_tokens - cached
            tot_cached += cached
            tot_out += u.completion_tokens
            results.append(f"\n\n<!-- page {pg} -->\n\n{md.strip()}")
            print(f"  [{i}/{len(pages)}] page {pg}: in={u.prompt_tokens} out={u.completion_tokens} "
                  f"({time.time()-t0:.1f}s)", file=sys.stderr)
            if args.usage_file:
                with open(args.usage_file, "a") as uf:
                    uf.write(json.dumps({"page": pg, "model": args.model,
                                         "prompt_tokens": u.prompt_tokens,
                                         "cached_tokens": cached,
                                         "completion_tokens": u.completion_tokens}) + "\n")

    Path(args.out).write_text("".join(results).lstrip())

    pin, pc, pout = PRICING.get(args.model, (0, 0, 0))
    cost = tot_in / 1e6 * pin + tot_cached / 1e6 * pc + tot_out / 1e6 * pout
    print(f"\n=== DONE: wrote {args.out} ===", file=sys.stderr)
    print(f"tokens: input(uncached)={tot_in:,} cached={tot_cached:,} output={tot_out:,}", file=sys.stderr)
    print(f"ESTIMATED COST ({args.model}): ${cost:.4f}", file=sys.stderr)


if __name__ == "__main__":
    main()
